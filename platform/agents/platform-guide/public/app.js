/* Guide state is transient in this page. Source excerpts are data, never HTML. */
(() => {
  'use strict';
  const {el, $} = Console;
  let language = 'en', busy = false, infoBusy = false, info = null, infoError = false, result = null, failure = null;
  const L = (en, ar) => language === 'ar' ? ar : en;
  const record = value => value && typeof value === 'object' && !Array.isArray(value);
  const sha = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
  const commit = value => value === null || (typeof value === 'string' && /^[0-9a-f]{40}$/.test(value));
  const path = value => typeof value === 'string' && /^docs\/(?:[A-Za-z0-9][A-Za-z0-9_.-]*\/)*[A-Za-z0-9][A-Za-z0-9_.-]*\.md$/.test(value);
  const corpus = value => record(value) && typeof value.id === 'string' && /^[a-z][a-z0-9-]{2,60}$/.test(value.id)
    && typeof value.reviewed_at === 'string' && /^20\d\d-\d\d-\d\d$/.test(value.reviewed_at) && sha(value.manifest_sha256);
  const TYPES = {
    CREDIT_CARD: ['Payment card numbers', 'أرقام بطاقات الدفع'], EMAIL_ADDRESS: ['Email addresses', 'عناوين البريد الإلكتروني'],
    IBAN_CODE: ['IBANs', 'أرقام الآيبان'], PHONE_NUMBER: ['Phone numbers', 'أرقام الهاتف'],
    SAUDI_BANK_ACCOUNT: ['Saudi bank account numbers', 'أرقام الحسابات البنكية السعودية'],
    SAUDI_NATIONAL_ID: ['Saudi national IDs', 'أرقام الهوية الوطنية السعودية'],
    SAUDI_RESIDENT_ID: ['Saudi resident IDs', 'أرقام الإقامة السعودية'], SAUDI_VAT_ID: ['Saudi VAT IDs', 'الأرقام الضريبية السعودية'],
  };
  const REASONS = {
    not_covered: ['The available documentation does not cover this question. Try a question about the platform.', 'لا تغطي الوثائق المتاحة هذا السؤال. جرّب سؤالًا عن المنصة.'],
    rate_limited: ['The current Guide process has reached its hourly question limit. This in-memory counter resets on restart.', 'بلغت عملية الدليل الحالية حد الأسئلة بالساعة. العداد في الذاكرة ويُصفّر عند إعادة التشغيل.'],
    token_budget_exhausted: ['The current Guide process has used its in-memory daily token allowance. This is not a durable quota.', 'استهلكت عملية الدليل الحالية حصة الرموز اليومية في الذاكرة. ليست حصة دائمة.'],
    question_length: ['Enter a question of 1–500 characters.', 'اكتب سؤالًا من حرف إلى ٥٠٠ حرف.'],
    language: ['Choose English or Arabic.', 'اختر العربية أو الإنجليزية.'],
    redaction_unavailable: ['Identifier masking failed, so the affected model call or displayed excerpt was refused.', 'تعذّر فحص إخفاء المعرّفات، فرُفض استدعاء النموذج أو المقتطف المتأثر.'],
    model_unavailable: ['The model is unavailable. Your question is kept so you can retry.', 'النموذج غير متاح. احتُفظ بسؤالك لتتمكن من إعادة المحاولة.'],
    model_reply_incomplete: ['The model did not return a complete source selection. No excerpts were released.', 'لم يُرجع النموذج اختيار مصادر كاملًا. لم تُعرض مقتطفات.'],
    unsupported_answer: ['The model added unsupported text or an invalid source selection, so it was refused.', 'أضاف النموذج نصًا غير مسند أو اختيار مصادر غير صالح، فرُفضت النتيجة.'],
    unknown_source: ['The model selected a source outside this request’s available passages. It was refused.', 'اختار النموذج مصدرًا خارج مقتطفات هذا الطلب، فرُفضت النتيجة.'],
    tool_not_allowed: ['The model attempted a tool call instead of selecting documentation. It was refused.', 'حاول النموذج استدعاء أداة بدل اختيار الوثائق، فرُفضت النتيجة.'],
    source_context_too_large: ['The source context did not fit this request. Try a shorter, more specific question.', 'لم يتسع الطلب لسياق المصادر. جرّب سؤالًا أقصر وأكثر تحديدًا.'],
  };
  const errorText = code => code === 'timeout'
    ? L('The request timed out. Its result is unknown; your question is kept. Retry when ready.', 'انتهت مهلة الطلب ونتيجته غير معروفة. احتُفظ بسؤالك؛ أعد المحاولة عندما تكون جاهزًا.')
    : code === 'invalid' ? L('The server returned an invalid response. Your question is kept; try again.', 'أرجع الخادم استجابة غير صالحة. احتُفظ بسؤالك؛ حاول مجددًا.')
      : L('No usable response arrived. Check the connection and try again; your question is kept.', 'لم تصل استجابة صالحة. تحقق من الاتصال وحاول مجددًا؛ احتُفظ بسؤالك.');
  const reasonText = code => REASONS[code] ? L(...REASONS[code]) : L('The Guide refused this result. No excerpts were released.', 'رفض الدليل هذه النتيجة. لم تُعرض مقتطفات.');
  const number = value => Number(value).toLocaleString(language);
  const sourceLang = value => /[\u0600-\u06ff]/.test(value) ? 'ar' : 'en';
  // Excerpts are Markdown from the reviewed docs. Render a small closed subset as DOM nodes, never as HTML:
  // paragraphs, bullet and numbered lists, **bold**, `code`, [link text](target) as its text, fenced blocks and table lines as
  // monospaced blocks (not <pre>: raw worker data is the only preformatted content in the answer area).
  function inline(text) {
    const out = [];
    for (const part of String(text).split(/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\))/)) {
      if (!part) continue;
      if (/^\*\*[^*]+\*\*$/.test(part)) out.push(el('strong', {}, part.slice(2, -2)));
      else if (/^`[^`]+`$/.test(part)) out.push(el('code', {}, part.slice(1, -1)));
      else if (/^\[[^\]]+\]\([^)\s]+\)$/.test(part)) out.push(part.slice(1, part.indexOf('](')));
      else out.push(part);
    }
    return out;
  }
  function markdown(text, cls) {
    const blocks = [], lines = String(text).split('\n');
    let para = [], list = null, fence = null;
    const flush = () => {
      if (para.length) blocks.push(el('p', {}, ...inline(para.join(' ')))); para = [];
      if (list) blocks.push(list); list = null;
    };
    for (const line of lines) {
      if (/^```/.test(line)) { if (fence) { blocks.push(el('div', {class: 'guide-block'}, fence.join('\n'))); fence = null; } else { flush(); fence = []; } continue; }
      if (fence) { fence.push(line); continue; }
      const item = /^\s*(?:[-*]|\d+[.)])\s+(.*)$/.exec(line);
      if (item) {
        if (para.length) { blocks.push(el('p', {}, ...inline(para.join(' ')))); para = []; }
        const tag = /^\s*\d/.test(line) ? 'ol' : 'ul';
        if (!list || list.tagName.toLowerCase() !== tag) { if (list) blocks.push(list); list = el(tag, {}); }
        list.append(el('li', {}, ...inline(item[1]))); continue;
      }
      if (/^\s*\|/.test(line)) { flush(); blocks.push(el('div', {class: 'guide-block'}, line)); continue; }
      if (!line.trim()) { flush(); continue; }
      if (list) { blocks.push(list); list = null; }
      para.push(line.trim());
    }
    if (fence) blocks.push(el('div', {class: 'guide-block'}, fence.join('\n')));
    flush();
    return el('div', {class: cls + ' guide-md', dir: 'auto', lang: sourceLang(text)}, ...blocks);
  }
  // "Architecture · Model gateway": the document and its section, so two passages of one document stay distinct.
  // Passages of one section in the same answer are numbered: "Architecture · Model gateway · passage 2".
  function sectionTitle(source) {
    const base = source.path.split('/').pop().replace(/\.md$/, '');
    const arabic = /\.ar$/.test(base), words = base.replace(/\.ar$/, '').replace(/[-_]+/g, ' ');
    const doc = words.charAt(0).toUpperCase() + words.slice(1) + (arabic ? L(' (Arabic)', ' (عربي)') : '');
    return source.heading && source.heading !== source.path && source.heading.toLowerCase() !== words.toLowerCase() ? doc + ' · ' + source.heading : doc;
  }
  function sourceTitle(source, all) {
    const title = sectionTitle(source), same = all.filter(other => sectionTitle(other) === title);
    return same.length > 1 ? title + L(' · passage ', ' · مقطع ') + number(same.indexOf(source) + 1) : title;
  }
  const validTrace = value => record(value) && value.request_id === result?.request_id
    && Number.isInteger(value.model_calls) && value.model_calls >= 0 && value.model_calls <= 1
    && Number.isInteger(value.tokens) && value.tokens >= 0 && record(value.redaction)
    && Number.isInteger(value.redaction.calls) && value.redaction.calls >= 0 && Array.isArray(value.tool_calls);
  function validReply(value) {
    if (!record(value) || !['answered', 'refused', 'blocked'].includes(value.status) || typeof value.request_id !== 'string' || !/^[0-9a-f]{32}$/.test(value.request_id)
        || !Array.isArray(value.sources)) return false;
    if (value.status !== 'answered') return value.sources.length === 0 && typeof value.reason === 'string';
    return value.answer_kind === 'document_excerpts' && corpus(value.corpus) && commit(value.source_commit)
      && value.sources.length > 0 && value.sources.length <= 3 && value.sources.every(source => record(source)
        && typeof source.id === 'string' && /^c-[0-9a-f]{64}$/.test(source.id) && path(source.path) && typeof source.heading === 'string'
        && source.heading.length > 0 && source.heading.length <= 120 && typeof source.excerpt === 'string'
        && source.excerpt.length > 0 && source.excerpt.length <= 4096 && sha(source.excerpt_sha256)
        && typeof source.identifiers_masked === 'boolean')
      && new Set(value.sources.map(source => source.id)).size === value.sources.length
      && value.answer === value.sources.map(source => source.excerpt).join('\n\n');
  }
  async function api(method, url, body, timeout) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), timeout);
    let response;
    try {
      response = await fetch(url, {method, signal: controller.signal, credentials: 'same-origin',
        headers: body === undefined ? {Accept: 'application/json'} : {'Content-Type': 'application/json', Accept: 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)});
      const data = await response.json();
      if (!record(data)) { Console.observeAPI(response.status, false); return {error: 'invalid'}; }
      Console.observeAPI(response.status);
      return response.ok ? {data} : {error: 'http'};
    } catch (error) {
      Console.observeAPI(response ? response.status : 0, !response);
      return {error: error.name === 'AbortError' ? 'timeout' : response ? 'invalid' : 'network'};
    } finally { clearTimeout(timer); }
  }
  function openSource(source, from) {
    const url = result?.source_commit ? 'https://github.com/lamanasser56/secure-financial-ai-infrastructure/blob/' + result.source_commit + '/' + source.path : null;
    const blocks = [
      {label: L('Excerpt shown', 'المقتطف المعروض'), node: markdown(source.excerpt, 'guide-excerpt')},
      {label: L('Document', 'الوثيقة'), node: el('bdi', {class: 'mono', dir: 'ltr'}, source.path)},
      {label: L('Source scope', 'نطاق المصدر'), text: L('Selected from the bundled current corpus. Source selection does not prove relevance, completeness or deployed enforcement. Excerpts retain their source language.', 'اختير من مجموعة الوثائق الحالية المرفقة. اختيار المصدر لا يثبت الصلة أو الاكتمال أو الإنفاذ المنشور. يبقى المقتطف بلغة وثيقته.')},
      {label: L('Identifier check', 'فحص المعرّفات'), text: source.identifiers_masked ? L('Supported identifiers were masked in the displayed excerpt.', 'أُخفيت معرّفات مدعومة في المقتطف المعروض.') : L('The output check reported no text change. This does not mean every kind of personal data is masked.', 'لم يُبلّغ فحص الإخراج عن تغيير النص. لا يعني ذلك إخفاء كل أنواع البيانات الشخصية.')},
      {label: L('Declared build source', 'مصدر البناء المعلن'), node: el('div', {}, el('bdi', {class: 'mono', dir: 'ltr'}, result.source_commit || L('Unbound test corpus', 'مجموعة اختبار غير مرتبطة بإصدار')), url ? el('p', {}, el('a', {class: 'btn link', href: url, target: '_blank', rel: 'noopener noreferrer'}, L('Open this source revision →', 'فتح نسخة المصدر ←'))) : null)},
      {label: L('Corpus review', 'مراجعة الوثائق'), node: el('p', {}, el('bdi', {dir: 'ltr'}, result.corpus.id + ' · ' + result.corpus.reviewed_at))},
      {label: L('Content identities', 'معرّفات المحتوى'), node: el('pre', {class: 'code guide-code'}, source.id + '\n' + source.excerpt_sha256 + '\n' + result.corpus.manifest_sha256)},
      {label: L('Build metadata limits', 'حدود بيانات البناء'), text: L('These are declared source and content identities, not cryptographic verification of an image signature or source provenance.', 'هذه بيانات مصدر معلن ومعرّفات محتوى، وليست تحققًا تشفيريًا من توقيع صورة أو إسناد مصدرها.')},
    ];
    Console.explain({eyebrow: L('DOCUMENT SOURCE', 'مصدر الوثيقة'), title: sourceTitle(source, result.sources), blocks}, from);
  }
  function openTrace(from) {
    const trace = result.trace;
    const labels = {source_quotes_verified: L('Selected source excerpts verified', 'تم التحقق من اختيار مقتطفات المصادر'),
      refused: L('No excerpts admitted', 'لم تُقبل مقتطفات'), unsupported_answer_blocked: L('Unsupported selection refused', 'رُفض الاختيار غير المسند')};
    Console.explain({eyebrow: L('WORKER REPORT', 'إفادة العامل'), title: L('Request trace', 'أثر الطلب'),
      copy: {label: L('request', 'الطلب'), value: result.request_id}, blocks: [
        {label: L('Source and limits', 'المصدر والحدود'), text: L('Produced by the Guide worker for this turn. It is not independent boundary evidence or a complete, durable audit.', 'أنتج عامل الدليل هذا الأثر للدور الحالي. ليس دليلًا مستقلًا على الحدود أو سجل تدقيق كاملًا ودائمًا.')},
        {label: L('Admission', 'قبول النتيجة'), text: labels[trace.grounding_result] || L('Unrecognized worker status', 'حالة عامل غير معروفة')},
        {label: L('Reported steps', 'الخطوات المبلّغ عنها'), text: L('Model calls: ', 'استدعاءات النموذج: ') + number(trace.model_calls) + L(' · Tokens: ', ' · الرموز: ') + number(trace.tokens) + L(' · Identifier checks: ', ' · فحوص المعرّفات: ') + number(trace.redaction.calls)},
        {label: L('Reported cost', 'التكلفة المبلّغ عنها'), text: cost(trace)},
        {label: L('Raw worker fields', 'حقول العامل الخام'), node: el('details', {}, el('summary', {}, L('Inspect the report', 'فحص الإفادة')), el('pre', {class: 'code guide-code'}, JSON.stringify(trace, null, 2)))},
      ]}, from);
  }
  function cost(trace) {
    const recognized = trace.cost_source === 'litellm_response_header' && trace.model_calls > 0
      || trace.cost_source === 'no_model_call' && trace.model_calls === 0 && trace.cost_usd === 0;
    if (!recognized || typeof trace.cost_usd !== 'number' || !Number.isFinite(trace.cost_usd) || trace.cost_usd < 0) return L('Cost unavailable', 'التكلفة غير متاحة');
    return trace.cost_usd > 0 && trace.cost_usd < 0.0001 ? '<$0.0001' : '$' + trace.cost_usd.toFixed(4);
  }
  function about(from) {
    Console.explain({eyebrow: L('HOW ANSWERS WORK', 'كيف تُعرض الإجابة'), title: L('Documentation, with limits', 'وثائق بحدود واضحة'), blocks: [
      {label: L('What is shown', 'ما يُعرض'), text: L('Code searches the actual question once. A model may select available passage IDs or decline. Code copies only the selected excerpts; it refuses invented IDs and generated factual prose. Excerpts keep their source language.', 'يبحث الكود عن السؤال نفسه مرة واحدة. يختار النموذج معرّفات مقتطفات متاحة أو يرفض الإجابة. ينسخ الكود المقتطفات المختارة فقط، ويرفض المعرّفات المختلقة والنص الواقعي المولّد. تبقى المقتطفات بلغة مصادرها.')},
      {label: L('What is not proved', 'ما لا يُثبت'), text: L('Literal source selection is not proof of truth, relevance, completeness or deployed controls. No results means no model call.', 'اختيار نص من مصدر ليس إثباتًا لصحته أو صلته أو اكتماله أو للضوابط المنشورة. عند غياب النتائج لا يُستدعى النموذج.')},
      {label: L('Supported masking patterns', 'أنماط الإخفاء المدعومة'), node: info ? el('ul', {}, info.masking_types.map(code => el('li', {}, L(...TYPES[code]), ' · ', el('bdi', {dir: 'ltr', class: 'mono'}, code)))) : el('p', {}, L('The current scope could not be loaded. No coverage is inferred.', 'تعذّر تحميل النطاق الحالي. لا نفترض تغطية للإخفاء.'))},
      {label: L('Masking limits', 'حدود الإخفاء'), text: L('Person names and passport numbers are not masked. Supported detection depends on format and context; this is not universal personal-data removal.', 'لا تُخفى أسماء الأشخاص أو أرقام جوازات السفر. يعتمد كشف الأنواع المدعومة على التنسيق والسياق؛ ولا يُزال كل ما قد يكون بيانات شخصية.')},
      {label: L('Limits and retention', 'الحدود والاحتفاظ'), text: L('Question and token counters are in this Guide process’s memory and reset on restart. They are not durable global quotas. The worker emits bounded request events, without a promise of complete or durable audit.', 'عدادا الأسئلة والرموز في ذاكرة عملية الدليل ويُصفّران عند إعادة تشغيلها. ليست حصصًا عامة دائمة. يصدر العامل أحداث طلب محدودة، دون ضمان سجل تدقيق كامل أو دائم.')},
    ]}, from);
  }
  function paint() {
    document.documentElement.lang = language; document.documentElement.dir = language === 'ar' ? 'rtl' : 'ltr';
    document.title = L('Platform Guide · Agent Runtime Platform', 'دليل المنصة · منصة تشغيل الوكلاء');
    Console.setLanguage(language);
    document.querySelector('.skip').textContent = L('Skip to content', 'انتقل إلى المحتوى');
    document.querySelector('.brand').textContent = L('Agent Runtime Platform', 'منصة تشغيل الوكلاء');
    document.querySelector('.tabs').setAttribute('aria-label', L('Screens', 'الشاشات'));
    $('guide-tab').textContent = L('Guide', 'الدليل'); $('passport').textContent = L('Agent passport', 'جواز الوكيل');
    $('title').textContent = L('Platform Guide', 'دليل المنصة');
    $('subtitle').textContent = L('Selected excerpts from the current platform docs.', 'مقتطفات مختارة من وثائق المنصة الحالية.');
    $('about').textContent = L('How answers work', 'كيف تُعرض الإجابة');
    $('language-label').textContent = L('Language', 'اللغة'); $('question-label').textContent = L('Question', 'السؤال');
    $('question-help').textContent = L('About this platform, up to 500 characters.', 'عن هذه المنصة، حتى ٥٠٠ حرف.');
    $('q').placeholder = L('What does the Model gateway mask?', 'ما الذي تخفيه بوابة النموذج؟');
    $('q').disabled = $('lang').disabled = busy;
    $('send').textContent = busy ? L('Finding excerpts…', 'جارٍ البحث عن مقتطفات…') : L('Ask', 'اسأل');
    $('send').disabled = busy || !$('q').value.trim();
    $('ask').setAttribute('aria-busy', String(busy)); $('out').setAttribute('aria-busy', String(busy));
    $('examples').replaceChildren(...[
      L('What does the Model gateway mask?', 'ما الذي تخفيه بوابة النموذج؟'),
      L('Who can execute approved changes?', 'من ينفذ التغييرات الموافق عليها؟'),
    ].map(question => el('button', {type: 'button', class: 'btn link', disabled: busy, onclick: () => { $('q').value = question; paint(); $('q').focus(); }}, question)));
    $('metadata-status').textContent = infoBusy ? L('Loading documentation details…', 'جارٍ تحميل تفاصيل الوثائق…')
      : infoError ? L('Documentation details unavailable. Questions can still be sent.', 'تفاصيل الوثائق غير متاحة. لا يزال إرسال الأسئلة ممكنًا.') : '';
    $('retry-info').hidden = !infoError; $('retry-info').disabled = infoBusy;
    $('retry-info').textContent = L('Retry documentation details', 'إعادة تحميل تفاصيل الوثائق');
    $('result-title').textContent = L('From the documentation', 'من الوثائق');
    const nodes = [];
    if (busy) nodes.push(el('p', {class: 'guide-state', role: 'status'}, L('Searching the bundled docs and checking a source selection…', 'جارٍ البحث في الوثائق المرفقة وفحص اختيار المصادر…')));
    else if (failure) nodes.push(el('p', {class: 'guide-state', role: 'alert'}, errorText(failure)));
    else if (!result) nodes.push(el('p', {class: 'muted guide-state'}, L('Ask about the platform. Details and sources open when selected.', 'اسأل عن المنصة. تُفتح التفاصيل والمصادر عند اختيارها.')));
    else {
      if (result.status === 'answered') {
        result.sources.forEach((source, i) => nodes.push(el('div', {class: 'guide-quote'},
          el('div', {class: 'guide-quote-from'}, L('Source ', 'المصدر ') + number(i + 1) + ' · ', el('span', {dir: 'auto'}, sourceTitle(source, result.sources))),
          markdown(source.excerpt, 'guide-excerpt'))));
        nodes.push(el('ul', {class: 'guide-sources', 'aria-label': L('Selected sources', 'المصادر المختارة')}, result.sources.map((source, i) => el('li', {},
          el('button', {type: 'button', class: 'btn link', onclick: event => openSource(source, event.currentTarget)},
            L('Source ', 'المصدر ') + number(i + 1), el('span', {class: 'guide-source-name', dir: 'auto'}, sourceTitle(source, result.sources)))))));
        nodes.push(el('p', {class: 'guide-note muted'}, L('Open a source for its document, revision and identifier check. Excerpts retain their source language.', 'افتح المصدر لعرض وثيقته ونسختها وفحص المعرّفات. تبقى المقتطفات بلغة مصادرها.')));
      } else nodes.push(el('p', {class: 'guide-state', role: 'status'}, reasonText(result.reason)));
      nodes.push(validTrace(result.trace) ? el('button', {class: 'btn link', type: 'button', onclick: event => openTrace(event.currentTarget)}, L('Inspect request trace', 'فحص أثر الطلب'))
        : el('p', {class: 'muted'}, L('Worker report unavailable; no trace evidence is inferred.', 'إفادة العامل غير متاحة؛ لا نفترض دليلًا من الأثر.')));
    }
    $('result').replaceChildren(...nodes);
  }
  async function loadInfo() {
    if (infoBusy) return;
    infoBusy = true; infoError = false; paint();
    const reply = await api('GET', '/api/info', undefined, 15000);
    const value = reply.data;
    if (!value || !corpus(value.corpus) || !commit(value.source_commit) || !Array.isArray(value.masking_types)
        || value.masking_types.length !== Object.keys(TYPES).length || new Set(value.masking_types).size !== value.masking_types.length
        || value.masking_types.some(type => typeof type !== 'string' || !Object.hasOwn(TYPES, type))) {
      info = null; infoError = true;
      if (!reply.error) Console.observeAPI(200, false);
    } else info = value;
    infoBusy = false; paint();
  }
  $('ask').addEventListener('submit', async event => {
    event.preventDefault(); if (busy || !$('q').value.trim()) return;
    const body = {question: $('q').value.trim(), language};
    Console.close(); busy = true; result = null; failure = null; paint();
    const reply = await api('POST', '/api/ask', body, 60000);
    if (reply.error) failure = reply.error;
    else if (!validReply(reply.data)) { failure = 'invalid'; Console.observeAPI(200, false); }
    else result = reply.data;
    busy = false; paint();
  });
  $('q').addEventListener('input', () => { $('send').disabled = busy || !$('q').value.trim(); });
  $('lang').addEventListener('change', event => {
    if (busy) { event.target.value = language; return; }
    Console.close(); language = event.target.value === 'ar' ? 'ar' : 'en'; paint(); $('lang').focus();
  });
  $('about').addEventListener('click', event => about(event.currentTarget));
  $('retry-info').addEventListener('click', loadInfo);
  $('guide-tab').addEventListener('click', event => { event.preventDefault(); $('view').focus(); });
  paint(); loadInfo();
})();
