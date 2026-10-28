import {test, expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {dirname, resolve, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {assets} from './server.js';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '../..');
const fixtures = JSON.parse(execFileSync(process.env.PYTHON || 'python3', [join(here, 'attack_payloads.py')], {
  encoding: 'utf8', env: {...process.env, PYTHONPATH: join(root, 'platform/core/src')}
}));
let server, origin;
test.beforeAll(async () => { server = await assets('platform/core/ui'); origin = server.origin; });
test.afterAll(async () => { await server.close(); });

async function open(page, scenario, status = 200) {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/console/attacks', route => route.fulfill({status,
    headers: {'Content-Type': 'application/json', 'X-Platform-Source-Commit': 'b'.repeat(40)},
    body: JSON.stringify(fixtures[scenario])}));
  await page.goto(origin + '/#/break');
  await expect(page.getByText('Loading…', {exact: true})).toHaveCount(0);
  expect(errors).toEqual([]);
}

test('current report distinguishes boundary attempts from positive controls and expands every row', async ({page}, info) => {
  await open(page, 'passed');
  await expect(page.getByText('This release', {exact: true})).toBeVisible();
  await expect(page.getByText('Attack cases: 17 held · 0 failed · 0 not exercised (of 17)')).toBeVisible();
  await expect(page.getByText('Controls: 6 passed · 0 failed · 0 not exercised (of 6)')).toBeVisible();
  await expect(page.getByText('17 attack cases + 6 controls = 23 recorded cases.')).toBeVisible();
  await expect(page.locator('.atk')).toHaveCount(6);
  await page.screenshot({path: info.outputPath('break-current.png'), animations: 'disabled'});
  await page.getByRole('button', {name: 'Show all 23', exact: true}).click();
  await expect(page.locator('.atk')).toHaveCount(23);
  const merchant = page.locator('.atk').filter({hasText: 'Answer about a merchant containing digits'});
  await expect(merchant.getByText('Passed', {exact: true})).toBeVisible();
  await expect(merchant.getByText('Boundary held', {exact: true})).toHaveCount(0);
  await expect(page.getByText('Blocked', {exact: true})).toHaveCount(0);
  await page.getByRole('button', {name: 'Show the first 6', exact: true}).click();
  await expect(page.locator('.atk')).toHaveCount(6);
});

test('incomplete execution is distinct from an observed failure', async ({page}) => {
  await open(page, 'incomplete');
  await expect(page.getByText('Not exercised', {exact: true})).toBeVisible();
  await expect(page.getByText('Attack cases: 16 held · 0 failed · 1 not exercised (of 17)')).toBeVisible();
  await expect(page.getByText('Controls: 6 passed · 0 failed · 0 not exercised (of 6)')).toBeVisible();
  await expect(page.getByText('Incomplete report. It cannot qualify this release because:')).toBeVisible();
  await expect(page.locator('ul.why li')).toHaveText(['Read or write beyond broker database rights — not exercised: The two simultaneous user turns could not be held open together.']);
  await expect(page.getByText('Failed', {exact: true})).toHaveCount(0);
});

test('a real failed check remains a failure', async ({page}) => {
  await open(page, 'failed');
  await expect(page.getByText('Failed', {exact: true})).toBeVisible();
  await expect(page.getByText('Attack cases: 16 held · 1 failed · 0 not exercised (of 17)')).toBeVisible();
  await expect(page.getByText('Incomplete report.', {exact: false})).toHaveCount(0);
});

test('every case opens with its outcome, recorded reason and facts', async ({page}) => {
  await open(page, 'incomplete');
  await page.locator('.atk').filter({hasText: 'Read or write beyond broker database rights'}).click();
  const drawer = page.getByRole('dialog');
  await expect(drawer.getByText('EXPLAIN · CASE 3 OF 23 · ATTACK', {exact: true})).toBeVisible();
  await expect(drawer.getByText('The two simultaneous user turns could not be held open together.')).toBeVisible();
  await expect(drawer.getByText('active_turn_not_established', {exact: true})).toBeVisible();
  await page.keyboard.press('Escape');
  await open(page, 'facts');
  await page.locator('.atk').filter({hasText: 'Forge a session or name another user'}).click();
  await expect(page.getByRole('dialog').locator('pre')).toHaveText('forged_session_cookie: 401\ninsert_naming_other_user: 400\nlama_sees_sara_rows: false');
});

test('a case link opens that case directly, even beyond the first six', async ({page}) => {
  await page.route('**/api/console/attacks', route => route.fulfill({status: 200, headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(fixtures.passed)}));
  await page.goto(origin + '/#/break/ops_stale_approval_refused');
  await expect(page.getByRole('dialog').getByRole('heading', {name: 'Forge, replay or reuse a stale approval'})).toBeVisible();
  await expect(page.locator('.atk')).toHaveCount(23);
});

for (const [scenario, label] of [['different', 'Other release'], ['unbound', 'Release unbound']]) {
  test(scenario + ' cannot qualify the current release', async ({page}) => {
    await open(page, scenario);
    await expect(page.getByText(label, {exact: true})).toBeVisible();
    await expect(page.getByText('This report does not qualify this release.')).toBeVisible();
  });
}

test('pre-versioned history is unqualified, never a stopped attack', async ({page}) => {
  await open(page, 'historical');
  await expect(page.getByText('Historical report', {exact: true})).toBeVisible();
  await expect(page.getByText('Recorded PASS', {exact: true})).toBeVisible();
  await expect(page.getByText('Unqualified outcomes', {exact: true})).toBeVisible();
  await expect(page.getByText('Boundary held', {exact: true})).toHaveCount(0);
});

for (const [scenario, label] of [['missing', 'No mounted results.'], ['invalid', 'Mounted results are invalid.'], ['unavailable', 'Mounted results are unreadable.']]) {
  test(scenario + ' has an honest read-only state without historical fallback', async ({page}) => {
    await open(page, scenario);
    await expect(page.getByText(label, {exact: true})).toBeVisible();
    await expect(page.getByText('Run make attack', {exact: false})).toBeVisible();
    await expect(page.locator('.atk')).toHaveCount(0);
  });
}

test('API failure does not display a result', async ({page}) => {
  await open(page, 'missing', 503);
  await expect(page.getByText('Results unavailable.', {exact: true})).toBeVisible();
  await expect(page.locator('.atk')).toHaveCount(0);
});

test('UTC time and report identity remain inspectable with drawer keyboard recovery', async ({page}, info) => {
  await open(page, 'passed');
  await expect(page.locator('time').first()).toHaveText('2026-10-25 12:00:00 UTC');
  const details = page.getByRole('button', {name: 'Report details →', exact: true});
  await details.click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByText('Source ' + 'b'.repeat(40), {exact: true})).toBeVisible();
  await expect(page.getByText('sha256:' + 'c'.repeat(64), {exact: true})).toBeVisible();
  await page.screenshot({path: info.outputPath('break-report-details.png'), animations: 'disabled'});
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(details).toBeFocused();
});


test('desktop and narrow layouts contain the report without horizontal page overflow', async ({page}) => {
  for (const width of [1440, 360]) {
    await page.setViewportSize({width, height: 900});
    for (const scenario of ['passed', 'historical']) {
      await open(page, scenario);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    }
  }
});
