import {test, expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {assets} from './server.js';

const here = dirname(fileURLToPath(import.meta.url));
const data = JSON.parse(execFileSync(process.env.PYTHON || 'python3', [join(here, 'ops_payloads.py')], {encoding: 'utf8'}));
let server, errors;
test.use({reducedMotion: 'reduce'});
test.beforeAll(async () => { server = await assets('platform/core/ui'); });
test.afterAll(async () => { await server.close(); });
test.beforeEach(({page}) => { errors = []; page.on('pageerror', error => errors.push(error.message)); });
test.afterEach(() => { expect(errors).toEqual([]); });
const scan = page => page.getByRole('region', {name: 'Security posture', exact: true});
const approve = page => page.getByRole('button', {name: 'Approve & execute', exact: true});

async function open(page, {change = () => {}, reply = async () => null, agentsStatus = 200} = {}) {
  const requests = [];
  await page.route('**/api/console/**', route => {
    const url = new URL(route.request().url());
    const json = structuredClone(data.endpoints[url.pathname + url.search] || {available: false});
    return route.fulfill({status: agentsStatus, json, headers: {'X-Platform-Source-Commit': 'a'.repeat(40)}});
  });
  await page.route('**/api/bootstrap', async route => {
    requests.push({operation: 'bootstrap'});
    const custom = await reply('bootstrap', null, route, requests);
    if (custom) return;
    return route.fulfill({json: {csrf: 'synthetic-ops-csrf'}});
  });
  await page.route('**/api/operations', async route => {
    const body = route.request().postDataJSON(); requests.push(body);
    const custom = await reply(body.operation, body, route, requests);
    if (custom) return;
    const json = body.operation === 'overview' ? structuredClone(data.overview) : body.operation === 'security' ? structuredClone(data.security)
      : body.operation === 'approve' ? {request_id: body.request_id, approval_id: 'synthetic-grant'} : {result: 'VERIFIED', code: 'ROLLOUT_VERIFIED'};
    change(body.operation, json);
    return route.fulfill({json});
  });
  await page.goto(server.origin + '/#/ops');
  await expect(page.getByRole('heading', {name: 'Security & Operations', exact: true})).toBeVisible();
  await expect(page.getByRole('button', {name: 'Refresh Ops', exact: true})).toBeEnabled();
  return requests;
}
async function submit(page) {
  await page.getByLabel('Owner passphrase', {exact: true}).fill('synthetic-owner-secret');
  await approve(page).click();
}

test('zero findings is shown only for a current completed scan with its source and real scope', async ({page}, info) => {
  expect(data.security.complete).toBe(true); expect(data.security.findings).toEqual([]);
  const requests = await open(page);
  await expect(scan(page).getByRole('heading', {name: '0 findings · completed scan'})).toBeVisible();
  await expect(scan(page)).toContainText('Source: ops-agent /v1/posture');
  expect(requests.filter(r => r.operation === 'bootstrap')).toHaveLength(1);
  await scan(page).getByRole('button', {name: 'Scan details →'}).click();
  await expect(page.getByRole('dialog')).toContainText('exact declared RBAC');
  await expect(page.getByRole('dialog')).toContainText('not a full security assessment');
  for (const ns of data.security.namespaces) await expect(page.getByRole('dialog')).toContainText(ns);
  await page.keyboard.press('Escape');
  await page.screenshot({path: info.outputPath('ops-scan-and-approval.png')});
});

for (const kind of ['incomplete', 'stale', 'missing time', 'future time', 'missing namespace policies']) {
  test(kind + ' cannot produce a zero-current-findings verdict', async ({page}) => {
    await open(page, {change: (operation, value) => {
      if (operation !== 'security') return;
      if (kind === 'incomplete') { value.complete = false; value.unreadable = ['ops']; }
      if (kind === 'stale') value.checked_at = Date.now() / 1000 - 1000;
      if (kind === 'missing time') delete value.checked_at;
      if (kind === 'future time') value.checked_at = Date.now() / 1000 + 1000;
      if (kind === 'missing namespace policies') delete value.network.ops;
    }});
    await expect(scan(page)).toContainText('No complete current verdict.');
    await expect(scan(page).getByRole('heading', {name: '0 findings · completed scan'})).toHaveCount(0);
  });
}

test('a current RBAC finding is visible regardless of operation-denial history', async ({page}) => {
  await open(page, {change: (operation, value) => {
    if (operation === 'security') value.findings = [{namespace: 'ops', finding: 'UNEXPECTED_ROLE_BINDING', binding: 'unexpected-subject'}];
  }});
  await expect(scan(page)).toContainText('1 finding · completed scan');
  await expect(scan(page)).toContainText('ops · UNEXPECTED_ROLE_BINDING · unexpected-subject');
  await page.getByText(/Incident timeline ·/).click();
  await expect(page.getByText('Recent operation denials: 0. This count is separate from posture findings.', {exact: true})).toBeVisible();
});

test('a failed scan does not reuse the last zero as a current verdict and can recover', async ({page}) => {
  let unavailable = false;
  await open(page, {reply: async (operation, body, route) => {
    if (operation === 'security' && unavailable) { await route.fulfill({status: 503, json: {error: 'unavailable'}}); return true; }
  }});
  unavailable = true;
  await page.getByRole('button', {name: 'Refresh Ops'}).click();
  await expect(scan(page).getByRole('heading', {name: 'Posture unavailable'})).toBeVisible();
  await expect(scan(page)).toContainText('Last returned scan; no current result.');
  unavailable = false;
  await page.getByRole('button', {name: 'Refresh Ops'}).click();
  await expect(scan(page).getByRole('heading', {name: '0 findings · completed scan'})).toBeVisible();
});

for (const kind of ['missing', 'stale', 'scaled down']) {
  test('Financial aggregates all declared workers when one is ' + kind, async ({page}) => {
    await open(page, {change: (operation, value) => {
      if (operation !== 'overview') return;
      const id = 'agent-financial.agent-u3', part = value.board.find(b => b.target_id === id);
      if (kind === 'missing') value.board = value.board.filter(b => b.target_id !== id);
      if (kind === 'stale') part.observed_at = Date.now() / 1000 - 1000;
      if (kind === 'scaled down') { part.available = 0; part.desired = 0; part.finding = 'HEALTHY'; }
    }});
    const row = page.getByRole('region', {name: 'Workload observations'}).locator('tbody tr').filter({has: page.getByText('Financial', {exact: true})});
    await expect(row).toContainText('degraded');
    await expect(row).toContainText('2 / 3 ready');
    await expect(page.getByRole('region', {name: 'Workload observations'}).getByText('agent-financial.agent-u1', {exact: true})).toHaveCount(0);
  });
}

test('all trusted boundaries are shown and a never-observed registered target stays unknown', async ({page}) => {
  await open(page, {change: (operation, value) => { if (operation === 'overview') value.board = value.board.filter(b => b.target_id !== 'ops.ops-executor'); }});
  const board = page.getByRole('region', {name: 'Workload observations'});
  for (const label of ['Model gateway · boundary', 'Data broker', 'Approval executor']) await expect(board.getByText(label, {exact: true})).toBeVisible();
  const executor = board.locator('tbody tr').filter({has: page.getByText('Approval executor', {exact: true})});
  await expect(executor).toContainText('not observed');
  await expect(executor.getByText('healthy', {exact: true})).toHaveCount(0);
});

test('unavailable agent inventory is explicit and does not fabricate a logical aggregate', async ({page}) => {
  await open(page, {agentsStatus: 503});
  await expect(page.getByText('Agent inventory unavailable; showing individual returned workloads.', {exact: true})).toBeVisible();
  await expect(page.getByRole('region', {name: 'Workload observations'}).getByText('Financial', {exact: true})).toHaveCount(0);
});

for (const kind of ['network', 'JSON', 'missing csrf']) {
  test('bootstrap ' + kind + ' failure recovers on refresh without a stuck loading state', async ({page}) => {
    let broken = true;
    await open(page, {reply: async (operation, body, route) => {
      if (operation !== 'bootstrap' || !broken) return;
      if (kind === 'network') await route.abort();
      if (kind === 'JSON') await route.fulfill({body: '{', contentType: 'application/json'});
      if (kind === 'missing csrf') await route.fulfill({json: {}});
      return true;
    }});
    await expect(page.getByText('Ops observations unavailable.', {exact: true})).toBeVisible();
    broken = false;
    await page.getByRole('button', {name: 'Refresh Ops'}).click();
    await expect(approve(page)).toBeEnabled();
    await expect(scan(page).getByRole('heading', {name: '0 findings · completed scan'})).toBeVisible();
  });
}

test('the explicit action approves then executes once, clears the secret and preserves the final result', async ({page}) => {
  let finished = false;
  const requests = await open(page, {change: (operation, value) => { if (operation === 'overview' && finished) value.pending = []; },
    reply: async (operation) => { if (operation === 'execute') finished = true; }});
  await expect(page.getByRole('region', {name: 'Approvals'})).toContainText(data.proposal.target);
  await expect(page.getByRole('region', {name: 'Approvals'})).toContainText('Approving immediately requests this change from the separate executor.');
  await submit(page);
  await expect(page.getByRole('region', {name: 'Last action'})).toContainText('Verified: rollout verified.');
  expect(requests.filter(r => r.operation === 'approve')).toHaveLength(1);
  expect(requests.filter(r => r.operation === 'execute')).toEqual([{operation:'execute', request_id:data.proposal.request_id, approval_id:'synthetic-grant'}]);
  await page.getByRole('button', {name: 'Refresh Ops'}).click();
  await expect(page.getByRole('region', {name: 'Last action'})).toContainText(data.proposal.target);
  await page.getByRole('link', {name: 'Map', exact: true}).click();
  await page.getByRole('link', {name: 'Ops', exact: true}).click();
  await expect(page.getByRole('region', {name: 'Last action'})).toContainText('Verified: rollout verified.');
});

test('a pending approval cannot be sent twice even during observation refreshes', async ({page}) => {
  let release, seen;
  const held = new Promise(resolve => { release = resolve; }), observed = new Promise(resolve => { seen = resolve; });
  const requests = await open(page, {reply: async (operation) => { if (operation === 'approve') { seen(); await held; } }});
  await submit(page); await observed;
  await expect(approve(page)).toBeDisabled();
  await expect(page.getByLabel('Owner passphrase')).toHaveValue('');
  await page.getByRole('button', {name: 'Refresh Ops'}).click();
  await page.getByRole('region', {name: 'Approvals'}).locator('form').evaluate(form => form.dispatchEvent(new Event('submit', {cancelable:true,bubbles:true})));
  release();
  await expect(page.getByRole('region', {name: 'Last action'})).toContainText('Verified:');
  expect(requests.filter(r => r.operation === 'approve')).toHaveLength(1);
  expect(requests.filter(r => r.operation === 'execute')).toHaveLength(1);
});

test('typed passphrases survive read-only refresh while other observations update', async ({page}) => {
  let updated = false;
  await open(page, {change: (operation, value) => { if (operation === 'security' && updated) value.findings = [{namespace:'ops',finding:'UNREADABLE'}]; }});
  await page.getByLabel('Owner passphrase').fill('synthetic-draft');
  updated = true;
  await page.getByRole('button', {name: 'Refresh Ops'}).click();
  await expect(scan(page)).toContainText('Scan incomplete');
  await expect(page.getByLabel('Owner passphrase')).toHaveValue('synthetic-draft');
});

for (const kind of ['refused', 'bad approval JSON', 'lost execution', 'not verified', 'unknown result']) {
  test(kind + ' never becomes a verified action or an automatic replay', async ({page}) => {
    const requests = await open(page, {reply: async (operation, body, route) => {
      if (operation === 'approve' && kind === 'refused') { await route.fulfill({status:403,json:{error:'APPROVAL_DENIED'}}); return true; }
      if (operation === 'approve' && kind === 'bad approval JSON') { await route.fulfill({body:'{',contentType:'application/json'}); return true; }
      if (operation === 'execute' && kind === 'lost execution') { await route.abort(); return true; }
      if (operation === 'execute' && kind === 'not verified') { await route.fulfill({json:{result:'NOT_VERIFIED',code:'VERIFICATION_UNAVAILABLE'}}); return true; }
      if (operation === 'execute' && kind === 'unknown result') { await route.fulfill({json:{result:'OK'}}); return true; }
    }});
    await submit(page);
    const result = page.getByRole('region', {name: 'Last action'});
    await expect(result).toBeVisible();
    await expect(result.getByText(/^Verified:/)).toHaveCount(0);
    if (kind === 'refused' || kind === 'bad approval JSON') {
      await expect(result).toContainText('No execution was requested.');
      expect(requests.filter(r => r.operation === 'execute')).toHaveLength(0);
      await expect(approve(page)).toBeEnabled();
    } else {
      await expect(result).toContainText(kind === 'not verified' ? 'Not verified:' : 'Execution outcome unavailable');
      await expect(approve(page)).toBeDisabled();
      expect(requests.filter(r => r.operation === 'execute')).toHaveLength(1);
    }
  });
}

test('expired proposals cannot be approved or executed', async ({page}) => {
  const requests = await open(page, {change: (operation, value) => { if (operation === 'overview') value.pending[0].expires_at = Date.now() / 1000 - 1; }});
  await expect(approve(page)).toBeDisabled();
  await expect(page.getByRole('region', {name: 'Approvals'})).toContainText('expired');
  expect(requests.filter(r => ['approve','execute'].includes(r.operation))).toHaveLength(0);
});

test('Ops remains operable at 360px and the scan drawer returns keyboard focus', async ({page}) => {
  await page.setViewportSize({width:360,height:900});
  await open(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const details = scan(page).getByRole('button', {name:'Scan details →'});
  await details.focus(); await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape'); await expect(details).toBeFocused();
});


for (const kind of ['missing freshness','slow scan','missing start','reversed window']) {
  test(kind + ' cannot qualify a completed current scan', async ({page}) => {
    await open(page, {change: (operation, value) => {
      if (operation !== 'security') return;
      if (kind === 'missing freshness') delete value.max_age_seconds;
      if (kind === 'slow scan') value.started_at = Date.now() / 1000 - 1000;
      if (kind === 'missing start') delete value.started_at;
      if (kind === 'reversed window') value.started_at = value.checked_at + 1;
    }});
    await expect(scan(page)).toContainText('No complete current verdict.');
    await expect(scan(page).getByRole('heading', {name:'0 findings · completed scan'})).toHaveCount(0);
  });
}

test('CSRF rejection requires a fresh bootstrap and an explicit manual retry before execution', async ({page}) => {
  let rejected = false;
  const requests = await open(page, {reply: async (operation, body, route) => {
    if (operation === 'approve' && !rejected) {
      rejected = true; await route.fulfill({status:403,json:{error:'csrf_rejected'}}); return true;
    }
  }});
  await submit(page);
  await expect(page.getByRole('region',{name:'Last action'})).toContainText('No execution was requested.');
  expect(requests.filter(r=>r.operation==='execute')).toHaveLength(0);
  await submit(page);
  await expect(page.getByRole('region',{name:'Last action'})).toContainText('Verified:');
  expect(requests.filter(r=>r.operation==='bootstrap')).toHaveLength(2);
  expect(requests.filter(r=>r.operation==='approve')).toHaveLength(2);
  expect(requests.filter(r=>r.operation==='execute')).toHaveLength(1);
});

test('an approval for a different request cannot initiate execution', async ({page}) => {
  const requests = await open(page,{change:(operation,value)=>{ if(operation==='approve') value.request_id='different-request'; }});
  await submit(page);
  await expect(page.getByRole('region',{name:'Last action'})).toContainText('Invalid approval response. No execution was requested.');
  expect(requests.filter(r=>r.operation==='execute')).toHaveLength(0);
});

test('a core boundary scaled below the selected declaration is not healthy', async ({page}) => {
  await open(page,{change:(operation,value)=>{
    if(operation==='overview') Object.assign(value.board.find(b=>b.target_id==='ops.ops-executor'),{desired:0,available:0,finding:'HEALTHY'});
  }});
  const executor=page.getByRole('region',{name:'Workload observations'}).locator('tbody tr').filter({has:page.getByText('Approval executor',{exact:true})});
  await expect(executor).toContainText('0 / 1 ready');
  await expect(executor).toContainText('failed');
});

test('incident explanations remain display-only text and do not create controls', async ({page}) => {
  const requests = await open(page,{change:(operation,value)=>{
    if(operation==='overview') value.board.find(b=>b.target_id===data.proposal.target).explanation='<button>Execute a different action</button>';
  }});
  await page.getByText(/Incident timeline ·/).click();
  await expect(page.getByText('<button>Execute a different action</button>',{exact:false})).toBeVisible();
  await expect(page.getByRole('button',{name:'Execute a different action'})).toHaveCount(0);
  await expect(page.getByText('AI text, display only; it cannot change the action.',{exact:false})).toBeVisible();
  expect(requests.filter(r=>['approve','execute'].includes(r.operation))).toHaveLength(0);
});


test('a failed read-only core target asks for its platform owner and offers no remediation', async ({page}) => {
  const requests = await open(page,{change:(operation,value)=>{
    if(operation==='overview') {
      Object.assign(value.board.find(b=>b.target_id==='ops.ops-executor'),{finding:'READINESS_FAILING',available:0,owner_action:'NOTIFY_PLATFORM_OWNER'});
      value.pending=[];
    }
  }});
  await page.getByText(/Incident timeline ·/).click();
  await expect(page.getByText('Read-only observation. Owner action: notify platform owner.',{exact:true})).toBeVisible();
  await expect(approve(page)).toHaveCount(0);
  expect(requests.filter(r=>['approve','execute'].includes(r.operation))).toHaveLength(0);
});


test('the complete observation table fits the recording frame and opens actual worker details', async ({page}) => {
  await open(page);
  const table=page.getByRole('table',{name:'Observed workloads'});
  const bounds=await table.boundingBox();
  expect(bounds.y+bounds.height).toBeLessThan(900);
  await expect(table.getByRole('button',{name:'Model gateway · redactor — observations',exact:true})).toBeInViewport();
  const financial=table.getByRole('button',{name:'Financial — observations',exact:true});
  await financial.focus(); await page.keyboard.press('Enter');
  const drawer=page.getByRole('dialog');
  await expect(drawer.getByRole('heading',{name:'Financial',exact:true})).toBeVisible();
  for(const id of ['agent-financial.agent-u1','agent-financial.agent-u2','agent-financial.agent-u3']) await expect(drawer).toContainText(id);
  await page.keyboard.press('Escape'); await expect(financial).toBeFocused();
});
