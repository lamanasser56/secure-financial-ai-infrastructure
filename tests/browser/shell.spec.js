import {test, expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {readFile} from 'node:fs/promises';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {assets} from './server.js';

const here = dirname(fileURLToPath(import.meta.url)), root = join(here, '../..');
const projection = name => JSON.parse(execFileSync(process.env.PYTHON || 'python3', [join(here, name)], {encoding: 'utf8'}));
const data = projection('presentation_payloads.py'), ops = projection('ops_payloads.py');
const sharedRoot = join(root, 'platform/core/ui');
const shared = JSON.parse(await readFile(join(sharedRoot, 'shared-assets.json'), 'utf8')).assets;
let consoleServer, financial, guide, errors;
test.use({reducedMotion: 'reduce'});
test.beforeAll(async () => {
  consoleServer = await assets('platform/core/ui');
  financial = await assets('platform/agents/financial/finance_agent/ui');
  guide = await assets('platform/agents/platform-guide/public');
});
test.afterAll(async () => { await consoleServer.close(); await financial.close(); await guide.close(); });
test.beforeEach(({page}) => { errors = []; page.on('pageerror', error => errors.push(error.message)); });
test.afterEach(() => { expect(errors).toEqual([]); });

async function finance(page, handle = () => false) {
  const requests = [];
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url()); requests.push(url.pathname);
    if (await handle(route, url)) return;
    return route.fulfill({json: url.pathname === '/api/me' ? data.profile : url.pathname === '/api/expenses' ? {expenses: []} : data.reply});
  });
  await page.goto(financial.origin);
  await expect(page.locator('#q')).toBeVisible();
  return requests;
}
async function consolePage(page, hash = '#/ops', limited = false) {
  await page.route('**/api/console/**', route => {
    const url = new URL(route.request().url()), key = url.pathname + url.search;
    const value = structuredClone(data.endpoints[key] || {available: false});
    if (key === '/api/console/agents' && limited) value.live_available = false;
    return route.fulfill({json: value});
  });
  await page.route('**/api/bootstrap', route => route.fulfill({json: {csrf: 'synthetic-csrf'}}));
  await page.route('**/api/operations', route => route.fulfill({json: route.request().postDataJSON().operation === 'security' ? ops.security : ops.overview}));
  await page.goto(consoleServer.origin + '/' + hash);
  await expect(page.locator('main h1')).toBeVisible();
}
async function skip(page) {
  await page.locator('.skip').focus(); await page.keyboard.press('Enter');
  await expect(page.locator('#view')).toBeFocused();
}

test('every shared route has identical canonical bytes in all three screen compositions', async ({request}) => {
  for (const server of [consoleServer, financial, guide]) {
    for (const [path, kind] of Object.entries(shared)) {
      const response = await request.get(server.origin + path);
      expect(response.status(), server.origin + path).toBe(200);
      expect(response.headers()['content-type']).toBe(kind);
      expect(await response.body()).toEqual(await readFile(join(sharedRoot, path.slice(1))));
    }
    expect((await request.get(server.origin + '/shared-assets.json')).status()).toBe(404);
  }
});

test('skip on Ops retains the route, proposal and typed owner passphrase', async ({page}) => {
  await consolePage(page);
  await expect(page.getByLabel('Owner passphrase', {exact: true})).toBeVisible();
  await page.getByLabel('Owner passphrase', {exact: true}).fill('synthetic-draft');
  await skip(page);
  expect(new URL(page.url()).hash).toBe('#/ops');
  await expect(page.getByRole('heading', {name: 'Security & Operations', exact: true})).toBeVisible();
  await expect(page.getByLabel('Owner passphrase', {exact: true})).toHaveValue('synthetic-draft');
});

for (const ar of [false, true]) {
  test('Financial skip preserves Expenses and draft ' + (ar ? 'in Arabic' : 'in English'), async ({page}) => {
    await finance(page);
    if (ar) await page.getByLabel('Language', {exact: true}).selectOption('ar');
    await page.getByRole('link', {name: ar ? 'المصروفات' : 'Expenses', exact: true}).click();
    await page.locator('#f-merchant').fill('Synthetic draft');
    await skip(page);
    expect(new URL(page.url()).hash).toBe('#/expenses');
    await expect(page.locator('#f-merchant')).toHaveValue('Synthetic draft');
  });
}

test('Guide uses the shared blueprint shell and skip preserves its draft without adding a hash', async ({page}, info) => {
  await page.goto(guide.origin);
  await page.getByLabel('Question', {exact: true}).fill('Synthetic Guide draft');
  await skip(page);
  expect(new URL(page.url()).hash).toBe('');
  await expect(page.getByLabel('Question', {exact: true})).toHaveValue('Synthetic Guide draft');
  await expect(page.getByRole('link', {name: 'Agent passport', exact: true})).toHaveAttribute('href', 'http://127.0.0.1:8080/#/agents/platform-guide');
  expect(await page.locator('body').evaluate(node => getComputedStyle(node).getPropertyValue('--bg').trim())).toBe('#0C2745');
  await expect(page.locator('#connection')).toHaveText('Not checked');
  await page.screenshot({path: info.outputPath('guide-shared-shell.png')});
});

for (const ar of [false, true]) {
  test('idle receipt becomes an old response rather than Offline ' + (ar ? 'in Arabic' : 'in English'), async ({page}) => {
    await page.clock.install();
    const requests = await finance(page);
    if (ar) await page.getByLabel('Language', {exact: true}).selectOption('ar');
    const badge = page.locator('#connection');
    await expect(badge).toHaveText(ar ? 'استجاب الخادم' : 'API answered');
    await page.clock.fastForward(61000);
    await expect(badge).toContainText(ar ? 'آخر استجابة:' : 'Last response:');
    await expect(badge).toHaveAttribute('data-state', 'answered');
    await expect(badge).toHaveAttribute('data-recent', 'false');
    expect(requests).toEqual(['/api/me']);
    expect(await badge.innerText()).not.toMatch(/Offline|غير متصل/);
    await expect(badge).toHaveAttribute('title', ar ? /ليست حكمًا/ : /not a verdict on all services/);
  });
}

for (const failure of ['network', 'bad-json', 'scalar-json', 'http-error']) {
  test('a real ' + failure + ' is separate from idle and recovers after a valid API response', async ({page}) => {
    let turn = 0;
    await finance(page, async (route, url) => {
      if (url.pathname !== '/api/ask' || ++turn > 1) return false;
      if (failure === 'network') await route.abort();
      else if (failure === 'bad-json') await route.fulfill({body: '{', contentType: 'application/json'});
      else if (failure === 'scalar-json') await route.fulfill({json: 'unexpected scalar'});
      else await route.fulfill({status: 503, json: {error: 'unavailable'}});
      return true;
    });
    await page.locator('#q').fill('Synthetic question'); await page.locator('form.send button').click();
    const badge = page.locator('#connection');
    await expect(badge).toHaveAttribute('data-state', failure === 'network' ? 'failed' : failure === 'http-error' ? 'error' : 'invalid');
    expect(await badge.innerText()).not.toMatch(/Offline|API answered/);
    await page.locator('#q').fill('Retry'); await page.locator('form.send button').click();
    await expect(badge).toHaveText('API answered');
  });
}

test('a Console response with unavailable observations stays explicitly limited', async ({page}) => {
  await consolePage(page, '#/map', true);
  await expect(page.locator('#connection')).toContainText('limited data');
  await expect(page.locator('#connection')).not.toHaveClass(/\bon\b/);
});

for (const width of [360, 1440]) {
  test('shared shells and readable Map fit at width ' + width, async ({page}, info) => {
    await page.setViewportSize({width, height: 900});
    await consolePage(page, '#/map');
    await expect(page.getByRole('button', {name: 'Model gateway — how it works', exact: true})).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path: info.outputPath('shared-map-' + width + '.png')});
    await finance(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.goto(guide.origin);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path: info.outputPath('shared-guide-' + width + '.png')});
  });
}
