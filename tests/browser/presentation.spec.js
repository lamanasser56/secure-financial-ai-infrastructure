import {test, expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {assets} from './server.js';

const here = dirname(fileURLToPath(import.meta.url));
const data = JSON.parse(execFileSync(process.env.PYTHON || 'python3', [join(here, 'presentation_payloads.py')], {encoding: 'utf8'}));
let financial, consoleAssets;
test.beforeAll(async () => {
  financial = await assets('platform/agents/financial/finance_agent/ui');
  consoleAssets = await assets('platform/core/ui');
});
test.afterAll(async () => { await financial.close(); await consoleAssets.close(); });
test.use({reducedMotion: 'reduce'});

async function finance(page, {change = () => {}, profile = data.profile} = {}) {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/me', route => route.fulfill({json: profile}));
  await page.route('**/api/ask', route => {
    const reply = structuredClone(data.reply); change(reply.trace, reply);
    return route.fulfill({json: reply});
  });
  await page.goto(financial.origin + '/');
  await expect(page.getByRole('button', {name: 'Send', exact: true})).toBeVisible();
  return errors;
}
async function ask(page) {
  await page.getByLabel('Your question', {exact: true}).fill('Synthetic expense question.');
  await page.getByRole('button', {name: 'Send', exact: true}).click();
  await expect(page.getByRole('region', {name: 'Worker request trace'}).getByText('Request trace →', {exact: true})).toBeVisible();
}

test('Financial explains all supported categories and explicitly excludes names and passports before asking', async ({page}) => {
  const errors = await finance(page);
  await page.getByRole('button', {name: 'Masking scope →', exact: true}).click();
  const drawer = page.getByRole('dialog');
  await expect(drawer.getByText(data.profile.masking_scope.summary, {exact: true})).toBeVisible();
  for (const row of data.profile.masking_scope.supported) await expect(drawer.getByText(row.code, {exact: true})).toBeVisible();
  expect(data.profile.masking_scope.supported).toHaveLength(8);
  await expect(drawer.getByText('Matching depends on format and context.', {exact: false})).toBeVisible();
  expect(errors).toEqual([]);
});

test('missing scope metadata cannot invent masking coverage', async ({page}) => {
  const profile = structuredClone(data.profile); delete profile.masking_scope;
  await finance(page, {profile});
  await page.getByRole('button', {name: 'Masking scope →', exact: true}).click();
  await expect(page.getByText('The scope is unavailable. No masking coverage is inferred.')).toBeVisible();
});

test('reported steps and trace never appear as independently verified audit evidence', async ({page}, info) => {
  const errors = await finance(page);
  await ask(page);
  const panel = page.getByRole('region', {name: 'Worker request trace'});
  await expect(panel.getByRole('button', {name: 'Identifier masking reported — details', exact: true})).toBeVisible();
  await expect(panel.getByRole('button', {name: 'Scoped reads reported — details', exact: true})).toBeVisible();
  await expect(panel.getByRole('button', {name: 'Grounding check reported — details', exact: true})).toBeVisible();
  await panel.getByRole('button', {name: 'Scoped reads reported — details'}).click();
  await expect(page.getByRole('dialog').getByText('The trusted data broker checks an active signed capability', {exact: false})).toBeVisible();
  await page.keyboard.press('Escape');
  await panel.getByRole('button', {name: 'Request trace →', exact: true}).click();
  const drawer = page.getByRole('dialog');
  await expect(drawer.getByText('EXPLAIN · WORKER REPORT', {exact: true})).toBeVisible();
  await expect(drawer.getByText('Components emit bounded request events.', {exact: false})).toBeVisible();
  await expect(drawer.getByText('EXPLAIN · VERIFIED LIVE', {exact: true})).toHaveCount(0);
  await page.screenshot({path: info.outputPath('financial-request-trace.png'), animations: 'disabled'});
  expect(errors).toEqual([]);
});

test('redaction calls without findings are reported as checks, not proof that data was hidden', async ({page}) => {
  await finance(page, {change: trace => { trace.redaction.categories = {}; }});
  await ask(page);
  await expect(page.getByRole('button', {name: 'Identifier checks reported — details', exact: true})).toBeVisible();
  await expect(page.getByRole('button', {name: 'Identifier masking reported — details', exact: true})).toHaveCount(0);
});

test('absent redaction and data access do not create reported steps', async ({page}) => {
  await finance(page, {change: trace => { trace.redaction = null; trace.data_access = null; }});
  await ask(page);
  await expect(page.getByRole('button', {name: 'Identifier masking reported — details', exact: true})).toHaveCount(0);
  await expect(page.getByRole('button', {name: 'Scoped reads reported — details', exact: true})).toHaveCount(0);
});

for (const [name, value] of [['null', null], ['missing', undefined], ['string', 'unknown'], ['negative', -1], ['object', {}]]) {
  test('cost ' + name + ' remains unavailable and does not break the trace', async ({page}) => {
    const errors = await finance(page, {change: trace => { trace.cost_usd = value; trace.cost_source = 'litellm_response_header'; }});
    await ask(page);
    const panel = page.getByRole('region', {name: 'Worker request trace'});
    await expect(panel.getByText('cost unavailable', {exact: false})).toBeVisible();
    await expect(panel.getByText('$0.0000', {exact: false})).toHaveCount(0);
    expect(errors).toEqual([]);
  });
}
for (const [value, text] of [[0, '$0.0000'], [0.125, '$0.1250'], [0.000001, '<$0.0001']]) {
  test('valid reported cost ' + value + ' is shown without inventing zero', async ({page}) => {
    await finance(page, {change: trace => { trace.cost_usd = value; trace.cost_source = 'litellm_response_header'; }});
    await ask(page);
    await expect(page.getByRole('region', {name: 'Worker request trace'}).getByText('reported model cost ' + text, {exact: false})).toBeVisible();
  });
}

async function openConsole(page, hash = '#/map') {
  await page.route('**/api/console/**', route => {
    const url = new URL(route.request().url()), key = url.pathname + url.search;
    return route.fulfill({status: data.endpoints[key] ? 200 : 404, json: data.endpoints[key] || {error: 'not_found'}});
  });
  await page.goto(consoleAssets.origin + '/' + hash);
}

test('the grouped model path exposes the same supported redaction scope', async ({page}) => {
  await openConsole(page);
  await page.getByRole('button', {name: 'Model gateway — how it works', exact: true}).click();
  const explain = page.locator('#view'); // The Map docks its explanation in the right column.
  await expect(explain.getByText(data.profile.masking_scope.summary, {exact: true})).toBeVisible();
  for (const row of data.profile.masking_scope.supported) await expect(explain.getByText(row.label, {exact: false})).toBeVisible();
  await expect(explain.getByText('EXPLAIN · MODEL PATH', {exact: true})).toBeVisible();
  expect(await page.evaluate(() => Console.plainCategories(['UNKNOWN_CATEGORY']))).toBe('an unspecified identifier');
});

test('passport redaction details expose the same limits without promising all personal data is hidden', async ({page}) => {
  await openConsole(page, '#/agents/financial');
  await page.getByRole('button', {name: 'Supported identifier masking', exact: false}).click();
  const drawer = page.getByRole('dialog');
  await expect(drawer.getByText(data.profile.masking_scope.summary, {exact: false})).toBeVisible();
  await expect(drawer.getByText('Matching depends on format and context.', {exact: false})).toBeVisible();
});


for (const source of ['unavailable', 'unknown', undefined]) {
  test('numeric cost with source ' + source + ' cannot invent availability', async ({page}) => {
    await finance(page, {change: trace => { trace.cost_usd = 0.125; trace.cost_source = source; }});
    await ask(page);
    await expect(page.getByRole('region', {name: 'Worker request trace'}).getByText('cost unavailable', {exact: false})).toBeVisible();
  });
}

test('an explicitly reported zero-call turn has zero model cost', async ({page}) => {
  await finance(page, {change: trace => { trace.model_calls = 0; trace.cost_usd = 0; trace.cost_source = 'no_model_call'; }});
  await ask(page);
  await expect(page.getByRole('region', {name: 'Worker request trace'}).getByText('reported model cost $0.0000', {exact: false})).toBeVisible();
});

test('filter and refusal reports remain worker reports with bounded claims', async ({page}) => {
  await finance(page, {change: (trace, reply) => {
    trace.injection_result = {question_instruction_like: true, withheld_fields: 2, result: 'instruction_like_text_withheld'};
    trace.grounding_result = 'ungrounded_claim_blocked'; trace.outcome = 'blocked'; trace.reason = 'ungrounded_claim';
    reply.status = 'blocked'; reply.reason = 'ungrounded_claim'; delete reply.answer;
  }});
  await ask(page);
  const panel = page.getByRole('region', {name: 'Worker request trace'});
  await expect(panel.getByRole('button', {name: 'Instruction-like question reported — details'})).toBeVisible();
  await expect(panel.getByRole('button', {name: 'Grounding refusal reported — details'})).toBeVisible();
  await panel.getByRole('button', {name: 'Field filtering reported — details'}).click();
  await expect(page.getByRole('dialog').getByText('Pattern filtering does not recognize every instruction or prove what the model followed.', {exact: true})).toBeVisible();
});
