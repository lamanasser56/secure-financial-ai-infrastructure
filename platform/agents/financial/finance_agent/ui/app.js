/* Financial Agent UI: real sign-in, chat, and "What the platform did" built from the /api/ask trace. Same design as the console. */
(() => {
  'use strict';
  const {el, $} = Console;
  const CONSOLE = 'http://127.0.0.1:8080/#/agents/financial';  // the console (kubectl port-forward), where this agent's passport is
  const REASONS = {
    ungrounded_numbers: 'The answer contained a figure that is not in your records, so it was not shown. Try asking about a specific month.',
    ungrounded_claim: 'I can only answer from the expenses you entered. I cannot confirm invoices, payments, refunds or whether something is recorded.',
    rate_limited: 'You reached the limit of 20 questions per hour.', token_budget_exhausted: 'Your daily AI budget is used up. Try again tomorrow.',
    question_length: 'Questions must be 1–500 characters.', redaction_unavailable: 'Privacy masking is unavailable right now, so nothing was sent to the AI model.',
    model_unavailable: 'The AI model is unavailable right now.', step_limit: 'The agent took too many steps and stopped.',
    tool_arguments_rejected: 'The agent asked for records in a way the platform does not allow, so it stopped.'
  };
  const ERRORS = {wrong_username_or_password: 'Wrong username or password.', too_many_attempts: 'Too many wrong attempts for this name. Try again in 15 minutes.',
    username_and_password_required: 'Enter a username and a password.', sign_in_required: 'Your session ended. Please sign in again.'};
  const CATEGORIES = ['food', 'transport', 'shopping', 'bills', 'subscriptions', 'health', 'travel', 'other'];
  let csrf = null, me = null;

  async function api(method, path, body) {
    const headers = {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (csrf) headers['X-CSRF'] = csrf;
    try {
      const response = await fetch(path, {method, headers, credentials: 'same-origin', body: body === undefined ? undefined : JSON.stringify(body)});
      Console.captureSource(response);
      const data = await response.json();
      Console.setLive(response.ok || response.status < 500);
      return {ok: response.ok, status: response.status, data};
    } catch (e) {
      Console.setLive(false);
      return {ok: false, status: 0, data: {error: 'unreachable'}};
    }
  }
  const money = minor => (minor / 100).toLocaleString('en', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' SAR';
  const words = s => String(s || '').replace(/_/g, ' ');

  // ---- What the platform did: each step exists only if the trace says it happened -------------------------------------------------
  function steps(trace) {
    const out = [];
    const ex = (title, plain, how, proof, without) => from => Console.explain({eyebrow: 'EXPLAIN · FROM THIS REQUEST', live: true, title, copy: {label: 'request', value: trace.request_id},
      blocks: [{label: 'In plain words', text: plain}, {label: 'How it works', text: how}, {label: 'Proof · this request\'s trace', node: el('pre', {class: 'code'}, proof.join('\n'))},
               {label: 'Without it', text: without, cls: 'without'}], file: 'platform/agents/financial/finance_agent/agent.py'}, from);
    out.push({mark: '✓', kind: 'allowed', text: 'Checked who you are', open: ex('Checked who you are', 'The platform knew who was asking before it touched any data.',
      'Your session cookie is signed and expires. Every request is checked, and your pseudonymous user reference is used instead of your name.',
      ['user_ref: ' + trace.user_ref, 'outcome: ' + trace.outcome], 'Anyone could ask as anyone.')});
    if (trace.redaction && trace.redaction.calls > 0) {
      const found = Object.entries(trace.redaction.categories).map(([k, v]) => k + ' × ' + v);
      out.push({mark: '✓', kind: 'allowed', text: 'Hid personal data from the model', open: ex('Hid personal data from the model', 'Personal data was masked before any text reached the AI model.',
        'Every model request goes through the platform redactor first. If the redactor fails, the request is not sent.',
        ['redactor calls: ' + trace.redaction.calls, 'categories found: ' + (found.join(', ') || 'none')], 'Names, emails and numbers would reach the model.')});
    }
    if (trace.data_access) {
      out.push({mark: '✓', kind: 'allowed', text: 'Read only your own rows', open: ex('Read only your own rows', 'The agent could read only your own records.',
        'The tools run as a read-only database role under row-level security, scoped to your user reference.',
        ['role: ' + trace.data_access.role, 'scoped_to: ' + trace.data_access.scoped_to, ...trace.tool_calls.map(t => t.tool_id + ': ' + t.rows_returned + ' row(s)')],
        "The agent could be tricked into reading someone else's expenses.")});
    }
    if (trace.injection_result && trace.injection_result.question_instruction_like) {
      out.push({mark: '!', kind: 'plain', text: 'Your question contained instruction-like text', open: ex('Your question contained instruction-like text',
        'Text you pasted (an invoice, an email) reads like an order to the assistant. It was sent as your question, and recorded.',
        'Your own question is never withheld. The answer is still limited to read-only tools, your own rows and the checks on figures and claims.',
        ['question_instruction_like: true'], 'A pasted document could carry someone else\'s instructions.')});
    }
    if (trace.injection_result && trace.injection_result.withheld_fields) {
      out.push({mark: '!', kind: 'denied', text: 'Ignored orders hidden in the data', open: ex('Ignored orders hidden in the data', 'Text in your records that looked like an instruction was withheld from the model.',
        'Record fields are screened before the model sees them. Instruction-like text is replaced and never followed.',
        ['result: ' + words(trace.injection_result.result), 'withheld fields: ' + trace.injection_result.withheld_fields], 'A merchant name could give the model orders.')});
    }
    if (trace.grounding_result === 'grounded') {
      out.push({mark: '✓', kind: 'allowed', text: 'Matched the number to the data', open: ex('Matched the number to the data', 'Every figure in the answer was found in your records.',
        'The answer is checked against the tool results before it is shown. An unmatched figure blocks the answer.',
        ['grounding: grounded', 'tool calls: ' + (trace.tool_calls.length || 'none')], 'The model could state a number that is not in your data.')});
    } else if (trace.grounding_result === 'ungrounded_claim_blocked') {
      out.push({mark: '!', kind: 'denied', text: 'Stopped an answer the data did not support', open: ex('Stopped an answer the data did not support', 'The answer made a claim your records do not support, so it was not shown.',
        'The answer is checked against the tool results before it is shown.', ['grounding: ungrounded claim blocked', 'reason: ' + words(trace.reason)], 'A made-up claim would look like a fact.')});
    }
    if (trace.outcome === 'refused') {
      out.push({mark: '!', kind: 'denied', text: 'Refused: ' + words(trace.reason), open: ex('Refused', REASONS[trace.reason] || 'The request was refused before any answer.',
        'Limits and checks run before and after the model.', ['outcome: refused', 'reason: ' + words(trace.reason)], 'Limits could be bypassed.')});
    }
    return out;
  }

  function didPanel(state) {
    const list = el('ul', {}), foot = el('footer', {});
    const panel = el('section', {class: 'panel did', 'aria-label': 'What the platform did'}, el('h2', {}, 'What the platform did'), list, foot);
    state.paint = (trace, elapsed) => {
      const rows = steps(trace);
      list.replaceChildren();
      rows.forEach((s, i) => {
        const li = el('li', {}, el('button', {type: 'button', onclick: e => s.open(e.currentTarget), 'aria-label': s.text + ' — how it works'},
          el('span', {class: 'ring ' + s.kind, 'aria-hidden': 'true'}, s.mark), s.text));
        if (Console.reduced()) list.append(li); else setTimeout(() => list.append(li), i * 160);  // fills row by row, as the controls ran
      });
      foot.replaceChildren(el('span', {}, elapsed.toFixed(1) + ' s · ' + (trace.cost_usd === null ? 'cost unavailable' : '$' + trace.cost_usd.toFixed(4))),
        el('button', {type: 'button', class: 'btn link', onclick: e => Console.explain({eyebrow: 'EXPLAIN · FROM THIS REQUEST', live: true, title: 'Audit record', copy: {label: 'request', value: trace.request_id},
          blocks: [{label: 'In plain words', text: 'One line per request is written to the audit log. It holds ids, counts and codes, never your question or the answer.'},
                   {label: 'How it works', text: 'This is the same object that was audited and returned to you.'},
                   {label: 'Proof · this request\'s trace', node: el('pre', {class: 'code'}, [
                     'request_id: ' + trace.request_id, 'outcome: ' + trace.outcome, 'model: ' + trace.model.alias + (trace.model.resolved ? ' → ' + trace.model.resolved : ''),
                     'model calls: ' + trace.model_calls, 'tokens: ' + trace.tokens, 'cost: ' + (trace.cost_usd === null ? '—' : trace.cost_usd) + ' (' + trace.cost_source + ')'].join('\n'))}],
          file: 'platform/agents/financial/finance_agent/agent.py'}, e.currentTarget)}, 'Audit record →'));
    };
    return panel;
  }

  function askView(view) {
    const now = new Date(), month = now.toLocaleString('en', {month: 'long'}) + ' ' + now.getFullYear();
    view.append(el('a', {class: 'hint', href: CONSOLE}, '← Financial Agent'), Console.head('Ask. Then see what protected you.', null));
    const log = el('div', {class: 'log', role: 'log', 'aria-live': 'polite'});
    const input = el('input', {id: 'q', type: 'text', maxlength: 500, autocomplete: 'off', placeholder: 'Ask about your expenses…'});
    const send = el('button', {type: 'submit', class: 'btn inverse'}, 'Send');
    const state = {}, did = didPanel(state);
    async function ask(question) {
      if (!question.trim()) return;
      log.append(el('div', {class: 'msgbox me'}, question));
      input.value = ''; send.disabled = true;
      const t0 = performance.now();
      const r = await api('POST', '/api/ask', {question, language: 'en'});
      send.disabled = false;
      if (r.status === 401) { await boot(); return; }
      if (r.ok && r.data.status === 'answered') log.append(el('div', {class: 'msgbox bot'}, r.data.answer));
      else log.append(el('div', {class: 'msgbox err', role: 'alert'}, r.ok ? (REASONS[r.data.reason] || 'The agent could not answer this safely, so nothing was shown.') : (ERRORS[r.data.error] || 'Something went wrong. Nothing was changed.')));
      log.scrollTop = log.scrollHeight;
      if (r.ok && r.data.trace) state.paint(r.data.trace, (performance.now() - t0) / 1000);
    }
    const chip = (text, cls) => el('button', {type: 'button', class: cls || '', onclick: () => ask(text)}, text);
    view.append(el('div', {class: 'ask'}, el('section', {class: 'panel chat', 'aria-label': 'Conversation'}, log,
      el('div', {class: 'chips'}, chip('How much did I spend in ' + month + '?'), chip('Which category did I spend most on in October 2026?')),
      el('form', {class: 'send', onsubmit: e => { e.preventDefault(); ask(input.value); }}, el('div', {}, el('label', {for: 'q'}, 'Your question'), input), send)), did));
    did.querySelector('ul').append(el('li', {class: 'muted'}, 'Ask a question to see what the platform did.'));
  }

  async function expensesView(view) {
    view.append(Console.head('Your expenses.', 'Only your own records. The agent can read them but never change them.'));
    const month = el('input', {id: 'month', type: 'month', value: new Date().toISOString().slice(0, 7)});
    const body = el('div', {});
    const add = el('form', {class: 'addform', onsubmit: async e => {
      e.preventDefault();
      const f = Object.fromEntries(new FormData(e.target));
      const r = await api('POST', '/api/expenses', {spent_on: f.spent_on, merchant: f.merchant, category: f.category, amount: f.amount, note: f.note});
      msg.textContent = r.ok ? 'Expense added.' : (r.data.error || 'Something went wrong. Nothing was changed.');
      if (r.ok) { e.target.reset(); month.value = f.spent_on.slice(0, 7); load(); }
    }},
      ...[['spent_on', 'Date', 'date'], ['merchant', 'Merchant', 'text'], ['amount', 'Amount (SAR)', 'text'], ['note', 'Note', 'text']].map(([n, l, t]) =>
        el('div', {}, el('label', {for: 'f-' + n}, l), el('input', {id: 'f-' + n, name: n, type: t, required: n !== 'note' || null}))),
      el('div', {}, el('label', {for: 'f-category'}, 'Category'), el('select', {id: 'f-category', name: 'category'}, CATEGORIES.map(c => el('option', {value: c}, c)))),
      el('button', {type: 'submit', class: 'btn inverse'}, 'Add'));
    const msg = el('div', {class: 'msg', role: 'status'});
    async function load() {
      const r = await api('GET', '/api/expenses?month=' + encodeURIComponent(month.value));
      if (r.status === 401) { await boot(); return; }
      if (!r.ok) { body.replaceChildren(Console.empty('Could not load expenses.', ERRORS[r.data.error] || r.data.error || '')); return; }
      const list = r.data.expenses, total = list.reduce((a, e) => a + e.amount_minor, 0);
      body.replaceChildren(list.length ? el('table', {class: 'x'}, el('thead', {}, el('tr', {}, ['Date', 'Merchant', 'Category', 'Amount'].map(h => el('th', {scope: 'col'}, h)))),
        el('tbody', {}, list.map(e => el('tr', {}, el('td', {class: 'mono'}, e.date), el('td', {}, e.merchant), el('td', {}, e.category), el('td', {class: 'mono'}, money(e.amount_minor))))),
        el('tfoot', {}, el('tr', {}, el('td', {colspan: 3}, 'Total · ' + list.length + ' expense(s)'), el('td', {class: 'mono'}, money(total)))))
        : Console.empty('No expenses in this month yet.', 'Add one below.'));
    }
    month.addEventListener('change', load);
    view.append(el('section', {class: 'panel'}, el('div', {class: 'card-head'}, el('div', {}, el('label', {for: 'month'}, 'Month'), month)), body, add, msg));
    load();
  }

  function loginView(view) {
    view.append(Console.head('Sign in.', 'Each person sees only their own expenses. Five wrong passwords lock that name for 15 minutes.'));
    const msg = el('div', {class: 'msg', role: 'alert'});
    view.append(el('form', {class: 'panel login', onsubmit: async e => {
      e.preventDefault();
      const r = await api('POST', '/api/login', {username: $('username').value.trim(), password: $('password').value});
      $('password').value = '';
      if (!r.ok) { msg.textContent = ERRORS[r.data.error] || 'Something went wrong. Nothing was changed.'; return; }
      csrf = r.data.csrf; me = r.data; start();
    }}, el('div', {}, el('label', {for: 'username'}, 'Username'), el('input', {id: 'username', autocomplete: 'username', maxlength: 64, required: true})),
      el('div', {}, el('label', {for: 'password'}, 'Password'), el('input', {id: 'password', type: 'password', autocomplete: 'current-password', maxlength: 128, required: true})),
      el('button', {type: 'submit', class: 'btn inverse'}, 'Sign in'), msg));
  }

  function start() {
    $('tabs').hidden = $('logout').hidden = $('who').hidden = !me;
    if (me) $('who').textContent = me.name;
    const view = $('view');
    view.replaceChildren();
    if (!me) { loginView(view); return; }
    const tab = location.hash === '#/expenses' ? 'expenses' : 'ask';
    document.querySelectorAll('nav.tabs a').forEach(a => { if (a.dataset.tab === tab) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    Console.close();
    (tab === 'ask' ? askView : expensesView)(view);
  }
  async function boot() {
    const r = await api('GET', '/api/me');
    me = r.ok ? r.data : null; csrf = r.ok ? r.data.csrf : null;
    start();
  }
  $('logout').addEventListener('click', async () => { await api('POST', '/api/logout', {}); me = csrf = null; start(); });
  window.addEventListener('hashchange', () => { if (me) start(); });
  boot();
})();
