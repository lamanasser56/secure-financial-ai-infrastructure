import {test, expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {assets} from './server.js';

const here = dirname(fileURLToPath(import.meta.url));
const data = JSON.parse(execFileSync(process.env.PYTHON || 'python3', [join(here, 'presentation_payloads.py')], {encoding: 'utf8'}));
let consoleAssets, financial, guide, errors;
test.use({reducedMotion: 'reduce'});
test.beforeAll(async () => {
  consoleAssets = await assets('platform/core/ui');
  financial = await assets('platform/agents/financial/finance_agent/ui');
  guide = await assets('platform/agents/platform-guide/public');
});
test.afterAll(async () => { await consoleAssets.close(); await financial.close(); await guide.close(); });
test.beforeEach(async ({page}) => { errors = []; page.on('pageerror', error => errors.push(error.message)); });
test.afterEach(() => { expect(errors).toEqual([]); });

async function open(page, {hash = '#/agents/financial', change = () => {}, unavailable = '', requests = []} = {}) {
  await page.route('**/api/console/**', async route => {
    requests.push({method: route.request().method(), url: route.request().url()});
    const url = new URL(route.request().url()), path = url.pathname + url.search;
    const body = structuredClone(data.endpoints[path] || {available: false});
    change(path, body);
    await route.fulfill({status: path === unavailable ? 503 : 200, json: body, headers: {'X-Platform-Source-Commit': 'a'.repeat(40)}});
  });
  await page.goto(consoleAssets.origin + '/' + hash);
  if (hash.startsWith('#/map')) await expect(page.locator('.stats')).toBeVisible();
  else await expect(page.getByRole('heading', {name: hash.startsWith('#/onboard') ? 'Review onboarding.' : 'Agent passports', exact: true})).toBeVisible();
  if (hash.startsWith('#/agents')) await expect(page.locator('.passport')).toBeVisible();
  if (hash.startsWith('#/onboard')) await expect(page.getByRole('region', {name: 'Manifest summary'})).toBeVisible();
}

test('a single Ops observation is partial coverage, never a VERIFIED passport', async ({page}, info) => {
  await open(page, {hash: '#/agents/ops-agent'});
  const stamp = page.getByRole('button', {name: 'Passport check, open the evidence'});
  await expect(stamp).toContainText('PARTIAL');
  await expect(stamp).toContainText('1 observed · 0 inferred · 6 declared');
  await expect(page.locator('.passport').getByText('VERIFIED', {exact: true})).toHaveCount(0);
  await stamp.click();
  await expect(page.getByRole('dialog').getByText('not an overall protection verdict', {exact: false})).toBeVisible();
  await expect(page.getByRole('dialog').getByText('Image admission · DECLARED', {exact: true})).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(stamp).toBeFocused();
  await page.screenshot({path: info.outputPath('ops-partial-passport.png')});
});

test('Map counts observations rather than protected agents and keeps inference separate', async ({page}) => {
  await open(page, {hash: '#/map'});
  const items = Object.entries(data.endpoints).filter(([path]) => path.startsWith('/api/console/onboarding/')).flatMap(([, onb]) => onb.guarantees);
  const observed = items.filter(g => g.state === 'verified' && g.basis === 'observed').length;
  await expect(page.locator('.stats')).toContainText('checks observed');
  await expect(page.locator('.stats')).toContainText(observed + ' / ' + items.length);
  await expect(page.getByText('protected', {exact: true})).toHaveCount(0);
  await expect(page.getByRole('link', {name: /Financial.*observed.*inferred.*declared/})).toBeVisible();
});

test('an image row is labelled INFERRED before its drawer opens', async ({page}) => {
  await open(page);
  await expect(page.locator('.stamp')).toContainText('3 observed · 1 inferred · 4 declared');
  await page.getByRole('link', {name: 'Review onboarding →', exact: true}).click();
  const row = page.getByRole('button', {name: 'Image admission', exact: true}).locator('..');
  await expect(row.getByText('Inferred', {exact: true})).toBeVisible();
  await expect(row.getByText('Observed', {exact: true})).toHaveCount(0);
  await row.getByRole('button').click();
  const drawer = page.getByRole('dialog');
  await expect(drawer.getByText('EXPLAIN · INFERRED', {exact: true})).toBeVisible();
  await expect(drawer.getByText('not a direct observation or a cryptographic signature check.', {exact: false})).toBeVisible();
  await expect(drawer.getByText('demo-check verifies image signatures', {exact: false})).toBeVisible();
});

test('Financial rows use the declared broker boundary, with no credential in the worker', async ({page}) => {
  await open(page);
  const rows = page.getByRole('button', {name: 'Read-only rows through the data broker — declared', exact: true});
  await expect(rows.getByText('DECLARED', {exact: true})).toBeVisible();
  await rows.click();
  const drawer = page.getByRole('dialog');
  await expect(drawer.getByText('workers have no database credential.', {exact: false})).toBeVisible();
  await expect(drawer.getByText('does not independently exercise this boundary.', {exact: false})).toBeVisible();
});

test('Ops declares its approval executor and never claims an observed execution', async ({page}) => {
  await open(page, {hash: '#/agents/ops-agent'});
  await expect(page.getByRole('button', {name: /Propose a restart to the approval executor/})).toBeVisible();
  await page.getByRole('button', {name: 'Changes require the separate approval executor — declared', exact: true}).click();
  await expect(page.getByRole('dialog').getByText('EXPLAIN · DECLARED', {exact: true})).toBeVisible();
  await expect(page.getByRole('dialog').getByText('Ops observes and proposes; it has no workload mutation authority.', {exact: false})).toBeVisible();
});

test('a failed observation is named and dominates the passport summary', async ({page}) => {
  await open(page, {change: (path, body) => {
    if (path !== '/api/console/onboarding/financial') return;
    const network = body.guarantees.find(g => g.id === 'network');
    Object.assign(network, {state: 'failing', basis: 'observed', detail: 'No default-deny policy observed'});
  }});
  await expect(page.locator('.stamp')).toContainText('FAILING');
  await expect(page.getByRole('alert')).toContainText('Default-deny network');
  await page.getByRole('button', {name: 'No internet access — failing', exact: true}).click();
  await expect(page.getByRole('dialog').getByText('EXPLAIN · FAILING', {exact: true})).toBeVisible();
});

test('all declarations remain declarations when observations are unavailable', async ({page}) => {
  await open(page, {change: (path, body) => {
    if (!path.startsWith('/api/console/onboarding/')) return;
    for (const g of body.guarantees) Object.assign(g, {state: 'declared', basis: 'manifest'});
  }});
  await expect(page.locator('.stamp')).toContainText('DECLARED');
  await expect(page.locator('.stamp')).toContainText('0 observed · 0 inferred · 8 declared');
  await expect(page.locator('.passport').getByText('VERIFIED', {exact: true})).toHaveCount(0);
});

test('unavailable onboarding does not fabricate counts, evidence or a stamp', async ({page}) => {
  await open(page, {unavailable: '/api/console/onboarding/financial'});
  await expect(page.locator('.stamp')).toHaveCount(0);
  await expect(page.getByRole('button', {name: 'See the evidence', exact: true})).toBeDisabled();
  await page.getByRole('link', {name: 'Review onboarding →'}).click();
  await expect(page.getByText('Checks are unavailable. No verdict is inferred.', {exact: true})).toBeVisible();
});

test('Onboard is a read-only review with a clearly labelled summary and owner workflow', async ({page}, info) => {
  const requests = [];
  await open(page, {hash: '#/onboard/financial', requests});
  await expect(page.getByText('Read-only review. No deployment or keys are created here.', {exact: true})).toBeVisible();
  await expect(page.getByText('This summary is not an applicable YAML file.', {exact: false})).toBeVisible();
  await expect(page.getByRole('region', {name: 'Manifest summary'}).locator('pre')).toHaveCount(0);
  await expect(page.getByRole('group', {name: 'Agent'}).getByRole('button')).toHaveCount(2);
  await page.getByRole('button', {name: 'Owner workflow →'}).click();
  const drawer = page.getByRole('dialog');
  await expect(drawer.getByText('make onboard-check F=platform/agents/<name>/agent.yaml', {exact: true})).toBeVisible();
  await expect(drawer.getByText('make onboard A=<name>', {exact: true})).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByRole('button', {name: 'Refresh observations'}).click();
  await expect(page.getByRole('button', {name: 'Refresh observations'})).toBeEnabled();
  expect(requests.every(r => r.method === 'GET')).toBe(true);
  await page.screenshot({path: info.outputPath('onboard-review.png')});
});

test('the rejected example shows the shipped file and a nonzero expected outcome', async ({page}) => {
  await open(page, {hash: '#/onboard/financial'});
  await page.getByRole('button', {name: 'See example →'}).click();
  const drawer = page.getByRole('dialog');
  await expect(drawer.getByRole('heading', {name: 'Expected rejection'})).toBeVisible();
  await expect(drawer.getByText('Nonzero exit status.', {exact: false})).toBeVisible();
  await expect(drawer.getByText('make onboard-check F=docs/examples/rejected-agent/agent.yaml', {exact: true})).toBeVisible();
  await expect(drawer.locator('pre').filter({hasText: 'agent: spend-bot'})).toHaveText(data.endpoints['/api/console/example'].text);
});

test('example unavailability remains explicit', async ({page}) => {
  await open(page, {hash: '#/onboard/financial', unavailable: '/api/console/example'});
  await page.getByRole('button', {name: 'See example →'}).click();
  await expect(page.getByRole('dialog').getByText('The example file is not available here.', {exact: true})).toBeVisible();
});

test('refresh retrieves current observations without creating a deployment', async ({page}) => {
  let update = false;
  const requests = [];
  await open(page, {hash: '#/onboard/financial', requests, change: (path, body) => {
    if (update && path === '/api/console/onboarding/financial') {
      Object.assign(body.guarantees.find(g => g.id === 'network'), {state: 'failing', basis: 'observed', detail: 'Current policy missing'});
    }
  }});
  update = true;
  await page.getByRole('button', {name: 'Refresh observations'}).click();
  await expect(page.getByRole('region', {name: 'Check observations'})).toContainText('1 failing');
  expect(requests.every(r => r.method === 'GET')).toBe(true);
});

test('all onboarding rows open their own evidence with keyboard focus restored', async ({page}) => {
  await open(page, {hash: '#/onboard/financial'});
  const rows = page.getByRole('region', {name: 'Check observations'}).getByRole('button');
  await expect(rows).toHaveCount(data.endpoints['/api/console/onboarding/financial'].guarantees.length);
  for (let i = 0; i < await rows.count(); i++) {
    const row = rows.nth(i), title = await row.textContent();
    await row.focus(); await page.keyboard.press('Enter');
    await expect(page.getByRole('dialog').getByRole('heading', {name: title, exact: true})).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(row).toBeFocused();
  }
});

test('a late example response cannot open a drawer on another screen', async ({page}) => {
  await open(page, {hash: '#/onboard/financial'});
  let release, seen;
  const observed = new Promise(resolve => { seen = resolve; });
  const held = new Promise(resolve => { release = resolve; });
  await page.route('**/api/console/example', async route => { seen(); await held; await route.fulfill({json: data.endpoints['/api/console/example']}); });
  await page.getByRole('button', {name: 'See example →'}).click(); await observed;
  await page.getByRole('link', {name: 'Agents', exact: true}).click();
  release();
  await expect(page.locator('.passport')).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('Try links reach the current Financial and Guide assets and Financial returns to its passport', async ({page, context}) => {
  context.on('page', child => child.on('pageerror', error => errors.push(error.message)));
  // Offline forward simulation: real assets at the exact supported loopback URLs, synthetic APIs, no cluster.
  await context.route(/^http:\/\/127\.0\.0\.1:808[012]\//, async route => {
    const url = new URL(route.request().url());
    if (url.port === '8081' && url.pathname === '/api/me') return route.fulfill({json: data.profile});
    if (url.port === '8080' && url.pathname.startsWith('/api/console/')) {
      return route.fulfill({json: data.endpoints[url.pathname + url.search] || {available: false}});
    }
    const asset = url.port === '8081' ? financial : url.port === '8082' ? guide : consoleAssets;
    const response = await route.fetch({url: asset.origin + url.pathname});
    return route.fulfill({response});
  });
  await open(page);
  await expect(page.getByText('Needs: make agent-forward A=financial · 127.0.0.1:8081', {exact: true})).toBeVisible();
  const popupPromise = page.waitForEvent('popup');
  await page.getByRole('link', {name: 'Try this agent →', exact: true}).click();
  const popup = await popupPromise;
  await expect(popup.getByRole('button', {name: 'Send', exact: true})).toBeVisible();
  await expect(popup).toHaveURL('http://127.0.0.1:8081/');
  await popup.getByRole('link', {name: /passport/i}).click();
  await expect(popup).toHaveURL('http://127.0.0.1:8080/#/agents/financial');
  await expect(popup.locator('.passport')).toBeVisible();
  await popup.close();
  await page.locator('.rail button').filter({hasText: 'Platform Guide'}).click();
  await expect(page.getByText('Needs: make agent-forward A=platform-guide · 127.0.0.1:8082', {exact: true})).toBeVisible();
  const guidePromise = page.waitForEvent('popup');
  await page.getByRole('link', {name: 'Try this agent →'}).click();
  const guidePage = await guidePromise;
  await expect(guidePage).toHaveURL('http://127.0.0.1:8082/');
  await expect(guidePage.locator('#q')).toBeVisible();
  await guidePage.close();
});

test('passport and review remain readable at 360px without horizontal overflow', async ({page}) => {
  await page.setViewportSize({width: 360, height: 900});
  await open(page);
  await expect(page.locator('.stamp')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('link', {name: 'Review onboarding →'}).click();
  await expect(page.getByRole('region', {name: 'Manifest summary'})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});


test('a pending refresh disables duplicate clicks and cannot overwrite a later selection', async ({page}) => {
  await open(page, {hash: '#/onboard/financial'});
  let release, seen, count = 0;
  const observed = new Promise(resolve => { seen = resolve; });
  const held = new Promise(resolve => { release = resolve; });
  await page.route('**/api/console/onboarding/financial', async route => {
    if (++count === 1) { seen(); await held; }
    await route.fulfill({json: data.endpoints['/api/console/onboarding/financial']});
  });
  const refresh = page.getByRole('button', {name: 'Refresh observations'});
  await refresh.click(); await observed;
  await expect(refresh).toBeDisabled();
  await page.getByRole('group', {name: 'Agent'}).getByRole('button', {name: 'Platform Guide', exact: true}).click();
  const table = page.getByRole('table', {name: 'Manifest facts'});
  await expect(table.getByRole('cell', {name: 'platform-guide', exact: true})).toBeVisible();
  await expect(refresh).toBeEnabled();
  const oldResponse = page.waitForResponse(response => response.url().endsWith('/onboarding/financial'));
  release(); await oldResponse;
  await expect(table.getByRole('cell', {name: 'platform-guide', exact: true})).toBeVisible();
});
