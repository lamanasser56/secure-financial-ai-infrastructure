'use strict';
const byId = (id) => document.getElementById(id);
let language = 'en';
let agent = 'infrastructure';
let catalog = null;
let csrf = null;
let busy = false;
let statusCode = 'loading';
let selectedReport = null;
const states = {
  infrastructure: {id: null, records: [], budget: null, draft: ''},
  financial: {id: null, records: [], budget: null, draft: ''}
};
const tabs = [byId('tab-infrastructure'), byId('tab-financial')];
const technical = /\x60[^\x60]{1,240}\x60|https?:\/\/[^\s<>]{1,240}|SAR [0-9]+\.[0-9]{2}|[A-Za-z0-9][A-Za-z0-9_./:@=+-]*/g;
function t(key, lang = language, values = {}) {
  const source = catalog ? catalog[lang][key] : null;
  if (typeof source !== 'string') throw new Error('Invalid localization');
  return source.replace(/\{([a-z_]+)\}/g, (_, name) => String(values[name]));
}
function setText(node, value) {
  node.replaceChildren();
  const source = String(value).replace(/[\u202a-\u202e\u2066-\u2069]/g, '\ufffd');
  let cursor = 0;
  for (const match of source.matchAll(technical)) {
    node.append(document.createTextNode(source.slice(cursor, match.index)));
    const code = match[0].charCodeAt(0) === 96;
    const item = document.createElement(code ? 'code' : 'bdi');
    item.dir = 'ltr';
    item.textContent = code ? match[0].slice(1, -1) : match[0];
    node.append(item);
    cursor = match.index + match[0].length;
  }
  node.append(document.createTextNode(source.slice(cursor)));
}
function element(tag, value, className) {
  const node = document.createElement(tag);
  if (value !== undefined) setText(node, value);
  if (className) node.className = className;
  return node;
}
function status(code) {
  statusCode = code;
  setText(byId('status'), t(code));
}
function setBusy(value) {
  busy = value;
  byId('send').disabled = value || csrf === null;
  byId('new-conversation').disabled = value || csrf === null;
  byId('question').disabled = value;
  byId('example').disabled = value;
  byId('scenario').disabled = value;
  byId('period').disabled = value;
  tabs.forEach((tab) => { tab.disabled = value; });
  byId('workspace').setAttribute('aria-busy', String(value));
  byId('history').setAttribute('aria-busy', String(value));
}
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
function renderBudget() {
  byId('budget').replaceChildren();
  const budget = states[agent].budget;
  if (!budget) return;
  byId('budget').append(element('h3', t('budget')));
  cards(byId('budget'), [[t('turns'), budget.turns], [t('modelBudget'), budget.model_requests], [t('toolBudget'), budget.tool_dispatches]]);
}
function renderFacts(frame) {
  selectedReport = null;
  byId('download').disabled = true;
  byId('result').hidden = true;
  byId('report-details').open = false;
  byId('audit-details').open = false;
  byId('facts').replaceChildren();
  byId('usage').replaceChildren();
  if (!frame) return;
  const data = frame.response;
  const view = data.presentation;
  setText(byId('badge'), t(data.status));
  setText(byId('mode'), t(data.mode === 'offline_simulation' ? 'offline' : 'live'));
  if (data.status === 'completed') {
    byId('facts').append(element('h3', t('toolFacts')));
    if (agent === 'infrastructure') {
      cards(byId('facts'), view.diagnosis.map((item) => [item.label, item.value]));
      table(byId('facts'), t('supportingEvidence'), [t('evidenceId'), t('supports')],
        view.supporting_evidence.map((item) => [item.source_id, item.purpose]));
      byId('facts').append(element('h3', t('unverified')));
      const list = element('ul');
      view.unverified_points.forEach((point) => list.append(element('li', point)));
      byId('facts').append(list);
      const context = view.supplemental_context;
      const aside = element('aside', undefined, 'supplemental');
      aside.append(element('h3', t('supplemental')), element('p', t('notCurrentScan')));
      cards(aside, [[t('sourceId'), context.source_id], [t('fixtureStatus'), context.status_label],
        [t('inventedHigh'), context.high], [t('inventedCritical'), context.critical]]);
      aside.append(element('p', context.limitations, 'muted'));
      byId('facts').append(aside);
    } else {
      const finance = view.financial;
      cards(byId('facts'), [[t('reportingPeriod'), finance.period], [t('syntheticSource'), finance.source_id],
        [t('expenseCount'), finance.expense_count], [t('currency'), finance.currency], [t('total'), finance.total]]);
      table(byId('facts'), t('rankedCategories'), [t('rank'), t('category'), t('expenses'), t('amount')],
        finance.categories.map((item) => [item.rank, item.category_label, item.expense_count, item.amount]));
      byId('facts').append(element('p', t('moneyNote'), 'muted'));
    }
  } else if (data.availability) {
    cards(byId('facts'), [[t('availabilitySource'), data.availability.period], [t('syntheticSource'), data.availability.source_id]]);
    byId('facts').append(element('p', t('availableMonths')));
  }
  const usage = view.usage;
  byId('usage').append(element('h3', t('accounting')));
  cards(byId('usage'), [[t('modelRequests'), usage.simulated_model_requests],
    [t('providerCalls'), usage.external_provider_calls], [t('toolAttempts'), usage.tool_dispatch_attempts],
    [t('tokens'), t('unknown')], [t('cost'), t('unknown')]]);
  byId('usage').append(element('p', usage.redaction_notice, 'muted'));
  byId('report-json').textContent = JSON.stringify(frame.report, null, 2);
  byId('audit').textContent = JSON.stringify(frame.report.audit, null, 2);
  selectedReport = frame.report;
  byId('download').disabled = false;
  byId('result').hidden = false;
}
function renderHistory() {
  const records = states[agent].records;
  byId('history').replaceChildren();
  let visible = 0;
  for (const record of records) {
    record.element.hidden = record.language !== language;
    byId('history').append(record.element);
    if (!record.element.hidden) visible++;
  }
  byId('empty-conversation').hidden = visible > 0;
  byId('other-language').hidden = records.every((record) => record.language === language);
  const latest = records.filter((record) => record.language === language && record.frame).at(-1);
  renderFacts(latest ? latest.frame : null);
  renderBudget();
}
function applyLanguage() {
  document.documentElement.lang = language;
  document.documentElement.dir = language === 'ar' ? 'rtl' : 'ltr';
  document.title = t('pageTitle');
  for (const node of document.querySelectorAll('[data-i18n]')) {
    if (node.tagName === 'OPTION') node.textContent = t(node.dataset.i18n);
    else setText(node, t(node.dataset.i18n));
  }
  byId('language').options[0].textContent = t('enName');
  byId('language').options[1].textContent = t('arName');
  byId('question').placeholder = t('questionPlaceholder');
  byId('question').lang = language;
  document.querySelector('[role=tablist]').setAttribute('aria-label', t('agents'));
  setText(byId('status'), t(statusCode));
  renderHistory();
}
function selectTab(index, focus = false) {
  if (busy) return;
  states[agent].draft = byId('question').value;
  agent = index === 0 ? 'infrastructure' : 'financial';
  tabs.forEach((tab, i) => {
    tab.setAttribute('aria-selected', String(i === index));
    tab.tabIndex = i === index ? 0 : -1;
    byId(tab.getAttribute('aria-controls')).hidden = i !== index;
  });
  byId('question').value = states[agent].draft;
  if (focus) tabs[index].focus();
  if (catalog) renderHistory();
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
byId('language').addEventListener('change', () => {
  if (!catalog || !['en', 'ar'].includes(byId('language').value)) return;
  language = byId('language').value;
  applyLanguage(); // No request, permission change, translation or tool execution.
});
byId('example').addEventListener('click', () => {
  if (busy || !catalog) return;
  const values = agent === 'infrastructure'
    ? {topic: t(byId('scenario').value || 'archive-export')}
    : {period: byId('period').value};
  const key = agent === 'infrastructure' ? 'exampleInfra' : values.period ? 'exampleFinancial' : 'exampleFinanceMissing';
  byId('question').value = t(key, language, values);
  states[agent].draft = byId('question').value;
  byId('question').focus();
});
function addMessage(profile, lang, role, value, frame = null) {
  const node = element('li', undefined, 'message ' + role);
  node.lang = lang;
  node.dir = lang === 'ar' ? 'rtl' : 'ltr';
  node.append(element('h3', t(role === 'user' ? 'you' : 'assistant', lang)));
  if (frame) node.append(element('p', t(frame.response.mode === 'offline_simulation' ? 'offline' : 'live', lang), 'muted'));
  node.append(element('p', value));
  const state = states[profile];
  state.records.push({language: lang, element: node, frame});
  state.records = state.records.slice(-16);
}
async function boundedJSON(response) {
  const reader = response.body.getReader();
  const chunks = [];
  let length = 0;
  try {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      length += chunk.value.byteLength;
      if (length > 65536) {
        await reader.cancel();
        throw new Error('Bounded response required');
      }
      chunks.push(chunk.value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(length);
  let offset = 0;
  chunks.forEach((chunk) => { bytes.set(chunk, offset); offset += chunk.length; });
  return JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
}
async function post(path, payload) {
  const response = await fetch(path, {
    method: 'POST', cache: 'no-store', credentials: 'same-origin',
    headers: {'Content-Type': 'application/json', 'X-Demo-CSRF': csrf},
    body: JSON.stringify(payload)
  });
  const data = await boundedJSON(response);
  if (!response.ok) throw new Error('Request rejected');
  return data;
}
byId('question-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy || !csrf) return;
  const question = byId('question').value.trim();
  if (!question || question.length > 500) return;
  const profile = agent;
  const lang = language;
  const state = states[profile];
  addMessage(profile, lang, 'user', question);
  state.draft = '';
  byId('question').value = '';
  setBusy(true);
  status('pending');
  renderHistory();
  try {
    const frame = await post('/api/conversation', {agent: profile, language: lang, question,
      evidence_source: profile === 'infrastructure' ? byId('scenario').value || null : null,
      conversation_id: state.id});
    const data = frame.response;
    if (!data || !data.presentation || !frame.report || !frame.budget_remaining || data.agent !== profile || data.language !== lang ||
      !['offline_simulation', 'gateway'].includes(data.mode) ||
      !['completed', 'clarification_required', 'refused', 'unavailable', 'blocked'].includes(data.status) ||
      !/^[0-9a-f-]{36}$/.test(frame.conversation_id)) throw new Error('Invalid response');
    state.id = frame.conversation_id;
    state.budget = frame.budget_remaining;
    const answer = data.answer ? data.answer.summary : data.question || t(data.reason || 'required_control_failed', lang);
    addMessage(profile, lang, 'assistant', answer, frame);
    status(data.status);
  } catch (_) {
    addMessage(profile, lang, 'assistant', t('failed', lang));
    status('failed');
    // Failure must not display an earlier turn's facts as the current answer.
    state.records.forEach((record) => { record.frame = null; });
  } finally {
    setBusy(false);
    renderHistory();
    byId('question').focus();
  }
});
byId('question').addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault();
    byId('question-form').requestSubmit();
  }
});
byId('new-conversation').addEventListener('click', async () => {
  if (busy || !csrf) return;
  const profile = agent;
  setBusy(true);
  try {
    const result = await post('/api/reset', {agent: profile, conversation_id: states[profile].id});
    if (result.reset !== true) throw new Error('Reset rejected');
    states[profile] = {id: null, records: [], budget: null, draft: ''};
    byId('question').value = '';
    status('resetDone');
  } catch (_) { status('failed'); }
  finally { setBusy(false); renderHistory(); byId('question').focus(); }
});
byId('download').addEventListener('click', () => {
  if (!selectedReport || busy) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(selectedReport, null, 2) + '\n'], {type: 'application/json'}));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'synthetic-' + agent + '-' + language + '-sanitized-turn-report.json';
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
async function bootstrap() {
  try {
    const responses = await Promise.all([
      fetch('/i18n.json', {cache: 'no-store', credentials: 'omit'}),
      fetch('/api/bootstrap', {cache: 'no-store', credentials: 'same-origin'})
    ]);
    if (responses.some((response) => !response.ok)) throw new Error('Unavailable');
    const [strings, data] = await Promise.all(responses.map(boundedJSON));
    if (!strings.en || !strings.ar || data.mode !== 'offline_simulation' || data.synthetic_only !== true || typeof data.csrf !== 'string') throw new Error('Boundary unavailable');
    catalog = strings;
    csrf = data.csrf;
    byId('language').disabled = false;
    statusCode = 'ready';
    applyLanguage();
    setBusy(false);
  } catch (_) {
    if (catalog) status('boundaryUnavailable');
    else byId('status').textContent = 'Private demo boundary unavailable';
  }
}
bootstrap();
