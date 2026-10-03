'use strict';
const byId = (id) => document.getElementById(id);
let agent = 'infrastructure';
let csrf = null;
let report = null;
let busy = false;
const tabs = [byId('tab-infrastructure'), byId('tab-financial')];
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
function resetResult() {
  report = null;
  byId('download').disabled = true;
  byId('result').hidden = true;
  byId('report-details').open = false;
  byId('audit-details').open = false;
}
function selectTab(index, focus = false) {
  if (busy) return;
  agent = index === 0 ? 'infrastructure' : 'financial';
  tabs.forEach((tab, i) => {
    tab.setAttribute('aria-selected', String(i === index));
    tab.tabIndex = i === index ? 0 : -1;
    byId(tab.getAttribute('aria-controls')).hidden = i !== index;
  });
  if (focus) tabs[index].focus();
  resetResult();
}
tabs.forEach((tab, index) => {
  tab.addEventListener('click', () => selectTab(index));
  tab.addEventListener('keydown', (event) => {
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      selectTab(event.key === 'Home' ? 0 : event.key === 'End' ? 1 : 1 - index, true);
    }
  });
});
function cards(parent, fields) {
  const grid = element('div', undefined, 'fact-grid');
  for (const [label, value] of fields) {
    const card = element('div', undefined, 'fact-card');
    card.append(element('h4', label), element('p', value));
    grid.append(card);
  }
  parent.append(grid);
}
function table(parent, caption, headings, rows) {
  const wrapper = element('div', undefined, 'table-scroll');
  const node = element('table');
  node.append(element('caption', caption));
  const head = element('thead');
  const header = element('tr');
  headings.forEach((label) => {
    const cell = element('th', label);
    cell.scope = 'col';
    header.append(cell);
  });
  head.append(header);
  const body = element('tbody');
  rows.forEach((values) => {
    const row = element('tr');
    values.forEach((value) => row.append(element('td', value)));
    body.append(row);
  });
  node.append(head, body);
  wrapper.append(node);
  parent.append(wrapper);
}
function renderResult(data) {
  const view = data.presentation;
  byId('answer').replaceChildren();
  byId('facts').replaceChildren();
  byId('usage').replaceChildren();
  const labels = {completed: 'Simulation completed', clarification_required: 'Clarification required', blocked: 'Request blocked'};
  if (!view || data.mode !== 'offline_simulation' || data.agent !== agent || !labels[data.status]) throw new Error('invalid response');
  byId('badge').textContent = labels[data.status];
  if (data.status === 'completed') {
    if (agent === 'infrastructure') {
      byId('facts').append(element('h3', 'Infrastructure diagnosis · deterministic tool facts'));
      cards(byId('facts'), view.diagnosis.map((item) => [item.label, item.value]));
      table(byId('facts'), 'Supporting evidence IDs', ['Evidence ID', 'Supports'],
        view.supporting_evidence.map((item) => [item.source_id, item.purpose]));
      byId('facts').append(element('h3', 'Unverified points'));
      const list = element('ul');
      view.unverified_points.forEach((point) => list.append(element('li', point)));
      byId('facts').append(list);
      const context = view.supplemental_context;
      const aside = element('aside', undefined, 'supplemental');
      aside.append(element('h3', 'Supplemental context · invented image fixture'));
      aside.append(element('p', 'This is not supporting failure evidence or a current image scan, signature or registry assertion.'));
      cards(aside, [['Source ID', context.source_id], ['Fixture status', context.status],
        ['Invented HIGH count', context.high], ['Invented CRITICAL count', context.critical]]);
      aside.append(element('p', context.limitations, 'muted'));
      byId('facts').append(aside);
    } else {
      const finance = view.financial;
      byId('facts').append(element('h3', 'Synthetic expense facts · deterministic tool calculations'));
      cards(byId('facts'), [['Reporting period', finance.period], ['Synthetic source ID', finance.source_id],
        ['Expense count', finance.expense_count], ['Currency', finance.currency], ['Total', finance.total]]);
      table(byId('facts'), 'Ranked expense categories', ['Rank', 'Category', 'Expenses', 'Amount'],
        finance.categories.map((item) => [item.rank, item.category.charAt(0).toUpperCase() + item.category.slice(1), item.expense_count, item.amount]));
      if (!finance.categories.length) byId('facts').append(element('p', 'No synthetic expenses were recorded for this period.'));
      byId('facts').append(element('p', 'Amounts use the currency’s defined scale and integer minor units. Original integers are preserved in the sanitized report.', 'muted'));
    }
    byId('answer').append(element('h3', 'Simulated explanation · untrusted model text'),
      element('p', data.answer.summary), element('p', data.answer.limitations, 'muted'));
  } else {
    byId('answer').append(element('h3', labels[data.status]), element('p',
      data.status === 'clarification_required' ? data.question : 'A required security control blocked this request. No partial result is shown and no retry was made.'));
  }
  const usage = view.usage;
  byId('usage').append(element('h3', 'Run accounting'));
  cards(byId('usage'), [['Simulated model requests', usage.simulated_model_requests],
    ['External provider calls', usage.external_provider_calls], ['Tool dispatch attempts', usage.tool_dispatch_attempts],
    ['Token usage', 'Unavailable'], ['Cost', 'Unavailable']]);
  byId('usage').append(element('p', usage.redaction_notice, 'muted'));
  byId('report-json').textContent = JSON.stringify(data, null, 2);
  byId('audit').textContent = JSON.stringify({mode: data.mode, authentication: data.authentication,
    tenant_ref: data.tenant_ref, model_requests: data.model_requests, tool_executions: data.tool_executions,
    audit: data.audit}, null, 2);
  report = data;
  byId('download').disabled = false;
  byId('result').hidden = false;
  byId('status').textContent = labels[data.status] + '. No external provider request was made.';
}
async function bootstrap() {
  try {
    const response = await fetch('/api/bootstrap', {cache: 'no-store', credentials: 'omit'});
    const data = await response.json();
    if (!response.ok || data.mode !== 'offline_simulation' || data.synthetic_only !== true || typeof data.csrf !== 'string') throw new Error('blocked');
    csrf = data.csrf;
    byId('run').disabled = false;
    byId('status').textContent = 'Ready for offline synthetic simulation';
  } catch (_) {
    byId('status').textContent = 'Private demo boundary unavailable';
  }
}
byId('run').addEventListener('click', async () => {
  busy = true;
  byId('run').disabled = true;
  tabs.forEach((tab) => { tab.disabled = true; });
  resetResult();
  byId('status').textContent = 'Validating and running…';
  try {
    const response = await fetch('/api/run', {
      method: 'POST', cache: 'no-store', credentials: 'omit',
      headers: {'Content-Type': 'application/json', 'X-Demo-CSRF': csrf},
      body: JSON.stringify({agent,
        period: agent === 'financial' ? byId('period').value || null : null,
        scenario_id: agent === 'infrastructure' ? byId('scenario').value : null})
    });
    const data = await response.json();
    if (!response.ok) throw new Error('blocked');
    renderResult(data);
  } catch (_) {
    resetResult();
    byId('status').textContent = 'Request rejected or unavailable; no retry was made.';
  } finally {
    busy = false;
    tabs.forEach((tab) => { tab.disabled = false; });
    byId('run').disabled = csrf === null;
  }
});
byId('download').addEventListener('click', () => {
  if (!report || busy) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2) + '\n'], {type: 'application/json'}));
  const link = element('a');
  link.href = url;
  link.download = 'synthetic-' + agent + '-sanitized-report.json';
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
bootstrap();
