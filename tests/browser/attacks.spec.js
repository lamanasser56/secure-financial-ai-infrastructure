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
  await expect(page.getByText('6/6 controls passed · 0 failed · 0 not exercised')).toBeVisible();
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
  await expect(page.getByText('6/6 controls passed · 0 failed · 1 not exercised')).toBeVisible();
  await expect(page.getByText('Incomplete report. Required execution or runner identity is missing.')).toBeVisible();
  await expect(page.getByText('Failed', {exact: true})).toHaveCount(0);
});

test('a real failed check remains a failure', async ({page}) => {
  await open(page, 'failed');
  await expect(page.getByText('Failed', {exact: true})).toBeVisible();
  await expect(page.getByText('6/6 controls passed · 1 failed · 0 not exercised')).toBeVisible();
  await expect(page.getByText('Incomplete report.', {exact: false})).toHaveCount(0);
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
