import {test, expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {assets} from './server.js';

const here = dirname(fileURLToPath(import.meta.url));
const data = JSON.parse(execFileSync(process.env.PYTHON || 'python3', [join(here, 'presentation_payloads.py')], {encoding: 'utf8'}));
let server, errors;
test.beforeAll(async () => { server = await assets('platform/core/ui'); });
test.afterAll(async () => { await server.close(); });
test.beforeEach(async ({page}) => { errors = []; page.on('pageerror', error => errors.push(error.message)); });
test.afterEach(() => { expect(errors).toEqual([]); });

async function open(page, {change = () => {}, status = () => 200, hash = '#/map'} = {}) {
  await page.route('**/api/console/**', route => {
    const url = new URL(route.request().url()), path = url.pathname + url.search;
    const body = structuredClone(data.endpoints[path] || {available: false, status: 'missing', results: [], file: 'ConfigMap apps/attack-results'});
    change(path, body);
    return route.fulfill({status: status(path), json: body});
  });
  await page.goto(server.origin + '/' + hash);
  if (hash === '#/map') await expect(page.locator('[data-platform-group]')).toHaveCount(3);
}
const gateway = page => page.getByRole('button', {name: 'Model gateway — how it works', exact: true});

test('three original-style cells and a thin audit strip fit the recording frame', async ({page}, info) => {
  await open(page);
  const groups = page.locator('[data-platform-group]');
  for (const name of ['Model gateway', 'Data broker', 'Approval executor']) {
    await expect(page.getByRole('button', {name: name + ' — how it works', exact: true})).toBeVisible();
  }
  for (const subtitle of ['identifiers masked first', 'your rows only, read-only', 'changes need your signature']) {
    await expect(page.locator('svg').getByText(subtitle, {exact: true})).toBeVisible();
  }
  await expect(page.getByRole('button', {name: 'Redactor — how it works', exact: true})).toHaveCount(0);
  await expect(page.getByRole('button', {name: 'Redaction gateway — how it works', exact: true})).toHaveCount(0);
  const geometry = await groups.evaluateAll(nodes => nodes.map(node => {
    const rect = node.querySelector('rect');
    return {x: +rect.getAttribute('x'), y: +rect.getAttribute('y'), h: +rect.getAttribute('height'), w: +rect.getAttribute('width')};
  }));
  const audit = page.locator('[data-audit-strip]');
  await expect(audit.getByText('Audit · request events', {exact: true})).toBeVisible();
  const strip = await audit.locator('rect').evaluate(rect => ({x: +rect.getAttribute('x'), y: +rect.getAttribute('y'), h: +rect.getAttribute('height'), w: +rect.getAttribute('width')}));
  expect(strip.y).toBe(Math.max(...geometry.map(rect => rect.y + rect.h)));
  expect(strip.h).toBeLessThan(Math.min(...geometry.map(rect => rect.h)) / 2);
  expect(strip.w).toBe(geometry[0].w);
  const drawing = await page.locator('[data-map-layout="diagram"]').boundingBox();
  expect(drawing.y + drawing.height).toBeLessThanOrEqual(900);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({path: info.outputPath('map-three-cells.png'), animations: 'disabled'});
});

test('both external connectors originate inside Model gateway', async ({page}) => {
  await open(page);
  const connections = await page.locator('[data-connects-from="model-path"]').evaluateAll(nodes => nodes.map(node => {
    const line = node.querySelector('line');
    return {to: node.getAttribute('data-connects-to'), x: +line.getAttribute('x1'), y: +line.getAttribute('y1')};
  }));
  expect(connections.map(edge => edge.to)).toEqual(['model-provider', 'dlp']);
  const box = await page.locator('[data-platform-group="model-path"] rect').evaluate(rect => ({x: +rect.getAttribute('x'), y: +rect.getAttribute('y'), w: +rect.getAttribute('width'), h: +rect.getAttribute('height')}));
  for (const edge of connections) {
    expect(edge.x).toBe(box.x + box.w);
    expect(edge.y).toBeGreaterThan(box.y);
    expect(edge.y).toBeLessThan(box.y + box.h);
  }
});

test('the grouped explanation lists exactly its three parts and the supported masking scope', async ({page}, info) => {
  await open(page);
  await gateway(page).focus();
  await page.keyboard.press('Enter');
  const panel = page.getByRole('region', {name: 'Model gateway', exact: true});
  await expect(panel).toBeVisible();
  await expect(panel.getByRole('button', {name: 'Close', exact: true})).toBeFocused();
  await expect(panel.locator(':scope > .block > .label')).toHaveText(['Path', 'Redaction gateway', 'Redactor', 'Model gateway', 'Supported masking patterns', 'Observations']);
  for (const id of ['gateway-boundary', 'redactor', 'gateway']) await expect(panel.getByText(id, {exact: true})).toBeVisible();
  const providerRole = await panel.getByText('gateway', {exact: true}).locator('..').boundingBox();
  const region = await panel.boundingBox();
  expect(providerRole.y + providerRole.height).toBeLessThan(region.y + region.height - 80);

  await expect(panel.getByText(data.profile.masking_scope.summary, {exact: true})).toBeVisible();
  for (const row of data.profile.masking_scope.supported) await expect(panel.getByText(row.label, {exact: false})).toBeVisible();
  await expect(page.locator('#scrim')).toBeHidden();
  await page.screenshot({path: info.outputPath('map-model-path.png'), animations: 'disabled'});
  await page.keyboard.press('Escape');
  await expect(panel).toHaveCount(0);
  await expect(gateway(page)).toBeFocused();
  await expect(gateway(page).locator('rect')).toHaveCSS('stroke-width', '2.5px');
});

test('broker, executor and audit continue to open their unchanged API topics', async ({page}) => {
  await open(page);
  for (const [name, topic] of [['Data broker', 'financial-frontdoor'], ['Approval executor', 'ops-executor'], ['Audit · request events', 'audit']]) {
    const button = page.getByRole('button', {name: name + ' — how it works', exact: true});
    await button.focus(); await page.keyboard.press('Space');
    await expect(page.getByRole('heading', {name: data.endpoints['/api/console/explain/' + topic].title, exact: true})).toBeVisible();
    await page.keyboard.press('Escape'); await expect(button).toBeFocused();
  }
});

test('allowed paths, denial explanations and motion preference changes keep working', async ({page}) => {
  await page.emulateMedia({reducedMotion: 'no-preference'});
  await open(page);
  expect(await page.locator('animateMotion').count()).toBeGreaterThan(0);
  const paths = page.getByRole('button', {name: /network path — how it works$/});
  expect(await paths.count()).toBe(3);
  const denial = page.getByRole('button', {name: /: denied — how it works$/}).first();
  await denial.focus();
  await expect(denial.locator('.tag')).toHaveCSS('stroke-width', '2.5px');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', {name: 'Network wall', exact: true})).toBeVisible();
  await page.keyboard.press('Escape');
  await page.emulateMedia({reducedMotion: 'reduce'});
  await expect(page.locator('animateMotion')).toHaveCount(0);
  await expect(page.locator('.cross').first()).toHaveCSS('animation-name', 'none');
  await page.emulateMedia({reducedMotion: 'no-preference'});
  await expect.poll(() => page.locator('animateMotion').count()).toBeGreaterThan(0);
});

test('360px uses a readable vertical list and restores focus after details and resizing', async ({page}, info) => {
  await page.setViewportSize({width: 360, height: 900});
  await open(page);
  await expect(page.locator('[data-map-layout="list"]')).toBeVisible();
  const title = await gateway(page).locator('.t-item').boundingBox();
  expect(title.height).toBeGreaterThanOrEqual(16);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await gateway(page).scrollIntoViewIfNeeded();
  await page.screenshot({path: info.outputPath('map-mobile-list.png'), animations: 'disabled'});
  await gateway(page).focus(); await page.keyboard.press('Enter');
  await expect(page.getByRole('region', {name: 'Model gateway', exact: true})).toBeVisible();
  await page.keyboard.press('Escape'); await expect(gateway(page)).toBeFocused();
  await page.setViewportSize({width: 1440, height: 900});
  await expect(page.locator('[data-map-layout="diagram"]')).toBeVisible();
  await expect(gateway(page)).toBeFocused();
});

test('media changes preserve an open explanation and current opener', async ({page}) => {
  await open(page); await gateway(page).click();
  await expect(page.getByRole('region', {name: 'Model gateway', exact: true})).toBeVisible();
  await page.setViewportSize({width: 360, height: 900});
  await expect(page.locator('[data-map-layout="list"]')).toBeVisible();
  await expect(page.getByRole('region', {name: 'Model gateway', exact: true}).getByRole('button', {name: 'Close', exact: true})).toBeFocused();
  await page.keyboard.press('Escape'); await expect(gateway(page)).toBeFocused();
});

test('missing declarations and missing explanation sources remain explicit', async ({page}) => {
  await open(page, {change: (path, body) => {
    if (path === '/api/console/topology') body.nodes = body.nodes.filter(node => node.id !== 'redactor');
  }});
  await expect(gateway(page).getByText('declaration incomplete', {exact: true})).toBeVisible();
  await gateway(page).click();
  await expect(page.getByText('This part is unavailable in the current declaration or its explanation could not be read.', {exact: true})).toBeVisible();
  await expect(page.getByText(data.profile.masking_scope.summary, {exact: true})).toHaveCount(0);
});

test('absent agent-to-platform edges cannot be drawn as allowed paths', async ({page}) => {
  const actors = new Set(data.endpoints['/api/console/agents'].agents.map(actor => actor.node));
  await open(page, {change: (path, body) => {
    if (path === '/api/console/topology') body.edges = body.edges.filter(edge => !actors.has(edge.from));
  }});
  await expect(page.getByRole('button', {name: /network path/})).toHaveCount(0);
});

test('navigation releases media listeners and late group responses cannot open on another screen', async ({page}) => {
  await page.addInitScript(() => {
    const original = window.matchMedia.bind(window), subscriptions = new Map();
    window.__mediaCount = () => [...subscriptions.values()].reduce((sum, listeners) => sum + listeners.size, 0);
    window.matchMedia = query => {
      const media = original(query), add = media.addEventListener.bind(media), remove = media.removeEventListener.bind(media);
      media.addEventListener = (type, listener, ...args) => {
        if (type === 'change') { if (!subscriptions.has(media)) subscriptions.set(media, new Set()); subscriptions.get(media).add(listener); }
        return add(type, listener, ...args);
      };
      media.removeEventListener = (type, listener, ...args) => {
        if (type === 'change' && subscriptions.has(media)) { subscriptions.get(media).delete(listener); if (!subscriptions.get(media).size) subscriptions.delete(media); }
        return remove(type, listener, ...args);
      };
      return media;
    };
  });
  await open(page, {hash: '#/break'});
  const baseline = await page.evaluate(() => window.__mediaCount());
  await page.getByRole('link', {name: 'Map', exact: true}).click();
  await expect(page.locator('[data-platform-group]')).toHaveCount(3);
  expect(await page.evaluate(() => window.__mediaCount())).toBeGreaterThan(baseline);
  const pending = [];
  await page.route('**/api/console/explain/**', route => { pending.push(route); });
  await gateway(page).click();
  await expect.poll(() => pending.length).toBe(3);
  await page.getByRole('link', {name: 'Break it', exact: true}).click();
  for (const route of pending) await route.fulfill({json: data.endpoints[new URL(route.request().url()).pathname]});
  await expect(page.getByRole('heading', {name: 'Try to break it.', exact: true})).toBeVisible();
  expect(await page.evaluate(() => window.__mediaCount())).toBe(baseline);
  await expect(page.locator('.xpanel')).toHaveCount(0);
  await expect(page.getByRole('dialog')).not.toBeVisible();
});
