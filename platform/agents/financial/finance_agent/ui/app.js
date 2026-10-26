/* Financial Agent UI: real sign-in, chat, and worker-reported steps from the /api/ask trace. Same design as the console. */
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

  function costText(trace) {
    const source = (trace.cost_source === 'litellm_response_header' && Number.isInteger(trace.model_calls) && trace.model_calls > 0)
      || (trace.cost_source === 'no_model_call' && trace.model_calls === 0 && trace.cost_usd === 0);
    if (!source || typeof trace.cost_usd !== 'number' || !Number.isFinite(trace.cost_usd) || trace.cost_usd < 0) return 'cost unavailable';
    return trace.cost_usd > 0 && trace.cost_usd < 0.0001 ? '<$0.0001' : '$' + trace.cost_usd.toFixed(4);
  }
  function maskingBlocks() {
    const scope = me && me.masking_scope;
    if (!scope || !Array.isArray(scope.supported)) return [{label: 'Masking scope', text: 'The scope is unavailable. No masking coverage is inferred.'}];
    return [{label: 'Masking scope', text: scope.summary},
      {label: 'Supported patterns', node: el('ul', {}, scope.supported.map(row => el('li', {}, row.label, ' · ', el('span', {class: 'mono'}, row.code))))},
      {label: 'Limits', text: scope.limits + ' ' + scope.additional}];
  }
  function maskingDetails(from) {
    Console.explain({eyebrow: 'EXPLAIN · MASKING SCOPE', title: 'Identifier masking scope',
      blocks: maskingBlocks(), file: 'platform/core/src/agent_platform/masking_scope.py'}, from);
  }

  // These are the worker's reported steps, not independently joined boundary events.
  function steps(trace) {
    const out = [], tools = Array.isArray(trace.tool_calls) ? trace.tool_calls : [];
    const ex = (title, plain, how, reported, extra = []) => from => Console.explain({eyebrow: 'EXPLAIN · WORKER REPORT', title,
      copy: {label: 'request', value: trace.request_id},
      blocks: [{label: 'Source', text: 'Produced by the worker for this request. This trace is not independent evidence that every boundary enforced its policy.'},
        {label: 'In plain words', text: plain}, {label: 'How the current platform works', text: how},
        {label: 'Reported fields', node: el('pre', {class: 'code'}, reported.join('\n'))}, ...extra],
      file: 'platform/agents/financial/finance_agent/agent.py'}, from);
    if (trace.user_ref) out.push({mark: '·', kind: 'plain', text: 'Identity reference reported', open: ex('Identity reference reported',
      'The worker included a pseudonymous user reference in its report.',
      'The trusted frontdoor authenticates the session. The broker checks capabilities bound to the user and worker; workers do not hold login or database credentials.',
      ['user_ref: ' + trace.user_ref, 'outcome: ' + trace.outcome])});
    if (trace.redaction && trace.redaction.calls > 0) {
      const found = Object.entries(trace.redaction.categories || {}).filter(([, count]) => count > 0).map(([code, count]) => code + ' × ' + count);
      const title = found.length ? 'Identifier masking reported' : 'Identifier checks reported';
      out.push({mark: '·', kind: 'plain', text: title, open: ex(title,
        'The worker reported redaction calls and the categories found. A call with no findings does not prove that text contained no sensitive data.',
        'The mandatory model boundary checks accepted messages before using private provider credentials. Unavailable redaction refuses that request.',
        ['redactor calls: ' + trace.redaction.calls, 'categories found: ' + (found.join(', ') || 'none reported')], maskingBlocks())});
    }
    if (trace.data_access) out.push({mark: '·', kind: 'plain', text: 'Scoped reads reported', open: ex('Scoped reads reported',
      'The worker reported calls through the user-scoped data path.',
      'The trusted data broker checks an active signed capability and runs registered read-only tools under row-level security. This worker trace is not an independent broker event.',
      ['reported role: ' + trace.data_access.role, 'reported scope: ' + trace.data_access.scoped_to,
        ...tools.map(tool => tool.tool_id + ': ' + tool.rows_returned + ' row(s)')])});
    if (trace.injection_result && trace.injection_result.question_instruction_like) out.push({mark: '!', kind: 'plain',
      text: 'Instruction-like question reported', open: ex('Instruction-like question reported',
        'The worker marked the question as instruction-like. This flag is not a stored copy of the question.',
        'Question text remains untrusted input. Registered tools, user scope and output checks still apply.', ['question_instruction_like: true'])});
    if (trace.injection_result && trace.injection_result.withheld_fields) out.push({mark: '!', kind: 'plain',
      text: 'Field filtering reported', open: ex('Field filtering reported',
        'The worker reported withholding fields recognized by its instruction-pattern filter.',
        'Pattern filtering does not recognize every instruction or prove what the model followed.',
        ['result: ' + words(trace.injection_result.result), 'withheld fields: ' + trace.injection_result.withheld_fields])});
    if (trace.grounding_result === 'grounded') out.push({mark: '·', kind: 'plain', text: 'Grounding check reported', open: ex('Grounding check reported',
      'The worker reported that its figure and claim checks accepted the answer.',
      'These checks compare figures and selected claims with tool results; they do not prove every sentence is correct.',
      ['grounding: grounded', 'tool calls: ' + tools.length])});
    else if (trace.grounding_result === 'ungrounded_claim_blocked') out.push({mark: '!', kind: 'plain', text: 'Grounding refusal reported',
      open: ex('Grounding refusal reported', 'The worker reported withholding an answer after its grounding checks.',
        'Figure and selected-claim checks run before an answer is shown.', ['grounding: ungrounded claim blocked', 'reason: ' + words(trace.reason)])});
    if (trace.outcome === 'refused' || trace.outcome === 'blocked') out.push({mark: '!', kind: 'plain', text: 'Refusal reported: ' + words(trace.reason),
      open: ex('Refusal reported', REASONS[trace.reason] || 'The worker reported a refusal.',
        'This is the reported result of this turn, not a statement about every service or request.', ['outcome: ' + trace.outcome, 'reason: ' + words(trace.reason)])});
    return out;
  }

  function didPanel(state) {
    const list = el('ul', {}), foot = el('footer', {}, 'Worker-produced metadata.');
    const panel = el('section', {class: 'panel did', 'aria-label': 'Worker request trace'}, el('h2', {}, 'Worker request trace'), list, foot);
    state.paint = (trace, elapsed) => {
      const rows = steps(trace);
      list.replaceChildren();
      rows.forEach((step, index) => {
        const row = el('li', {}, el('button', {type: 'button', onclick: event => step.open(event.currentTarget), 'aria-label': step.text + ' — details'},
          el('span', {class: 'ring ' + step.kind, 'aria-hidden': 'true'}, step.mark), step.text));
        if (Console.reduced()) list.append(row); else setTimeout(() => list.append(row), index * 160);
      });
      foot.replaceChildren(el('span', {}, elapsed.toFixed(1) + ' s · ' + (costText(trace) === 'cost unavailable' ? 'cost unavailable' : 'reported model cost ' + costText(trace))),
        el('button', {type: 'button', class: 'btn link', onclick: event => Console.explain({eyebrow: 'EXPLAIN · WORKER REPORT', title: 'Request trace',
          copy: {label: 'request', value: trace.request_id},
          blocks: [{label: 'Source', text: 'Worker-produced metadata returned with this answer. Boundary events are not independently joined into this trace.'},
            {label: 'Audit scope', text: 'Components emit bounded request events. This trace does not prove complete recording, durable retention or an authentic record of every boundary decision.'},
            {label: 'Reported fields', node: el('pre', {class: 'code'}, ['request_id: ' + trace.request_id, 'outcome: ' + trace.outcome,
              'model: ' + trace.model.alias + (trace.model.resolved ? ' → ' + trace.model.resolved : ''), 'model calls: ' + trace.model_calls,
              'tokens: ' + JSON.stringify(trace.tokens), 'model cost: ' + costText(trace), 'cost source: ' + (trace.cost_source || 'unavailable')].join('\n'))}],
          file: 'platform/agents/financial/finance_agent/agent.py'}, event.currentTarget)}, 'Request trace →'));
    };
    return panel;
  }

  function askView(view) {
    const now = new Date(), month = now.toLocaleString('en', {month: 'long'}) + ' ' + now.getFullYear();
    view.append(el('a', {class: 'hint', href: CONSOLE}, '← Financial Agent'), Console.head('Ask. Review the trace.', null, el('button', {type: 'button', class: 'btn link', onclick: event => maskingDetails(event.currentTarget)}, 'Masking scope →')));
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
    did.querySelector('ul').append(el('li', {class: 'muted'}, 'Ask a question to see worker-reported steps.'));
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
