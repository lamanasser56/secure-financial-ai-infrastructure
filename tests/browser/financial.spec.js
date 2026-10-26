import {test, expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {assets} from './server.js';

const here = dirname(fileURLToPath(import.meta.url));
const data = JSON.parse(execFileSync(process.env.PYTHON || 'python3', [join(here, 'presentation_payloads.py')], {encoding: 'utf8'}));
let server, errors;
test.use({reducedMotion: 'reduce'});
test.beforeAll(async () => { server = await assets('platform/agents/financial/finance_agent/ui'); });
test.afterAll(async () => { await server.close(); });
test.beforeEach(({page}) => { errors = []; page.on('pageerror', error => errors.push(error.message)); });
test.afterEach(() => { expect(errors).toEqual([]); });

async function open(page, {signedIn = true, profile = data.profile, handle = () => false} = {}) {
  const requests = [];
  await page.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url());
    requests.push({path: url.pathname, search: url.search, method: request.method(), body: request.postDataJSON()});
    if (await handle(route, url, requests)) return;
    if (url.pathname === '/api/me') return route.fulfill({status: signedIn ? 200 : 401, json: signedIn ? profile : {error: 'sign_in_required'}});
    if (url.pathname === '/api/login') return route.fulfill({json: profile});
    if (url.pathname === '/api/logout') return route.fulfill({json: {signed_out: true}});
    if (url.pathname === '/api/expenses') return route.fulfill({json: request.method() === 'GET' ? {month: url.searchParams.get('month'), expenses: []} : {id: 42}});
    if (url.pathname === '/api/ask') return route.fulfill({json: data.reply});
    return route.fulfill({status: 404, json: {error: 'not_found'}});
  });
  await page.goto(server.origin + '/');
  await expect(page.getByRole('button', {name: signedIn ? 'Send' : 'Sign in', exact: true})).toBeVisible();
  return requests;
}
async function arabic(page) { await page.getByLabel('Language', {exact: true}).selectOption('ar'); }
async function ask(page, text = 'Synthetic question') {
  await page.locator('#q').fill(text); await page.locator('form.send button').click();
}
async function expense(page, ar = false) {
  await page.getByRole('link', {name: ar ? 'المصروفات' : 'Expenses', exact: true}).click();
  await page.locator('#f-spent_on').fill('2026-10-03');
  await page.locator('#f-merchant').fill(ar ? 'متجر اختبار' : 'Synthetic store');
  await page.locator('#f-amount').fill('24.50');
}

test('Arabic covers sign-in, errors, scope, trace drawers and expense form with real Arabic fonts', async ({page}, info) => {
  const answer = 'مصروف الاختبار: 15.00 ر.س.';
  const requests = await open(page, {signedIn: false, handle: async (route, url) => {
    if (url.pathname !== '/api/ask') return false;
    await route.fulfill({json: {...data.reply, answer}}); return true;
  }});
  await arabic(page);
  await expect(page.locator('html')).toHaveAttribute('lang', 'ar');
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.getByRole('heading', {name: 'سجّل الدخول.'})).toBeVisible();
  await expect(page.getByText('قيود الدخول المؤقتة', {exact: false})).toBeVisible();
  await page.getByLabel('اسم المستخدم', {exact: true}).fill('demo');
  await page.getByLabel('كلمة المرور', {exact: true}).fill('offline-only');
  await page.getByRole('button', {name: 'دخول', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'اسأل. راجع الأثر.'})).toBeVisible();
  await page.getByRole('button', {name: 'نطاق الإخفاء ←', exact: true}).click();
  const drawer = page.getByRole('dialog');
  await expect(drawer.getByText('لا تُخفى أسماء الأشخاص ولا أرقام جوازات السفر.', {exact: false})).toBeVisible();
  for (const row of data.profile.masking_scope_ar.supported) await expect(drawer.getByText(row.code, {exact: true})).toBeVisible();
  await expect(drawer.getByRole('button', {name: 'إغلاق', exact: true})).toBeVisible();
  await expect(drawer.getByText('نسخة المصدر غير متاحة', {exact: true})).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', {name: 'نطاق الإخفاء ←', exact: true})).toBeFocused();
  await ask(page, 'كم أنفقت؟');
  await expect(page.locator('.msgbox.bot')).toHaveText(answer);
  expect(requests.find(row => row.path === '/api/ask').body.language).toBe('ar');
  for (const label of ['مرجع هوية أبلغ عنه العامل', 'إخفاء معرّفات أبلغ عنه العامل', 'قراءات مقيّدة أبلغ عنها العامل', 'فحص استناد أبلغ عنه العامل']) {
    await page.getByRole('button', {name: label + ' — التفاصيل', exact: true}).click();
    await expect(drawer.getByText('ليست', {exact: false}).or(drawer.getByText('ليس', {exact: false})).first()).toBeVisible();
    await page.keyboard.press('Escape');
  }
  await page.getByRole('button', {name: 'أثر الطلب ←', exact: true}).click();
  await expect(drawer.getByRole('button', {name: 'انسخ القيمة الكاملة: الطلب', exact: true})).toBeVisible();
  await expect(drawer.getByText('لا يثبت هذا الأثر اكتمال التسجيل', {exact: false})).toBeVisible();
  await page.keyboard.press('Escape');
  await page.evaluate(() => document.fonts.ready);
  expect(await page.evaluate(() => document.fonts.check('400 16px "IBM Plex Sans Arabic"', 'مصروفاتك'))).toBe(true);
  expect(await page.locator('.bar').evaluate(node => node.getBoundingClientRect().top)).toBeGreaterThanOrEqual(0);
  expect(await page.locator('.send').evaluate(node => node.getBoundingClientRect().bottom)).toBeLessThanOrEqual(900);
  expect(await page.locator('.did footer').evaluate(node => node.getBoundingClientRect().bottom)).toBeLessThanOrEqual(900);
  await page.screenshot({path: info.outputPath('financial-arabic-ask.png')});
  await expense(page, true);
  await expect(page.getByLabel('الفئة', {exact: true}).locator('option')).toHaveText(data.profile.schema.categories.map(row => row.labels.ar));
  await page.getByRole('button', {name: 'إضافة', exact: true}).click();
  await expect(page.getByText('أُضيف المصروف.', {exact: true})).toBeVisible();
  await page.screenshot({path: info.outputPath('financial-arabic-expenses.png')});
});

test('Arabic code link and copy button use the actual immutable source and full request value', async ({page, context}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await open(page, {handle: async (route, url) => {
    if (url.pathname !== '/api/me' && url.pathname !== '/api/ask') return false;
    await route.fulfill({json: url.pathname === '/api/me' ? data.profile : data.reply, headers: {'X-Platform-Source-Commit': 'b'.repeat(40)}}); return true;
  }});
  await arabic(page); await ask(page, 'طلب اختبار');
  await page.getByRole('button', {name: 'أثر الطلب ←', exact: true}).click();
  const drawer = page.getByRole('dialog');
  await expect(drawer.getByRole('link', {name: 'عرض الشيفرة ←', exact: true})).toHaveAttribute('href', 'https://github.com/lamanasser56/secure-financial-ai-infrastructure/blob/' + 'b'.repeat(40) + '/platform/agents/financial/finance_agent/agent.py');
  await drawer.getByRole('button', {name: 'انسخ القيمة الكاملة: الطلب', exact: true}).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(data.reply.trace.request_id);
});

test('period and category choices come from metadata, independent of browser date', async ({page}) => {
  const profile = structuredClone(data.profile);
  profile.schema.demo_month = '2031-02';
  profile.schema.categories = [{code: 'other', labels: {en: 'Example category', ar: 'فئة اختبار'}}];
  await page.clock.setFixedTime(new Date('2029-07-31T23:59:59Z'));
  const requests = await open(page, {profile});
  for (const text of await page.locator('.chips button').allTextContents()) expect(text).toContain('February 2031');
  await page.getByRole('link', {name: 'Expenses', exact: true}).click();
  await expect(page.locator('#month')).toHaveValue('2031-02');
  await expect(page.locator('#f-category option')).toHaveText(['Example category']);
  expect(requests.filter(row => row.path === '/api/expenses')[0].search).toBe('?month=2031-02');
});

test('missing metadata disables category guessing but still allows a typed question', async ({page}) => {
  const profile = structuredClone(data.profile); delete profile.schema;
  await open(page, {profile});
  await expect(page.locator('.chips button')).toHaveCount(0);
  await page.getByRole('link', {name: 'Expenses', exact: true}).click();
  await expect(page.getByText('Form metadata unavailable.', {exact: true})).toBeVisible();
  await expect(page.locator('.addform')).toHaveCount(0);
  await page.getByRole('link', {name: 'Ask', exact: true}).click();
  await ask(page); await expect(page.locator('.msgbox.bot')).toBeVisible();
});

test('one pending turn disables every submit path and survives navigation and language changes', async ({page}) => {
  let pending;
  const requests = await open(page, {handle: route => {
    if (new URL(route.request().url()).pathname !== '/api/ask') return false;
    pending = route; return true;
  }});
  await page.locator('.chips button').first().click();
  await expect(page.locator('form.send button')).toBeDisabled();
  for (const button of await page.locator('.chips button').all()) await expect(button).toBeDisabled();
  await expect(page.locator('#logout')).toBeDisabled();
  await page.locator('#q').fill('Next draft');
  await page.getByRole('link', {name: 'Expenses', exact: true}).click();
  await page.getByRole('link', {name: 'Ask', exact: true}).click();
  await expect(page.locator('.msgbox.me')).toHaveCount(1);
  await expect(page.locator('#q')).toHaveValue('Next draft');
  await arabic(page);
  await expect(page.locator('form.send button')).toBeDisabled();
  await pending.fulfill({json: data.reply});
  await expect(page.locator('.msgbox.bot')).toContainText(data.reply.answer);
  await expect(page.getByRole('button', {name: 'إرسال', exact: true})).toBeEnabled();
  expect(requests.filter(row => row.path === '/api/ask')).toHaveLength(1);
  expect(await page.evaluate(() => ({local: localStorage.length, session: sessionStorage.length}))).toEqual({local: 0, session: 0});
});

test('the visible conversation and current trace remain across Expenses and Ask', async ({page}) => {
  await open(page); await ask(page, 'Keep this visible');
  await expect(page.locator('.msgbox.bot')).toBeVisible();
  await page.getByRole('link', {name: 'Expenses', exact: true}).click();
  await page.getByRole('link', {name: 'Ask', exact: true}).click();
  await expect(page.locator('.msgbox.me')).toHaveText('Keep this visible');
  await expect(page.locator('.msgbox.bot')).toHaveText(data.reply.answer);
  await expect(page.getByRole('button', {name: 'Request trace →', exact: true})).toBeVisible();
});

for (const failure of ['worker_unavailable', 'network', 'bad-json', 'bad-trace']) {
  test(failure + ' clears the previous turn trace without delayed stale rows', async ({page}) => {
    let turn = 0;
    await open(page, {handle: async (route, url) => {
      if (url.pathname !== '/api/ask' || ++turn === 1) return false;
      if (failure === 'network') await route.abort();
      else if (failure === 'bad-json') await route.fulfill({body: '{', contentType: 'application/json'});
      else if (failure === 'bad-trace') await route.fulfill({json: {...data.reply, trace: {model: null}}});
      else await route.fulfill({json: {status: 'blocked', reason: failure}});
      return true;
    }});
    await ask(page); await expect(page.getByRole('button', {name: 'Request trace →', exact: true})).toBeVisible();
    await ask(page, 'Second request');
    await expect(page.getByText('No trace returned for this request.', {exact: true})).toBeVisible();
    await expect(page.getByRole('button', {name: 'Request trace →', exact: true})).toHaveCount(0);
    if (failure === 'worker_unavailable') await expect(page.getByRole('alert')).toContainText('worker did not return an answer');
  });
}

for (const failure of ['network', 'refused', 'wrong-shape']) {
  test('sign-out ' + failure + ' keeps the session visible until confirmation', async ({page}) => {
    let attempt = 0;
    await open(page, {handle: async (route, url) => {
      if (url.pathname !== '/api/logout' || ++attempt > 1) return false;
      if (failure === 'network') await route.abort();
      else await route.fulfill({status: failure === 'refused' ? 403 : 200, json: failure === 'refused' ? {error: 'csrf_rejected'} : {signed_out: false}});
      return true;
    }});
    await ask(page); await expect(page.locator('.msgbox.bot')).toBeVisible();
    await page.getByRole('button', {name: 'Sign out', exact: true}).click();
    await expect(page.getByText('Sign-out was not confirmed.', {exact: false})).toBeVisible();
    await expect(page.locator('.msgbox.bot')).toBeVisible();
    await page.getByRole('button', {name: 'Sign out', exact: true}).click();
    await expect(page.getByRole('heading', {name: 'Sign in.', exact: true})).toBeVisible();
  });
}

for (const endpoint of ['/api/ask', '/api/expenses-write', '/api/expenses-read']) {
  test('401 from ' + endpoint + ' consistently clears private page state', async ({page}) => {
    await open(page, {handle: async (route, url) => {
      const method = route.request().method();
      if (url.pathname !== endpoint.replace(/-write|-read/g, '') || (endpoint.endsWith('-write') && method !== 'POST') || (endpoint.endsWith('-read') && method !== 'GET')) return false;
      await route.fulfill({status: 401, json: {error: 'sign_in_required'}}); return true;
    }});
    if (endpoint === '/api/ask') await ask(page);
    else if (endpoint.endsWith('-read')) await page.getByRole('link', {name: 'Expenses', exact: true}).click();
    else { await expense(page); await page.getByRole('button', {name: 'Add', exact: true}).click(); }
    await expect(page.getByRole('heading', {name: 'Sign in.', exact: true})).toBeVisible();
    await expect(page.getByRole('alert')).toContainText('Your session ended');
    await expect(page.locator('.msgbox')).toHaveCount(0);
  });
}

test('expense submission cannot duplicate while pending, including after navigation', async ({page}) => {
  let pending;
  const requests = await open(page, {handle: (route, url) => {
    if (url.pathname !== '/api/expenses' || route.request().method() !== 'POST') return false;
    pending = route; return true;
  }});
  await expense(page); await page.getByRole('button', {name: 'Add', exact: true}).click();
  await expect(page.locator('.addform button')).toBeDisabled();
  await expect(page.locator('#logout')).toBeDisabled();
  await page.getByRole('link', {name: 'Ask', exact: true}).click();
  await page.getByRole('link', {name: 'Expenses', exact: true}).click();
  await expect(page.locator('.addform button')).toBeDisabled();
  await expect(page.locator('#f-merchant')).toHaveValue('Synthetic store');
  await pending.fulfill({status: 201, json: {id: 123}});
  await expect(page.getByText('Expense added.', {exact: true})).toBeVisible();
  await expect(page.getByRole('button', {name: 'Add', exact: true})).toBeEnabled();
  await expect(page.locator('#f-merchant')).toHaveValue('');
  expect(requests.filter(row => row.path === '/api/expenses' && row.method === 'POST')).toHaveLength(1);
});

for (const failure of ['network', 'bad-json', 'validation']) {
  test('Arabic expense ' + failure + ' preserves the draft and explains the outcome', async ({page}) => {
    await open(page, {handle: async (route, url) => {
      if (url.pathname !== '/api/expenses' || route.request().method() !== 'POST') return false;
      if (failure === 'network') await route.abort();
      else if (failure === 'bad-json') await route.fulfill({body: '{', contentType: 'application/json'});
      else await route.fulfill({status: 400, json: {error: 'category must be one of ...'}});
      return true;
    }});
    await arabic(page); await expense(page, true); await page.getByRole('button', {name: 'إضافة', exact: true}).click();
    await expect(page.getByRole('status').filter({hasText: failure === 'validation' ? 'راجع التاريخ والفئة' : 'نتيجة الحفظ غير معروفة'})).toBeVisible();
    await expect(page.locator('#f-merchant')).toHaveValue('متجر اختبار');
    await expect(page.getByText('أُضيف المصروف.', {exact: true})).toHaveCount(0);
  });
}

test('a late month response cannot replace the current month', async ({page}) => {
  let pending;
  await open(page, {handle: (route, url) => {
    if (url.pathname !== '/api/expenses' || url.searchParams.get('month') !== data.profile.schema.demo_month) return false;
    pending = route; return true;
  }});
  await page.getByRole('link', {name: 'Expenses', exact: true}).click();
  await expect.poll(() => Boolean(pending)).toBe(true);
  await page.locator('#month').fill('2026-09');
  await page.locator('#month').dispatchEvent('change');
  await expect(page.getByText('No expenses in this month yet.', {exact: true})).toBeVisible();
  await pending.fulfill({json: {month: data.profile.schema.demo_month, expenses: [{id: 1, date: '2026-10-01', merchant: 'Stale row', category: 'food', amount_minor: 1}]}});
  await expect(page.getByText('Stale row', {exact: true})).toHaveCount(0);
});

for (const code of ['wrong_username_or_password', 'too_many_attempts', 'unreachable']) {
  test('Arabic login ' + code + ' is translated and password clears on submission', async ({page}) => {
    await open(page, {signedIn: false, handle: async (route, url) => {
      if (url.pathname !== '/api/login') return false;
      if (code === 'unreachable') await route.abort(); else await route.fulfill({status: 401, json: {error: code}});
      return true;
    }});
    await arabic(page);
    await page.getByLabel('اسم المستخدم', {exact: true}).fill('demo');
    await page.getByLabel('كلمة المرور', {exact: true}).fill('do-not-retain');
    await page.getByRole('button', {name: 'دخول', exact: true}).click();
    await expect(page.getByRole('alert')).not.toBeEmpty();
    await expect(page.getByLabel('كلمة المرور', {exact: true})).toHaveValue('');
    expect(await page.getByRole('alert').innerText()).toMatch(/[ء-ي]/);
    if (code === 'too_many_attempts') await expect(page.getByRole('alert')).toContainText('ذاكرة');
  });
}

for (const code of ['rate_limited', 'token_budget_exhausted', 'worker_unavailable']) {
  test('Arabic refusal ' + code + ' describes its actual scope', async ({page}) => {
    await open(page, {handle: async (route, url) => {
      if (url.pathname !== '/api/ask') return false;
      await route.fulfill({json: {status: 'blocked', reason: code}}); return true;
    }});
    await arabic(page); await ask(page, 'سؤال اختبار');
    await expect(page.getByRole('alert')).toContainText(code === 'worker_unavailable' ? 'لم يُرجع العامل إجابة' : 'ذاكرة');
    await expect(page.getByText('لم يصل أثر لهذا الطلب.', {exact: true})).toBeVisible();
  });
}

for (const width of [360, 1440]) {
  test('Arabic keyboard, drawer and form fit at width ' + width, async ({page}, info) => {
    await page.setViewportSize({width, height: 900});
    await open(page); await arabic(page);
    const scope = page.getByRole('button', {name: 'نطاق الإخفاء ←', exact: true});
    await scope.focus(); await page.keyboard.press('Enter');
    await expect(page.getByRole('button', {name: 'إغلاق', exact: true})).toBeFocused();
    await page.keyboard.press('Escape'); await expect(scope).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expense(page, true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path: info.outputPath('financial-arabic-' + width + '.png'), fullPage: true});
  });
}
