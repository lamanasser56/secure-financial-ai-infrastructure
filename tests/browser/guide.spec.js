import {test, expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {assets} from './server.js';

const here = dirname(fileURLToPath(import.meta.url));
const data = JSON.parse(execFileSync(process.execPath, [join(here, 'guide_payloads.cjs')], {encoding: 'utf8'}));
let server, errors;
test.use({reducedMotion: 'reduce'});
test.beforeAll(async () => { server = await assets('platform/agents/platform-guide/public'); });
test.afterAll(async () => { await server.close(); });
test.beforeEach(({page}) => { errors = []; page.on('pageerror', error => errors.push(error.message)); });
test.afterEach(() => { expect(errors).toEqual([]); });

async function open(page, ar = false, handle = async () => false) {
  const calls = [];
  await page.route('**/api/**', async route => {
    const name = new URL(route.request().url()).pathname;
    if (await handle(route, name)) return;
    if (name === '/api/info') return route.fulfill({json: data.info});
    calls.push(route.request().postDataJSON());
    return route.fulfill({json: calls.at(-1).language === 'ar' ? data.ar : data.en});
  });
  await page.goto(server.origin);
  await expect(page.locator('#connection')).toHaveText('API answered');
  if (ar) await page.getByLabel('Language', {exact: true}).selectOption('ar');
  return calls;
}
async function ask(page, ar = false) {
  await page.locator('#q').fill(ar ? 'ما الذي تخفيه بوابة النموذج؟' : 'What does the Model gateway mask?');
  await page.locator('#send').click();
}

for (const ar of [false, true]) {
  const suffix = ar ? 'Arabic' : 'English';
  test('complete language, direction, current sources and worker drawer in ' + suffix, async ({page}, info) => {
    const calls = await open(page, ar);
    await expect(page.locator('html')).toHaveAttribute('lang', ar ? 'ar' : 'en');
    await expect(page.locator('html')).toHaveAttribute('dir', ar ? 'rtl' : 'ltr');
    await expect(page.getByRole('heading', {level: 1})).toHaveText(ar ? 'دليل المنصة' : 'Platform Guide');
    await expect(page.locator('#passport')).toHaveText(ar ? 'جواز الوكيل' : 'Agent passport');
    if (ar) expect(await page.locator('body').evaluate(node => getComputedStyle(node).fontFamily)).toContain('IBM Plex Sans Arabic');
    await ask(page, ar);
    expect(calls).toEqual([{question: ar ? 'ما الذي تخفيه بوابة النموذج؟' : 'What does the Model gateway mask?', language: ar ? 'ar' : 'en'}]);
    const reply = ar ? data.ar : data.en;
    // Excerpts render from Markdown: the visible text is the excerpt without its markers.
    const plain = text => text.replace(/^```.*$/gm, '').replace(/^\s*(?:[-*]|\d+[.)])\s+/gm, '').replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/`([^`]+)`/g, '$1').replace(/\[([^\]]+)\]\([^)\s]+\)/g, '$1');
    await expect(page.locator('#result .guide-excerpt')).toHaveText(reply.sources.map(source => plain(source.excerpt)));
    if (reply.sources.some(source => /\*\*[^*]+\*\*/.test(source.excerpt))) await expect(page.locator('#result .guide-excerpt strong').first()).toBeVisible();
    await expect(page.locator('.guide-excerpt').first()).toHaveAttribute('lang', ar ? 'ar' : 'en');
    expect(await page.locator('#result').innerText()).not.toContain('grounded');
    expect(await page.locator('main pre').count()).toBe(0);
    const source = page.locator('.guide-sources button').first();
    await source.click();
    await expect(page.locator('#explain')).toBeVisible();
    await expect(page.locator('#explain')).toContainText(reply.sources[0].excerpt_sha256);
    await expect(page.locator('#explain')).toContainText(ar ? 'ليست تحققًا تشفيريًا' : 'not cryptographic verification');
    const link = page.getByRole('link', {name: ar ? 'فتح نسخة المصدر ←' : 'Open this source revision →', exact: true});
    await expect(link).toHaveAttribute('href', 'https://github.com/lamanasser56/secure-financial-ai-infrastructure/blob/' + reply.source_commit + '/' + reply.sources[0].path);
    await expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    await page.keyboard.press('Escape'); await expect(source).toBeFocused();
    const trace = page.getByRole('button', {name: ar ? 'فحص أثر الطلب' : 'Inspect request trace', exact: true});
    await trace.click();
    await expect(page.locator('#explain')).toContainText(ar ? 'ليس دليلًا مستقلًا' : 'not independent boundary evidence');
    await page.getByText(ar ? 'فحص الإفادة' : 'Inspect the report', {exact: true}).click();
    await expect(page.locator('#explain pre')).toContainText('source_quotes_verified');
    await page.getByRole('button', {name: ar ? 'إغلاق' : 'Close', exact: true}).click();
    await expect(trace).toBeFocused();
    await page.screenshot({path: info.outputPath('guide-' + suffix + '.png')});
  });

  test('masking explains all eight current types and names/passports and memory limits in ' + suffix, async ({page}) => {
    await open(page, ar);
    await page.locator('#about').click();
    await expect(page.locator('#explain li')).toHaveCount(8);
    for (const type of data.info.masking_types) await expect(page.locator('#explain')).toContainText(type);
    await expect(page.locator('#explain')).toContainText(ar ? 'لا تُخفى أسماء الأشخاص أو أرقام جوازات السفر' : 'Person names and passport numbers are not masked');
    await expect(page.locator('#explain')).toContainText(ar ? 'ليست حصصًا عامة دائمة' : 'not durable global quotas');
    await expect(page.locator('#explain')).toContainText(ar ? 'دون ضمان سجل تدقيق كامل أو دائم' : 'without a promise of complete or durable audit');
  });

  for (const kind of ['refused', 'blocked']) {
    test(kind + ' clears old sources and explains the current outcome in ' + suffix, async ({page}) => {
      let count = 0;
      await open(page, ar, async (route, name) => {
        if (name !== '/api/ask' || ++count === 1) return false;
        await route.fulfill({json: data[kind]}); return true;
      });
      await ask(page, ar); await expect(page.locator('.guide-sources button')).toHaveCount(data[ar ? 'ar' : 'en'].sources.length);
      await ask(page, ar);
      await expect(page.locator('#result')).toContainText(kind === 'refused'
        ? ar ? 'لا تغطي الوثائق المتاحة هذا السؤال' : 'does not cover this question'
        : ar ? 'نصًا غير مسند' : 'unsupported text');
      await expect(page.locator('.guide-sources button')).toHaveCount(0);
      await expect(page.locator('.guide-excerpt')).toHaveCount(0);
      await expect(page.locator('#q')).not.toHaveValue('');
    });
  }
}

test('one pending turn disables duplicate sends and clears the previous result/trace until completion', async ({page}) => {
  let finish, count = 0;
  await open(page, false, async (route, name) => {
    if (name !== '/api/ask' || ++count === 1) return false;
    await new Promise(resolve => { finish = resolve; }); await route.fulfill({json: data.en}); return true;
  });
  await ask(page); await expect(page.locator('.guide-excerpt')).toBeVisible();
  await ask(page);
  await expect(page.locator('#ask')).toHaveAttribute('aria-busy', 'true');
  await expect(page.locator('#send')).toBeDisabled(); await expect(page.locator('#lang')).toBeDisabled();
  await expect(page.locator('#q')).toBeDisabled();
  await expect(page.locator('#examples button').first()).toBeDisabled();
  await expect(page.locator('.guide-excerpt')).toHaveCount(0);
  await expect(page.getByRole('button', {name: 'Inspect request trace', exact: true})).toHaveCount(0);
  await page.locator('#ask').evaluate(form => form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true})));
  expect(count).toBe(2);
  finish();
  await expect(page.locator('#send')).toBeEnabled(); await expect(page.locator('.guide-excerpt')).toBeVisible();
});

for (const ar of [false, true]) {
  for (const kind of ['network', 'json', 'scalar', 'http', 'contract']) {
    test('visible ' + kind + ' failure preserves the draft and recovers in ' + (ar ? 'Arabic' : 'English'), async ({page}) => {
      let count = 0;
      await open(page, ar, async (route, name) => {
        if (name !== '/api/ask' || ++count > 1) return false;
        if (kind === 'network') await route.abort();
        else if (kind === 'json') await route.fulfill({body: '{', contentType: 'application/json'});
        else if (kind === 'scalar') await route.fulfill({json: 'invalid'});
        else if (kind === 'http') await route.fulfill({status: 503, json: {error: 'down'}});
        else await route.fulfill({json: {...data.en, answer: 'Invented text'}});
        return true;
      });
      await ask(page, ar);
      await expect(page.locator('#result [role=alert]')).toBeVisible();
      await expect(page.locator('#q')).not.toHaveValue('');
      await expect(page.locator('#send')).toBeEnabled();
      await expect(page.locator('.guide-excerpt')).toHaveCount(0);
      if (ar) await expect(page.locator('#result')).toContainText('احتُفظ بسؤالك');
      await page.locator('#send').click(); await expect(page.locator('.guide-excerpt')).toBeVisible();
      await expect(page.locator('#connection')).toHaveText(ar ? 'استجاب الخادم' : 'API answered');
    });
  }
}

test('timeout is explicit, preserves the question and does not replay the request automatically', async ({page}) => {
  await page.clock.install(); let count = 0;
  await open(page, false, async (route, name) => {
    if (name !== '/api/ask') return false;
    count++; await new Promise(resolve => setTimeout(resolve, 250)); await route.abort(); return true;
  });
  // Stall the transport in the page; advancing its clock must abort that single fetch.
  await page.route('**/api/ask', async route => { count++; await new Promise(resolve => setTimeout(resolve, 1000)); await route.abort(); });
  await page.locator('#q').fill('What does the Model gateway mask?'); await page.locator('#send').click();
  await expect(page.locator('#ask')).toHaveAttribute('aria-busy', 'true');
  await page.clock.fastForward(60001);
  await expect(page.locator('#result')).toContainText('result is unknown');
  await expect(page.locator('#q')).not.toHaveValue('');
  await expect(page.locator('#send')).toBeEnabled(); expect(count).toBe(1);
});

test('metadata failure is visible and retry restores the exact supported type inventory', async ({page}) => {
  let count = 0;
  await page.route('**/api/info', route => ++count === 1 ? route.fulfill({status: 503, json: {error: 'down'}}) : route.fulfill({json: data.info}));
  await page.goto(server.origin);
  await expect(page.locator('#retry-info')).toBeVisible();
  await page.locator('#about').click(); await expect(page.locator('#explain')).toContainText('No coverage is inferred');
  await page.keyboard.press('Escape'); await page.locator('#retry-info').click();
  await expect(page.locator('#retry-info')).toBeHidden(); await page.locator('#about').click();
  await expect(page.locator('#explain li')).toHaveCount(8);
});

test('invalid worker trace does not become evidence and unbound sources do not link to main', async ({page}) => {
  await open(page, false, async (route, name) => {
    if (name !== '/api/ask') return false;
    await route.fulfill({json: {...data.en, source_commit: null, trace: {}}}); return true;
  });
  await ask(page);
  await expect(page.locator('#result')).toContainText('Worker report unavailable');
  await expect(page.getByRole('button', {name: 'Inspect request trace', exact: true})).toHaveCount(0);
  await page.locator('.guide-sources button').first().click();
  await expect(page.locator('#explain')).toContainText('Unbound test corpus');
  await expect(page.locator('#explain a')).toHaveCount(0);
});

test('API strings are plain data and cannot execute markup or supply a foreign source URL', async ({page}) => {
  await open(page, false, async (route, name) => {
    if (name !== '/api/ask') return false;
    const reply = structuredClone(data.en);
    reply.sources[0].excerpt = '<img src=x onerror="window.injected=true">'; reply.answer = reply.sources.map(source => source.excerpt).join('\n\n');
    await route.fulfill({json: reply}); return true;
  });
  await ask(page); await expect(page.locator('.guide-excerpt')).toContainText('<img');
  expect(await page.evaluate(() => window.injected)).toBeUndefined(); await expect(page.locator('#result img')).toHaveCount(0);
  await page.locator('.guide-sources button').first().click(); await expect(page.locator('#explain img')).toHaveCount(0);
});

for (const ar of [false, true]) for (const width of [360, 1440]) {
  test('keyboard, draft, readable sources and layout at ' + width + (ar ? ' Arabic' : ' English'), async ({page}, info) => {
    await page.setViewportSize({width, height: 900});
    await open(page, ar); await ask(page, ar);
    const draft = await page.locator('#q').inputValue();
    await page.locator('.skip').focus(); await page.keyboard.press('Enter'); await expect(page.locator('#view')).toBeFocused();
    await expect(page.locator('#q')).toHaveValue(draft); expect(new URL(page.url()).hash).toBe('');
    await page.locator('#guide-tab').click(); await expect(page.locator('#q')).toHaveValue(draft);
    await page.locator('.guide-sources button').first().focus(); await page.keyboard.press('Enter');
    await expect(page.locator('#explain .close')).toBeFocused(); await page.keyboard.press('Escape');
    await expect(page.locator('.guide-sources button').first()).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (width === 1440) expect(await page.locator('#result').evaluate(node => node.getBoundingClientRect().bottom <= innerHeight)).toBe(true);
    await page.screenshot({path: info.outputPath('guide-' + width + '-' + (ar ? 'ar' : 'en') + '.png')});
  });
}

for (const ar of [false, true]) {
  test('examples, language switches, copy and outside close preserve state ' + (ar ? 'Arabic' : 'English'), async ({page, context}) => {
    const calls = await open(page, ar);
    const examples = page.locator('#examples button');
    await examples.nth(1).click();
    await expect(page.locator('#q')).toHaveValue(ar ? 'من ينفذ التغييرات الموافق عليها؟' : 'Who can execute approved changes?');
    await examples.first().click();
    const draft = await page.locator('#q').inputValue();
    await page.locator('#send').click(); await expect(page.locator('.guide-excerpt')).toBeVisible();
    const excerpt = await page.locator('.guide-excerpt').innerText();
    await page.locator('#lang').selectOption(ar ? 'en' : 'ar');
    await expect(page.locator('#q')).toHaveValue(draft);
    await expect(page.locator('.guide-excerpt')).toHaveText(excerpt);
    expect(calls.length).toBe(1); // Translation never resubmits a question or fabricates a translated source.
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.getByRole('button', {name: ar ? 'Inspect request trace' : 'فحص أثر الطلب', exact: true}).click();
    await page.getByRole('button', {name: ar ? 'Copy the full request' : 'انسخ القيمة الكاملة: الطلب', exact: true}).click();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(data[ar ? 'ar' : 'en'].request_id);
    await page.locator('#scrim').click({position: {x: 5, y: 5}});
    await expect(page.locator('#explain')).toBeHidden();
  });
}

test('a foreign document path cannot become a source link or a displayed answer', async ({page}) => {
  await open(page, false, async (route, name) => {
    if (name !== '/api/ask') return false;
    const reply = structuredClone(data.en); reply.sources[0].path = 'https://evil.example/private';
    await route.fulfill({json: reply}); return true;
  });
  await ask(page);
  await expect(page.locator('#result [role=alert]')).toBeVisible();
  await expect(page.locator('.guide-sources')).toHaveCount(0);
});
