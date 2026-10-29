/* Financial UI. Transient conversation/drafts stay in this page, never in browser storage. */
(() => {
  'use strict';
  const {el, $} = Console;
  const CONSOLE = 'http://127.0.0.1:8080/#/agents/financial';
  let language = 'en', me = null, csrf = null, session = 0, bootSerial = 0;
  let paintAsk = () => {}, paintExpenses = () => {}, loginBusy = false, logoutBusy = false, authMessage = null;
  const L = (en, ar) => language === 'ar' ? ar : en;
  const fresh = () => ({messages: [], question: '', trace: null, elapsed: 0, askBusy: false, turn: 0,
    month: null, draft: {}, expenseBusy: false, expenseMessage: null});
  let state = fresh();
  const REASONS = {
    ungrounded_numbers: ['The answer contained a figure that is not in your records, so it was not shown. Try asking about a specific month.', 'احتوت الإجابة على رقم غير موجود في سجلاتك، فحُجبت. جرّب السؤال عن شهر محدد.'],
    ungrounded_claim: ['I can only answer from the expenses you entered. I cannot confirm invoices, payments, refunds or whether something is recorded.', 'أجيب من المصروفات التي أدخلتها فقط، ولا أستطيع تأكيد الفواتير أو المدفوعات أو الاستردادات أو حالة تسجيلها.'],
    rate_limited: ['The current process has reached its hourly question limit for you. This counter is held in memory and resets on restart.', 'وصلت إلى حد الأسئلة بالساعة في العملية الحالية. العداد في الذاكرة ويُصفّر عند إعادة التشغيل.'],
    token_budget_exhausted: ['The worker’s current in-memory daily token allowance is used up. It is not a durable quota across restarts.', 'استهلكت حصة رموز النموذج اليومية في ذاكرة العامل الحالي. لا يستمر هذا الحد عبر إعادة التشغيل.'],
    question_length: ['Questions must be 1–500 characters.', 'اكتب سؤالًا من حرف إلى ٥٠٠ حرف.'],
    redaction_unavailable: ['Identifier masking failed, so the affected model call was refused.', 'تعذّر إخفاء المعرّفات، فرُفض استدعاء النموذج المتأثر.'],
    model_unavailable: ['The AI model is unavailable right now.', 'النموذج غير متاح الآن.'],
    worker_unavailable: ['The worker did not return an answer. It may be unavailable; no request trace was returned.', 'لم يُرجع العامل إجابة. قد يكون غير متاح؛ ولم يصل أثر لهذا الطلب.'],
    step_limit: ['The agent took too many steps and stopped.', 'توقف الوكيل بعد بلوغ حد الخطوات.'],
    language: ['Choose English or Arabic.', 'اختر العربية أو الإنجليزية.'],
    tool_arguments_rejected: ['The agent asked for records in a way the platform does not allow, so it stopped.', 'توقف الوكيل لأن طلب السجلات لم يطابق القواعد المسموحة.']
  };
  const ERRORS = {
    wrong_username_or_password: ['Wrong username or password.', 'اسم المستخدم أو كلمة المرور غير صحيحة.'],
    too_many_attempts: ['Too many failed attempts. Sign-in throttling is held in the frontdoor’s memory and resets on restart. Try later.', 'محاولات دخول فاشلة كثيرة. تقييد الدخول في ذاكرة البوابة الأمامية ويُصفّر عند إعادة تشغيلها. حاول لاحقًا.'],
    username_and_password_required: ['Enter a username and a password.', 'أدخل اسم المستخدم وكلمة المرور.'],
    sign_in_required: ['Your session ended. Please sign in again.', 'انتهت جلستك. سجّل الدخول مجددًا.'],
    csrf_rejected: ['Session validation failed. Reload this page before retrying.', 'فشل التحقق من الجلسة. أعد تحميل الصفحة قبل المحاولة.'],
    origin_rejected: ['This address is not allowed. Open the supported local address.', 'هذا العنوان غير مسموح. افتح العنوان المحلي المدعوم.'],
    unreachable: ['No usable response arrived. Check the connection and try again.', 'لم تصل استجابة صالحة. تحقق من الاتصال وحاول مجددًا.'],
    invalid_response: ['The server returned an invalid response.', 'أرجع الخادم استجابة غير صالحة.']
  };
  const pair = (table, code, fallback) => table[code] ? L(...table[code]) : fallback;
  const errorText = code => pair(ERRORS, code, L('The request failed. Please review and retry.', 'فشل الطلب. راجعه ثم حاول مجددًا.'));
  const reasonText = code => pair(REASONS, code, L('The agent could not answer this safely, so nothing was shown.', 'تعذرت الإجابة ضمن القواعد، فلم يُعرض جواب.'));
  const money = minor => (minor / 100).toLocaleString(language, {minimumFractionDigits: 2, maximumFractionDigits: 2}) + L(' SAR', ' ر.س');
  const category = code => { const row = me?.schema?.categories?.find(item => item.code === code); return row?.labels?.[language] || code; };
  const words = value => String(value || '').replace(/_/g, ' ');
  const validTrace = trace => trace && typeof trace === 'object' && !Array.isArray(trace)
    && typeof trace.request_id === 'string' && trace.request_id.length > 0 && trace.request_id.length <= 128
    && trace.model && typeof trace.model.alias === 'string'
    && (!trace.tool_calls || (Array.isArray(trace.tool_calls) && trace.tool_calls.every(row => row && typeof row.tool_id === 'string')))
    && (!trace.redaction || (typeof trace.redaction === 'object' && typeof trace.redaction.calls === 'number'));
  function metadata() {
    const schema = me?.schema;
    if (!schema || !/^20\d\d-(?:0[1-9]|1[0-2])$/.test(schema.demo_month) || !Array.isArray(schema.categories) || !schema.categories.length
      || schema.categories.some(row => !/^[a-z_]+$/.test(row.code) || !row.labels?.en || !row.labels?.ar)
      || new Set(schema.categories.map(row => row.code)).size !== schema.categories.length) return null;
    return schema;
  }
  async function api(method, path, body) {
    const headers = {Accept: 'application/json'}, controller = new AbortController();
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (csrf) headers['X-CSRF'] = csrf;
    const timer = setTimeout(() => controller.abort(), path === '/api/ask' ? 80000 : 20000);
    try {
      const response = await fetch(path, {method, headers, signal: controller.signal, credentials: 'same-origin', body: body === undefined ? undefined : JSON.stringify(body)});
      Console.captureSource(response);
      let data;
      try { data = await response.json(); } catch { Console.observeAPI(response.status, false); return {ok: false, status: response.status, data: {error: 'invalid_response'}}; }
      if (!data || typeof data !== 'object' || Array.isArray(data)) { Console.observeAPI(response.status, false); return {ok: false, status: response.status, data: {error: 'invalid_response'}}; }
      // Not signed in yet is the normal answer to /api/me, not an API failure; the page shows the sign-in form.
      Console.observeAPI(response.status, true, path === '/api/me' && response.status === 401);
      return {ok: response.ok, status: response.status, data};
    } catch {
      Console.observeAPI(0);
      return {ok: false, status: 0, data: {error: 'unreachable'}};
    } finally { clearTimeout(timer); }
  }
  function expire() {
    ++session; me = csrf = null; state = fresh(); authMessage = 'sign_in_required'; start();
  }
  function bar() {
    $('tabs').hidden = $('logout').hidden = $('who').hidden = !me;
    if (me) $('who').textContent = me.name;
    $('logout').textContent = logoutBusy ? L('Signing out…', 'جارٍ الخروج…') : L('Sign out', 'تسجيل الخروج');
    $('logout').disabled = logoutBusy || state.askBusy || state.expenseBusy;
  }
  function costText(trace) {
    const source = (trace.cost_source === 'litellm_response_header' && Number.isInteger(trace.model_calls) && trace.model_calls > 0)
      || (trace.cost_source === 'no_model_call' && trace.model_calls === 0 && trace.cost_usd === 0);
    if (!source || typeof trace.cost_usd !== 'number' || !Number.isFinite(trace.cost_usd) || trace.cost_usd < 0) return L('cost unavailable', 'التكلفة غير متاحة');
    return trace.cost_usd > 0 && trace.cost_usd < 0.0001 ? '<$0.0001' : '$' + trace.cost_usd.toFixed(4);
  }
  function maskingBlocks() {
    const scope = language === 'ar' ? me?.masking_scope_ar : me?.masking_scope;
    if (!scope || !Array.isArray(scope.supported)) return [{label: L('Masking scope', 'نطاق الإخفاء'), text: L('The scope is unavailable. No masking coverage is inferred.', 'النطاق غير متاح. لا نفترض تغطية للإخفاء.')}];
    return [{label: L('Masking scope', 'نطاق الإخفاء'), text: scope.summary},
      {label: L('Supported patterns', 'الأنماط المدعومة'), node: el('ul', {}, scope.supported.map(row => el('li', {}, row.label, ' · ', el('bdi', {class: 'mono', dir: 'ltr'}, row.code))))},
      {label: L('Limits', 'الحدود'), text: scope.limits + ' ' + scope.additional}];
  }
  function maskingDetails(from) {
    Console.explain({eyebrow: L('EXPLAIN · MASKING SCOPE', 'شرح · نطاق الإخفاء'), title: L('Identifier masking scope', 'نطاق إخفاء المعرّفات'),
      blocks: maskingBlocks(), file: 'platform/core/src/agent_platform/masking_scope.py'}, from);
  }
  // These are the worker's reported steps, not independently joined boundary events.
  function steps(trace) {
    const out = [], tools = Array.isArray(trace.tool_calls) ? trace.tool_calls : [];
    const ex = (title, plain, how, reported, extra = []) => from => Console.explain({eyebrow: L("EXPLAIN · WORKER REPORT", "شرح · إفادة العامل"), title,
      copy: {label: L('request', 'الطلب'), value: trace.request_id},
      blocks: [{label: L("Source", "المصدر"), text: L("Produced by the worker for this request. This trace is not independent evidence that every boundary enforced its policy.", "أنتج العامل هذا الأثر للطلب. ليس دليلًا مستقلًا على أن كل حد طبّق سياسته.")},
        {label: L("In plain words", "بعبارة واضحة"), text: plain}, {label: L("How the current platform works", "كيف تعمل المنصة الحالية"), text: how},
        {label: L("Reported fields", "الحقول المبلّغ عنها"), node: el('pre', {class: 'code'}, reported.join('\n'))}, ...extra],
      file: 'platform/agents/financial/finance_agent/agent.py'}, from);
    if (trace.user_ref) out.push({mark: '·', kind: 'plain', text: L("Identity reference reported", "مرجع هوية أبلغ عنه العامل"), open: ex(L("Identity reference reported", "مرجع هوية أبلغ عنه العامل"),
      L("The worker included a pseudonymous user reference in its report.", "أدرج العامل مرجعًا مستعارًا للمستخدم في إفادته."),
      L("The trusted frontdoor authenticates the session. The broker checks capabilities bound to the user and worker; workers do not hold login or database credentials.", "تتحقق البوابة الأمامية الموثوقة من الجلسة. يتحقق وسيط البيانات من صلاحيات مرتبطة بالمستخدم والعامل؛ ولا يحمل العامل بيانات دخول أو اتصال بقاعدة البيانات."),
      ['user_ref: ' + trace.user_ref, 'outcome: ' + trace.outcome])});
    if (trace.redaction && trace.redaction.calls > 0) {
      // Each count is the number of identifier checks (redactor calls) in which the category appeared, not a number of
      // values: one IBAN checked in three calls is "found in 3 of 4 identifier checks", never "IBAN × 3".
      const checks = trace.redaction.calls;
      const found = Object.entries(trace.redaction.categories || {}).filter(([, count]) => count > 0)
        .map(([code, count]) => code + L(': found in ' + count + ' of ' + checks + ' identifier checks', ': ظهر في ' + count + ' من ' + checks + ' فحوص معرّفات'));
      const title = found.length ? L("Identifier masking reported", "إخفاء معرّفات أبلغ عنه العامل") : L("Identifier checks reported", "فحوص معرّفات أبلغ عنها العامل");
      out.push({mark: '·', kind: 'plain', text: title, open: ex(title,
        L("The worker reported redaction calls and the categories found. A call with no findings does not prove that text contained no sensitive data.", "أبلغ العامل عن استدعاءات الإخفاء والفئات المكتشفة. عدم اكتشاف شيء لا يثبت خلو النص من البيانات الحساسة."),
        L("The mandatory model boundary checks accepted messages before using private provider credentials. Unavailable redaction refuses that request.", "يفحص حد النموذج الإلزامي الرسائل المقبولة قبل استخدام بيانات المزوّد الخاصة. يُرفض الطلب عند تعذر الإخفاء."),
        ['identifier checks (redactor calls): ' + checks, ...(found.length ? found : ['categories found: none reported'])], maskingBlocks())});
    }
    if (trace.data_access) out.push({mark: '·', kind: 'plain', text: L("Scoped reads reported", "قراءات مقيّدة أبلغ عنها العامل"), open: ex(L("Scoped reads reported", "قراءات مقيّدة أبلغ عنها العامل"),
      L("The worker reported calls through the user-scoped data path.", "أبلغ العامل عن استدعاءات عبر مسار بيانات مقيّد بالمستخدم."),
      L("The trusted data broker checks an active signed capability and runs registered read-only tools under row-level security. This worker trace is not an independent broker event.", "يتحقق وسيط البيانات الموثوق من صلاحية موقّعة وسارية، ويشغّل أدوات قراءة مسجلة تحت أمان الصفوف. أثر العامل هذا ليس حدثًا مستقلًا من الوسيط."),
      ['reported role: ' + trace.data_access.role, 'reported scope: ' + trace.data_access.scoped_to,
        ...tools.map(tool => tool.tool_id + ': ' + tool.rows_returned + ' row(s)')])});
    if (trace.injection_result && trace.injection_result.question_instruction_like) out.push({mark: '!', kind: 'plain',
      text: L("Instruction-like question reported", "سؤال يشبه التعليمات أبلغ عنه العامل"), open: ex(L("Instruction-like question reported", "سؤال يشبه التعليمات أبلغ عنه العامل"),
        L("The worker marked the question as instruction-like. This flag is not a stored copy of the question.", "صنّف العامل السؤال على أنه يشبه التعليمات. هذه العلامة ليست نسخة مخزنة من السؤال."),
        L("Question text remains untrusted input. Registered tools, user scope and output checks still apply.", "يبقى نص السؤال مدخلًا غير موثوق، وتظل الأدوات المسجلة ونطاق المستخدم وفحوص المخرجات سارية."), ['question_instruction_like: true'])});
    if (trace.injection_result && trace.injection_result.withheld_fields) out.push({mark: '!', kind: 'plain',
      text: L("Field filtering reported", "ترشيح حقول أبلغ عنه العامل"), open: ex(L("Field filtering reported", "ترشيح حقول أبلغ عنه العامل"),
        L("The worker reported withholding fields recognized by its instruction-pattern filter.", "أبلغ العامل عن حجب حقول تعرف عليها مرشح أنماط التعليمات."),
        L("Pattern filtering does not recognize every instruction or prove what the model followed.", "لا يتعرف ترشيح الأنماط على كل التعليمات ولا يثبت ما اتبعه النموذج."),
        ['result: ' + words(trace.injection_result.result), 'withheld fields: ' + trace.injection_result.withheld_fields])});
    if (trace.grounding_result === 'grounded') out.push({mark: '·', kind: 'plain', text: L("Grounding check reported", "فحص استناد أبلغ عنه العامل"), open: ex(L("Grounding check reported", "فحص استناد أبلغ عنه العامل"),
      L("The worker reported that its figure and claim checks accepted the answer.", "أبلغ العامل أن فحوص الأرقام والادعاءات قبلت الإجابة."),
      L("These checks compare figures and selected claims with tool results; they do not prove every sentence is correct.", "تقارن هذه الفحوص الأرقام وادعاءات محددة بنتائج الأدوات؛ ولا تثبت صحة كل جملة."),
      ['grounding: grounded', 'tool calls: ' + tools.length])});
    else if (trace.grounding_result === 'ungrounded_claim_blocked') out.push({mark: '!', kind: 'plain', text: L("Grounding refusal reported", "رفض استناد أبلغ عنه العامل"),
      open: ex(L("Grounding refusal reported", "رفض استناد أبلغ عنه العامل"), L("The worker reported withholding an answer after its grounding checks.", "أبلغ العامل عن حجب الإجابة بعد فحوص الاستناد."),
        L("Figure and selected-claim checks run before an answer is shown.", "تجري فحوص الأرقام وادعاءات محددة قبل عرض الإجابة."), ['grounding: ungrounded claim blocked', 'reason: ' + words(trace.reason)])});
    if (trace.outcome === 'refused' || trace.outcome === 'blocked') out.push({mark: '!', kind: 'plain', text: L("Refusal reported: ", "رفض أبلغ عنه العامل: ") + reasonText(trace.reason),
      open: ex(L("Refusal reported", "رفض أبلغ عنه العامل"), reasonText(trace.reason),
        L("This is the reported result of this turn, not a statement about every service or request.", "هذه النتيجة المبلّغ عنها لهذه الجولة، وليست حكمًا على كل خدمة أو طلب."), ['outcome: ' + trace.outcome, 'reason: ' + words(trace.reason)])});
    return out;
  }

  function didPanel(state) {
    const list = el('ul', {}), foot = el('footer', {}, L("Worker-produced metadata.", "بيانات وصفية أنتجها العامل."));
    const panel = el('section', {class: 'panel did', 'aria-label': L("Worker request trace", "أثر طلب العامل")}, el('h2', {}, L("Worker request trace", "أثر طلب العامل")), list, foot);
    state.clear = text => {
      list.replaceChildren(el('li', {class: 'muted'}, text));
      foot.textContent = L('Worker-produced metadata.', 'بيانات وصفية أنتجها العامل.');
    };
    state.paint = (trace, elapsed) => {
      const rows = steps(trace);
      list.replaceChildren();
      rows.forEach(step => {
        const row = el('li', {}, el('button', {type: 'button', onclick: event => step.open(event.currentTarget), 'aria-label': step.text + L(" — details", " — التفاصيل")},
          el('span', {class: 'ring ' + step.kind, 'aria-hidden': 'true'}, step.mark), step.text));
        list.append(row);
      });
      foot.replaceChildren(el('span', {}, elapsed.toFixed(1) + L(" s · ", " ث · ") + (costText(trace) === L("cost unavailable", "التكلفة غير متاحة") ? L("cost unavailable", "التكلفة غير متاحة") : L("reported model cost ", "تكلفة نموذج أبلغ عنها العامل ") + costText(trace))),
        el('button', {type: 'button', class: 'btn link', onclick: event => Console.explain({eyebrow: L("EXPLAIN · WORKER REPORT", "شرح · إفادة العامل"), title: L("Request trace", "أثر الطلب"),
          copy: {label: L('request', 'الطلب'), value: trace.request_id},
          blocks: [{label: L("Source", "المصدر"), text: L("Worker-produced metadata returned with this answer. Boundary events are not independently joined into this trace.", "بيانات وصفية أنتجها العامل وأعادها مع الإجابة. لا يجمع هذا الأثر أحداث الحدود من مصادر مستقلة.")},
            {label: L("Audit scope", "نطاق الأحداث"), text: L("Components emit bounded request events. This trace does not prove complete recording, durable retention or an authentic record of every boundary decision.", "تصدر المكونات أحداث طلب محدودة. لا يثبت هذا الأثر اكتمال التسجيل أو الاحتفاظ الدائم أو صحة سجل كل قرار عند الحدود.")},
            {label: L("Reported fields", "الحقول المبلّغ عنها"), node: el('pre', {class: 'code'}, ['request_id: ' + trace.request_id, 'outcome: ' + trace.outcome,
              'model: ' + trace.model.alias + (trace.model.resolved ? ' → ' + trace.model.resolved : ''), 'model calls: ' + trace.model_calls,
              'tokens: ' + JSON.stringify(trace.tokens), 'model cost: ' + costText(trace), 'cost source: ' + (trace.cost_source || 'unavailable')].join('\n'))}],
          file: 'platform/agents/financial/finance_agent/agent.py'}, event.currentTarget)}, L("Request trace →", "أثر الطلب ←")));
    };
    return panel;
  }



  function askView(view) {
    const schema = metadata(), month = schema ? new Date(schema.demo_month + '-01T12:00:00Z').toLocaleDateString(language, {month: 'long', year: 'numeric', timeZone: 'UTC'}) : null;
    view.append(el('a', {class: 'hint', href: CONSOLE}, L('← Agent passport', 'جواز الوكيل ←')),
      Console.head(L('Ask. Review the trace.', 'اسأل. راجع الأثر.'), null, el('button', {type: 'button', class: 'btn link', onclick: event => maskingDetails(event.currentTarget)}, L('Masking scope →', 'نطاق الإخفاء ←'))));
    const log = el('div', {class: 'log', role: 'log', 'aria-live': 'polite'});
    const input = el('input', {id: 'q', type: 'text', maxlength: 500, autocomplete: 'off', value: state.question, placeholder: L('Ask about your expenses…', 'اسأل عن مصروفاتك…')});
    input.addEventListener('input', () => { state.question = input.value; });
    const send = el('button', {type: 'submit', class: 'btn inverse'}, L('Send', 'إرسال'));
    const didState = {}, did = didPanel(didState), controls = [send];
    async function ask(question) {
      question = question.trim();
      if (!question || state.askBusy || logoutBusy) return;
      const owner = session, current = state, turn = ++current.turn;
      current.askBusy = true; current.trace = null; current.messages.push({who: 'me', text: question}); current.question = '';
      input.value = ''; paintAsk(); bar();
      const t0 = performance.now(), r = await api('POST', '/api/ask', {question, language});
      if (owner !== session || current !== state || turn !== current.turn) return;
      current.askBusy = false;
      if (r.status === 401) { expire(); return; }
      if (r.ok && r.data.status === 'answered' && typeof r.data.answer === 'string') current.messages.push({who: 'bot', text: r.data.answer});
      else current.messages.push({who: 'err', reason: r.ok && ['blocked', 'refused'].includes(r.data.status) ? r.data.reason : null,
        error: r.ok ? 'invalid_response' : r.data.error});
      current.trace = r.ok && validTrace(r.data.trace) ? r.data.trace : null;
      current.elapsed = (performance.now() - t0) / 1000;
      paintAsk(); bar();
    }
    const chip = text => { const button = el('button', {type: 'button', onclick: () => ask(text)}, text); controls.push(button); return button; };
    view.append(el('div', {class: 'ask'}, el('section', {class: 'panel chat', 'aria-label': L('Conversation', 'المحادثة')}, log,
      el('div', {class: 'chips'}, ...(month ? [chip(L('How much did I spend in ' + month + '?', 'كم أنفقت في ' + month + '؟')),
        chip(L('Which category did I spend most on in ' + month + '?', 'ما أكثر فئة أنفقت عليها في ' + month + '؟'))] : [])),
      el('form', {class: 'send', onsubmit: event => { event.preventDefault(); ask(input.value); }}, el('div', {}, el('label', {for: 'q'}, L('Your question', 'سؤالك')), input), send)), did));
    paintAsk = () => {
      if (!view.isConnected || !me) return;
      controls.forEach(button => { button.disabled = state.askBusy || logoutBusy; });
      send.textContent = state.askBusy ? L('Waiting…', 'بانتظار الإجابة…') : L('Send', 'إرسال');
      log.replaceChildren(...state.messages.map(message => el('div', {class: 'msgbox ' + message.who, dir: 'auto', role: message.who === 'err' ? 'alert' : null},
        message.text || (message.reason ? reasonText(message.reason) : errorText(message.error)))));
      if (state.askBusy) log.append(el('div', {class: 'muted', role: 'status'}, L('Waiting for the worker…', 'بانتظار العامل…')));
      log.scrollTop = log.scrollHeight;
      if (state.trace) didState.paint(state.trace, state.elapsed);
      else didState.clear(state.askBusy ? L('This request is pending. No trace yet.', 'الطلب قيد الانتظار. لم يصل أثر بعد.')
        : state.messages.length ? L('No trace returned for this request.', 'لم يصل أثر لهذا الطلب.') : L('Ask a question to see worker-reported steps.', 'اسأل لعرض الخطوات التي أبلغ عنها العامل.'));
    };
    paintAsk();
  }

  function expensesView(view) {
    const schema = metadata();
    view.append(Console.head(L('Your expenses.', 'مصروفاتك.'), L('Only your own records. The agent can read them but never change them.', 'سجلاتك وحدك. يقرأها الوكيل ولا يغيّرها.')));
    if (!schema) { view.append(Console.empty(L('Form metadata unavailable.', 'بيانات النموذج غير متاحة.'), L('Reload before entering an expense. No categories or period are guessed.', 'أعد التحميل قبل الإضافة. لا نفترض فئات أو فترة.'))); return; }
    if (!state.month) state.month = schema.demo_month;
    const current = state, owner = session;
    const month = el('input', {id: 'month', type: 'month', value: state.month, min: '2020-01', max: '2035-12'});
    const body = el('div', {}), msg = el('div', {class: 'msg', role: 'status'});
    const save = el('button', {type: 'submit', class: 'btn inverse'}, L('Add', 'إضافة'));
    let loadSerial = 0;
    const add = el('form', {class: 'addform', onsubmit: async event => {
      event.preventDefault();
      if (current.expenseBusy || logoutBusy) return;
      const form = event.currentTarget, fields = Object.fromEntries(new FormData(form));
      current.expenseBusy = true; current.expenseMessage = null; paintExpenses(); bar();
      const r = await api('POST', '/api/expenses', fields);
      if (owner !== session || current !== state) return;
      current.expenseBusy = false;
      if (r.status === 401) { expire(); return; }
      if (r.ok && Number.isSafeInteger(r.data.id) && r.data.id > 0) {
        current.draft = {}; current.month = fields.spent_on.slice(0, 7); current.expenseMessage = {success: true};
      } else current.expenseMessage = {unknown: r.status === 0 || r.status >= 500 || r.ok || r.data.error === 'invalid_response', error: r.data.error};
      if (location.hash === '#/expenses') start(); else bar();
    }},
    ...[['spent_on', L('Date', 'التاريخ'), 'date'], ['merchant', L('Merchant', 'المتجر'), 'text'], ['amount', L('Amount (SAR)', 'المبلغ (ر.س)'), 'text'], ['note', L('Note', 'ملاحظة'), 'text']].map(([name, label, type]) =>
      el('div', {}, el('label', {for: 'f-' + name}, label), el('input', {id: 'f-' + name, name, type, required: name !== 'note' || null,
        value: current.draft[name] || '', maxlength: name === 'merchant' ? 60 : name === 'note' ? 200 : null,
        min: type === 'date' ? '2020-01-01' : null, max: type === 'date' ? '2035-12-31' : null,
        inputmode: name === 'amount' ? 'decimal' : null, dir: name === 'merchant' || name === 'note' ? 'auto' : 'ltr'}))),
    el('div', {}, el('label', {for: 'f-category'}, L('Category', 'الفئة')), el('select', {id: 'f-category', name: 'category'},
      schema.categories.map(row => el('option', {value: row.code, selected: row.code === current.draft.category}, row.labels[language])))), save);
    add.addEventListener('input', () => { current.draft = Object.fromEntries(new FormData(add)); });
    paintExpenses = () => {
      if (!view.isConnected) return;
      for (const field of add.elements) field.disabled = current.expenseBusy || logoutBusy;
      save.textContent = current.expenseBusy ? L('Saving…', 'جارٍ الحفظ…') : L('Add', 'إضافة');
      const result = current.expenseMessage;
      msg.textContent = !result ? '' : result.success ? L('Expense added.', 'أُضيف المصروف.') : result.unknown
        ? L('The save outcome is unknown. Check this month before submitting again; retrying may add a duplicate.', 'نتيجة الحفظ غير معروفة. راجع مصروفات الشهر قبل إعادة الإرسال؛ قد تؤدي المحاولة إلى تكرار الإضافة.')
        : errorText(result.error) + L(' Check the date, category, merchant and amount (0.01–100000.00 SAR, up to two decimals).', ' راجع التاريخ والفئة والمتجر والمبلغ (من 0.01 إلى 100000.00 ر.س، بمنزلتين عشريتين كحد أقصى).');
    };
    async function load() {
      const request = ++loadSerial, selected = month.value; current.month = selected;
      body.replaceChildren(el('p', {class: 'muted', role: 'status'}, L('Loading…', 'جارٍ التحميل…')));
      const r = await api('GET', '/api/expenses?month=' + encodeURIComponent(selected));
      if (owner !== session || current !== state || request !== loadSerial || !view.isConnected) return;
      if (r.status === 401) { expire(); return; }
      const list = r.data.expenses;
      if (!r.ok || !Array.isArray(list) || list.some(entry => !Number.isSafeInteger(entry.amount_minor) || entry.amount_minor < 0 || typeof entry.date !== 'string' || typeof entry.merchant !== 'string' || typeof entry.category !== 'string')) {
        body.replaceChildren(Console.empty(L('Could not load expenses.', 'تعذر تحميل المصروفات.'), errorText(r.data.error || 'invalid_response'))); return;
      }
      const total = list.reduce((sum, entry) => sum + entry.amount_minor, 0);
      body.replaceChildren(list.length ? el('div', {class: 'expense-table'}, el('table', {class: 'x'},
        el('thead', {}, el('tr', {}, [L('Date', 'التاريخ'), L('Merchant', 'المتجر'), L('Category', 'الفئة'), L('Amount', 'المبلغ')].map(label => el('th', {scope: 'col'}, label)))),
        el('tbody', {}, list.map(entry => el('tr', {}, el('td', {class: 'mono', dir: 'ltr'}, entry.date), el('td', {dir: 'auto'}, entry.merchant), el('td', {}, category(entry.category)), el('td', {class: 'mono'}, money(entry.amount_minor))))),
        el('tfoot', {}, el('tr', {}, el('td', {colspan: 3}, L('Total · ', 'الإجمالي · ') + list.length + L(' expense(s)', ' مصروف')), el('td', {class: 'mono'}, money(total))))))
        : Console.empty(L('No expenses in this month yet.', 'لا توجد مصروفات لهذا الشهر بعد.'), L('Add one below.', 'أضف مصروفًا أدناه.')));
    }
    month.addEventListener('change', load);
    view.append(el('section', {class: 'panel'}, el('div', {class: 'card-head'}, el('div', {}, el('label', {for: 'month'}, L('Month', 'الشهر')), month)), body, add, msg));
    paintExpenses(); load();
  }
  function loginView(view) {
    view.append(Console.head(L('Sign in.', 'سجّل الدخول.'), L('Each person sees only their own expenses. Temporary sign-in limits are held in frontdoor memory and reset on restart.', 'يرى كل شخص مصروفاته فقط. قيود الدخول المؤقتة في ذاكرة البوابة الأمامية وتُصفّر عند إعادة التشغيل.')));
    const msg = el('div', {class: 'msg', role: 'alert'}, authMessage ? errorText(authMessage) : '');
    const submit = el('button', {type: 'submit', class: 'btn inverse', disabled: loginBusy}, L('Sign in', 'دخول'));
    view.append(el('form', {class: 'panel login', onsubmit: async event => {
      event.preventDefault(); if (loginBusy) return;
      const owner = session, username = $('username').value.trim(), password = $('password').value;
      $('password').value = ''; loginBusy = true; submit.disabled = true;
      const r = await api('POST', '/api/login', {username, password});
      loginBusy = false;
      if (owner !== session) return;
      if (!r.ok || !validIdentity(r.data)) { authMessage = r.ok ? 'invalid_response' : r.data.error; start(); return; }
      ++session; state = fresh(); csrf = r.data.csrf; me = r.data; authMessage = null; start();
    }}, el('div', {}, el('label', {for: 'username'}, L('Username', 'اسم المستخدم')), el('input', {id: 'username', autocomplete: 'username', maxlength: 64, dir: 'ltr', required: true})),
    el('div', {}, el('label', {for: 'password'}, L('Password', 'كلمة المرور')), el('input', {id: 'password', type: 'password', autocomplete: 'current-password', maxlength: 128, required: true})), submit, msg));
  }
  const validIdentity = value => typeof value.name === 'string' && typeof value.csrf === 'string' && value.csrf.length > 0;
  function start() {
    paintAsk = () => {}; paintExpenses = () => {}; Console.close(); bar();
    const view = $('view'); view.replaceChildren();
    if (!me) { loginView(view); return; }
    if (authMessage) view.append(el('p', {class: 'msg', role: 'alert'}, errorText(authMessage)));
    const tab = location.hash === '#/expenses' ? 'expenses' : 'ask';
    document.querySelectorAll('nav.tabs a').forEach(link => { if (link.dataset.tab === tab) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current'); });
    (tab === 'ask' ? askView : expensesView)(view);
  }
  async function boot() {
    const serial = ++bootSerial, owner = session, r = await api('GET', '/api/me');
    if (serial !== bootSerial || owner !== session) return;
    me = r.ok && validIdentity(r.data) ? r.data : null; csrf = me?.csrf || null;
    authMessage = r.ok && !me ? 'invalid_response' : !r.ok && r.status !== 401 ? r.data.error : null;
    start();
  }
  function translate() {
    document.documentElement.lang = language; document.documentElement.dir = language === 'ar' ? 'rtl' : 'ltr';
    Console.setLanguage(language);
    document.title = L('Financial Agent · Agent Runtime Platform', 'الوكيل المالي · منصة تشغيل الوكلاء');
    document.querySelector('meta[name=description]').content = L('Your own expenses through the governed agent platform.', 'مصروفاتك عبر منصة الوكلاء المحكومة.');
    $('brand').textContent = L('Agent Runtime Platform', 'منصة تشغيل الوكلاء');
    $('skip').textContent = L('Skip to content', 'انتقل إلى المحتوى');
    $('tabs').setAttribute('aria-label', L('Screens', 'الشاشات'));
    document.querySelector('[data-tab="ask"]').textContent = L('Ask', 'اسأل');
    document.querySelector('[data-tab="expenses"]').textContent = L('Expenses', 'المصروفات');
    $('language').value = language; $('language').setAttribute('aria-label', L('Language', 'اللغة'));
  }
  $('language').addEventListener('change', event => { language = event.target.value === 'ar' ? 'ar' : 'en'; translate(); start(); });
  $('logout').addEventListener('click', async () => {
    if (logoutBusy || state.askBusy || state.expenseBusy) return;
    logoutBusy = true; bar(); paintAsk(); paintExpenses();
    const owner = session, r = await api('POST', '/api/logout', {});
    logoutBusy = false;
    if (owner !== session) return;
    if (r.status === 401) { expire(); return; }
    if (!r.ok || r.data.signed_out !== true) {
      authMessage = r.ok ? 'invalid_response' : r.data.error;
      start();
      const notice = el('p', {class: 'msg', role: 'alert'}, L('Sign-out was not confirmed. This screen remains signed in; retry or reload to check the session.', 'لم يتأكد تسجيل الخروج. تبقى الشاشة في حالة دخول؛ حاول مجددًا أو أعد التحميل للتحقق من الجلسة.'));
      $('view').prepend(notice); return;
    }
    ++session; me = csrf = null; state = fresh(); authMessage = null; start();
  });
  window.addEventListener('hashchange', () => { if (me) start(); });
  translate(); boot();
})();
