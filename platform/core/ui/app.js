'use strict';
// Shared page core for the front door (About and Security & Operations): language, formatting, guided tour.
// textContent only, never HTML strings; CSP script-src 'self'. Arabic uses Western digits 0-9 and the Gregorian calendar.
const UI_PARAMS = () => new URLSearchParams(window.location.hash.slice(1));
const UI = (() => {
  const dict = {en: {}, ar: {}};
  const listeners = [];
  let lang = 'en';
  const store = {
    get(k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { window.localStorage.setItem(k, v); } catch (e) { /* storage blocked: the page still works */ } },
  };
  const locale = () => (lang === 'ar' ? 'ar-u-nu-latn-ca-gregory' : 'en-GB');
  const t = key => (dict[lang][key] !== undefined ? dict[lang][key] : (dict.en[key] !== undefined ? dict.en[key] : key));
  const latin = s => String(s).replace(/[٠-٩]/g, d => String(d.charCodeAt(0) - 0x0660)).replace(/[۰-۹]/g, d => String(d.charCodeAt(0) - 0x06F0));
  const fmt = {
    date: d => new Intl.DateTimeFormat(locale(), {day: 'numeric', month: 'long', year: 'numeric'}).format(d),
    time: d => new Intl.DateTimeFormat(locale(), {hour: 'numeric', minute: '2-digit'}).format(d),
    month: ym => { const [y, m] = String(ym).split('-').map(Number); return new Intl.DateTimeFormat(locale(), {month: 'long', year: 'numeric'}).format(new Date(y, m - 1, 1)); },
    day: iso => { const [y, m, d] = String(iso).split('-').map(Number); return fmt.date(new Date(y, m - 1, d)); },
    money: minor => (minor / 100).toFixed(2) + (lang === 'ar' ? ' ر.س' : ' SAR'),
    num: n => String(n),
  };
  function el(tag, attrs, ...children) {
    const e = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => { if (k === 'class') e.className = v; else if (v !== null && v !== undefined) e.setAttribute(k, v); });
    children.flat().forEach(c => { if (c !== null && c !== undefined) e.append(c instanceof Node ? c : String(c)); });
    return e;
  }
  const ltr = text => el('bdi', {dir: 'ltr'}, text);
  function apply() {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
    document.querySelectorAll('[data-t]').forEach(e => { e.textContent = t(e.dataset.t); });
    document.querySelectorAll('[data-t-aria]').forEach(e => { e.setAttribute('aria-label', t(e.dataset.tAria)); });
    document.querySelectorAll('[data-t-ph]').forEach(e => { e.setAttribute('placeholder', t(e.dataset.tPh)); });
    document.querySelectorAll('[data-lang]').forEach(b => { b.setAttribute('aria-pressed', String(b.dataset.lang === lang)); });
    document.title = t('title_' + document.body.dataset.page);
    document.querySelectorAll('nav.links a, a.cta').forEach(a => {  // keep the language when moving between pages
      if (!a.dataset.base) a.dataset.base = a.getAttribute('href');
      a.setAttribute('href', a.dataset.base + '#lang=' + lang);
    });
    listeners.forEach(fn => fn(lang));
  }
  function setLang(next) { lang = next === 'ar' ? 'ar' : 'en'; store.set('lang', lang); apply(); }

  // Guided tour: numbered steps, highlighted section, Next / Back / Skip. "Seen" is remembered when storage works.
  let tourState = null;
  function endTour(seenKey) {
    if (!tourState) return;
    tourState.veil.remove(); tourState.tip.remove();
    document.querySelectorAll('.tour-focus').forEach(e => e.classList.remove('tour-focus'));
    tourState = null; store.set(seenKey, '1');
  }
  function tour(steps, seenKey) {
    endTour(seenKey);
    const shown = steps.filter(s => { const e = document.querySelector(s.sel); return e && !e.closest('[hidden]'); });
    if (!shown.length) return;
    const veil = el('div', {class: 'tour-veil'});
    const tip = el('div', {class: 'tour-tip', role: 'dialog', 'aria-modal': 'false', 'aria-labelledby': 'tour-title'});
    document.body.append(veil, tip);
    tourState = {veil, tip, i: 0};
    veil.onclick = () => endTour(seenKey);
    const render = () => {
      const s = shown[tourState.i], target = document.querySelector(s.sel);
      document.querySelectorAll('.tour-focus').forEach(e => e.classList.remove('tour-focus'));
      target.classList.add('tour-focus');
      target.scrollIntoView({block: 'center', behavior: 'instant'});
      const back = el('button', {type: 'button', class: 'ghost'}, t('tour_back'));
      const next = el('button', {type: 'button', class: 'primary'}, tourState.i === shown.length - 1 ? t('tour_done') : t('tour_next'));
      const skip = el('button', {type: 'button', class: 'ghost'}, t('tour_skip'));
      back.disabled = tourState.i === 0;
      back.onclick = () => { tourState.i -= 1; render(); };
      next.onclick = () => { if (tourState.i === shown.length - 1) endTour(seenKey); else { tourState.i += 1; render(); } };
      skip.onclick = () => endTour(seenKey);
      tip.replaceChildren(
        el('h3', {id: 'tour-title'}, el('span', {class: 'step-no'}, String(tourState.i + 1)), t(s.title)),
        el('p', {}, t(s.body)),
        el('div', {class: 'row'}, el('span', {class: 'muted small'}, (tourState.i + 1) + ' / ' + shown.length), el('span', {class: 'spacer'}), skip, back, next));
      const r = target.getBoundingClientRect();
      const top = window.scrollY + (r.bottom + tip.offsetHeight + 16 < window.innerHeight ? r.bottom + 12 : Math.max(8, r.top - tip.offsetHeight - 12));
      const left = lang === 'ar' ? Math.max(8, r.right - tip.offsetWidth) : Math.min(r.left, window.innerWidth - tip.offsetWidth - 8);
      tip.style.top = top + 'px';
      tip.style.left = Math.max(8, left) + window.scrollX + 'px';
      next.focus();
    };
    render();
    document.addEventListener('keydown', function esc(ev) { if (ev.key === 'Escape') { endTour(seenKey); document.removeEventListener('keydown', esc); } });
  }
  function start(steps) {
    const key = 'tour:' + document.body.dataset.page;
    document.querySelectorAll('[data-lang]').forEach(b => { b.onclick = () => setLang(b.dataset.lang); });
    const open = document.getElementById('tour');
    if (open) open.onclick = () => tour(steps, key);
    const params = UI_PARAMS();  // the fragment: the front door serves exact paths only, so no query string
    setLang(params.get('lang') || store.get('lang') || ((navigator.language || '').startsWith('ar') ? 'ar' : 'en'));
    if (params.get('tour') === 'off') store.set(key, '1');
    if (!store.get(key)) window.setTimeout(() => tour(steps, key), 400);
  }
  return {dict, t, fmt, el, ltr, latin, start, onLang: fn => listeners.push(fn), get lang() { return lang; }};
})();

Object.assign(UI.dict.en, {
  title_about: 'About · Secure AI Agent Platform', title_operations: 'Security & Operations · Secure AI Agent Platform',
  brand: 'Secure AI Agent Platform', nav_financial: 'Financial Agent', nav_ops: 'Security & Operations', nav_about: 'About',
  tour_open: 'Show the guided tour', tour_next: 'Next', tour_back: 'Back', tour_skip: 'Skip', tour_done: 'Done', open: 'Open',
  about_title: 'About the platform',
  about_intro: 'Any team can deploy its own AI agent here and inherit these protections without building them.',
  agents_title: 'Agents running on the platform', agents_intro: 'Each agent was onboarded with one manifest and runs in its own isolated namespace.',
  a_fin: 'Financial Agent', a_fin_d: 'Answers questions about your own expenses, only from your records, in Arabic or English.',
  a_ops: 'Security & Operations Agent', a_ops_d: "Watches the platform's services, explains problems and fixes them only after your approval.",
  a_hello: 'hello agent', a_hello_d: 'The smallest onboarded example: one manifest, one model call, every protection inherited.',
  flow1_title: 'How a question is answered', flow1_intro: 'Every model call takes the same path. No step can be skipped.',
  f1_1: 'You', f1_1d: 'ask in your own words', f1_2: 'Privacy masking', f1_2d: 'personal data is hidden first',
  f1_3: 'Gateway', f1_3d: 'budget per agent, no direct provider access', f1_4: 'AI model', f1_4d: 'sees masked text only',
  f1_5: 'Answer check', f1_5d: 'every figure must match your records',
  flow2_title: 'How a problem is fixed', flow2_intro: 'The operations agent proposes; only you approve. It can restart or resize a service, never change what it runs.',
  f2_1: 'Observe', f2_1d: 'reads service state', f2_2: 'Diagnose', f2_2d: 'fixed rules, no AI', f2_3: 'Propose', f2_3d: 'restart or bounded resize',
  f2_4: 'Your approval', f2_4d: 'valid once, for 5 minutes', f2_5: 'Execute once', f2_5d: 'only if nothing changed', f2_6: 'Verify', f2_6d: 'healthy again, or reported',
  controls_title: 'What every agent inherits',
  c1: 'An isolated network: nothing in or out unless allowed.', c2: 'Its own AI key with a monthly budget; no direct provider access.',
  c3: 'Automatic masking of personal data before every model call.', c4: 'Read-only tools from a registry, checked by policy.',
  c5: 'An audit trail without personal content.', c6: 'Only signed and attested images can run.', c7: 'The operations agent cannot change what a service runs.',
  about_foot: 'All data is synthetic. Pages are reached only through a private port-forward on this computer.',
  tour_a1_t: 'What this platform is', tour_a1_b: 'A shared home for AI agents. Each team brings an agent; the platform supplies the safety.',
  tour_a2_t: 'The agents', tour_a2_b: 'Three agents run here today. Open the Financial Agent or the Security & Operations Agent from these cards.',
  tour_a3_t: 'The answer path', tour_a3_b: 'Personal data is masked before the AI model sees anything, and every figure in an answer is checked against your records.',
  tour_a4_t: 'The repair loop', tour_a4_b: 'The operations agent can only propose. Nothing changes until you approve, and an approval works once.',
  chk_netpol: 'Every namespace starts with default-deny networking', chk_netpol_h: 'each watched namespace has a deny-all NetworkPolicy.',
  chk_root: 'No service runs as root or privileged', chk_root_h: 'every running container is non-root and unprivileged.',
  chk_rbac: 'Only the operations agent holds roles in watched namespaces', chk_rbac_h: 'role bindings list no other identity.',
  chk_admission: 'No image was rejected by the signature check', chk_admission_h: 'no admission denial events in watched namespaces.',
  chk_signed: 'Images are signed and attested (Binary Authorization)', chk_signed_h: 'An unsigned image was refused in two namespaces (unsigned_image_rejected).',
  chk_scan: 'Vulnerability scan: 0 high or critical, no KEV entry', chk_scan_h: 'CI scans each image before signing; any known-exploited flaw blocks it.',
  chk_public: 'No public exposure', chk_public_h: 'Load balancers and node ports are refused by quota (no_public_exposure).',
  chk_egress: 'No internet access from agents', chk_egress_h: 'Agents reach only the gateway and the redactor (egress_containment).',
  chk_spec: 'The operations agent cannot change a Pod spec', chk_spec_h: 'Admission policy allows only a restart or a bounded resize (ops_stale_approval_refused).',
  chk_redact: 'Personal data is masked before every model call', chk_redact_h: 'With masking down, no request reached the model (redaction_down).',
  tour_a5_t: 'Inherited protections', tour_a5_b: 'These seven controls come with every agent, without extra work by its team.',
});
Object.assign(UI.dict.ar, {
  title_about: 'عن المنصة · منصة وكلاء الذكاء الاصطناعي الآمنة', title_operations: 'الأمن والعمليات · منصة وكلاء الذكاء الاصطناعي الآمنة',
  brand: 'منصة وكلاء الذكاء الاصطناعي الآمنة', nav_financial: 'الوكيل المالي', nav_ops: 'الأمن والعمليات', nav_about: 'عن المنصة',
  tour_open: 'عرض الجولة التعريفية', tour_next: 'التالي', tour_back: 'السابق', tour_skip: 'تخطٍّ', tour_done: 'تم', open: 'فتح',
  about_title: 'عن المنصة',
  about_intro: 'يمكن لأي فريق نشر وكيله هنا ليرث هذه الحمايات دون أن يبنيها بنفسه.',
  agents_title: 'الوكلاء العاملون على المنصة', agents_intro: 'أُضيف كل وكيل بملف تعريف واحد، ويعمل في مساحة معزولة خاصة به.',
  a_fin: 'الوكيل المالي', a_fin_d: 'يجيب عن أسئلتك حول مصروفاتك أنت، من سجلاتك فقط، بالعربية أو الإنجليزية.',
  a_ops: 'وكيل الأمن والعمليات', a_ops_d: 'يراقب خدمات المنصة، ويشرح المشكلات، ولا يصلحها إلا بعد موافقتك.',
  a_hello: 'وكيل hello', a_hello_d: 'أبسط مثال للانضمام: ملف تعريف واحد، واستدعاء واحد للنموذج، وكل الحمايات موروثة.',
  flow1_title: 'كيف يُجاب عن السؤال', flow1_intro: 'كل استدعاء للنموذج يمر بالمسار نفسه، ولا يمكن تخطي أي خطوة.',
  f1_1: 'أنت', f1_1d: 'تسأل بكلماتك', f1_2: 'إخفاء البيانات الشخصية', f1_2d: 'تُخفى البيانات الشخصية أولاً',
  f1_3: 'البوابة', f1_3d: 'ميزانية لكل وكيل، ولا وصول مباشر لمزوّد النموذج', f1_4: 'نموذج الذكاء الاصطناعي', f1_4d: 'يرى النص بعد الإخفاء فقط',
  f1_5: 'فحص الجواب', f1_5d: 'كل رقم يجب أن يطابق سجلاتك',
  flow2_title: 'كيف تُصلح المشكلة', flow2_intro: 'وكيل العمليات يقترح، وأنت وحدك توافق. يستطيع إعادة تشغيل الخدمة أو تغيير حجمها، ولا يغيّر أبداً ما تشغّله.',
  f2_1: 'المراقبة', f2_1d: 'يقرأ حالة الخدمة', f2_2: 'التشخيص', f2_2d: 'قواعد ثابتة بلا ذكاء اصطناعي', f2_3: 'الاقتراح', f2_3d: 'إعادة تشغيل أو تغيير حجم محدود',
  f2_4: 'موافقتك', f2_4d: 'صالحة مرة واحدة لمدة 5 دقائق', f2_5: 'التنفيذ مرة واحدة', f2_5d: 'فقط إن لم يتغير شيء', f2_6: 'التحقق', f2_6d: 'عادت سليمة، أو يُبلَّغ عنها',
  controls_title: 'ما يرثه كل وكيل',
  c1: 'شبكة معزولة: لا دخول ولا خروج إلا بإذن.', c2: 'مفتاح ذكاء اصطناعي خاص بميزانية شهرية، ولا وصول مباشر للمزوّد.',
  c3: 'إخفاء تلقائي للبيانات الشخصية قبل كل استدعاء للنموذج.', c4: 'أدوات للقراءة فقط من سجل معتمد، تراقبها السياسة.',
  c5: 'سجل تدقيق بلا محتوى شخصي.', c6: 'لا تعمل إلا الصور الموقّعة والمعتمدة.', c7: 'وكيل العمليات لا يستطيع تغيير ما تشغّله الخدمة.',
  about_foot: 'كل البيانات تجريبية. يُوصَل إلى الصفحات فقط عبر توجيه منافذ خاص على هذا الجهاز.',
  tour_a1_t: 'ما هذه المنصة', tour_a1_b: 'بيت مشترك لوكلاء الذكاء الاصطناعي: كل فريق يجلب وكيله، والمنصة توفّر الأمان.',
  tour_a2_t: 'الوكلاء', tour_a2_b: 'ثلاثة وكلاء يعملون هنا اليوم. افتح الوكيل المالي أو وكيل الأمن والعمليات من هذه البطاقات.',
  tour_a3_t: 'مسار الجواب', tour_a3_b: 'تُخفى البيانات الشخصية قبل أن يرى النموذج أي شيء، ويُطابَق كل رقم في الجواب مع سجلاتك.',
  tour_a4_t: 'حلقة الإصلاح', tour_a4_b: 'وكيل العمليات يقترح فقط. لا يتغير شيء حتى توافق، والموافقة تعمل مرة واحدة.',
  chk_netpol: 'كل مساحة تبدأ بشبكة مغلقة افتراضياً', chk_netpol_h: 'في كل مساحة مراقَبة سياسة شبكة ترفض كل شيء افتراضياً.',
  chk_root: 'لا خدمة تعمل بصلاحيات الجذر أو بامتيازات', chk_root_h: 'كل حاوية عاملة غير جذرية وبلا امتيازات.',
  chk_rbac: 'وكيل العمليات وحده يملك أدواراً في المساحات المراقَبة', chk_rbac_h: 'روابط الأدوار لا تذكر أي هوية أخرى.',
  chk_admission: 'لم يرفض فحصُ التوقيع أي صورة', chk_admission_h: 'لا أحداث رفض في المساحات المراقَبة.',
  chk_signed: 'الصور موقّعة ومعتمدة (Binary Authorization)', chk_signed_h: 'رُفضت صورة غير موقّعة في مساحتين (unsigned_image_rejected).',
  chk_scan: 'فحص الثغرات: 0 عالية أو حرجة، ولا شيء من قائمة KEV', chk_scan_h: 'يفحص CI كل صورة قبل توقيعها، وأي ثغرة مستغلة معروفة توقفها.',
  chk_public: 'لا انكشاف للعامة', chk_public_h: 'موازنات الحمل والمنافذ العامة مرفوضة بالحصص (no_public_exposure).',
  chk_egress: 'لا وصول للإنترنت من الوكلاء', chk_egress_h: 'يصل الوكلاء إلى البوابة وخدمة الإخفاء فقط (egress_containment).',
  chk_spec: 'وكيل العمليات لا يستطيع تغيير مواصفات الـ Pod', chk_spec_h: 'سياسة القبول تسمح فقط بإعادة التشغيل أو تغيير حجم محدود (ops_stale_approval_refused).',
  chk_redact: 'تُخفى البيانات الشخصية قبل كل استدعاء للنموذج', chk_redact_h: 'عند توقف الإخفاء لم يصل أي طلب إلى النموذج (redaction_down).',
  tour_a5_t: 'الحمايات الموروثة', tour_a5_b: 'هذه الضوابط السبعة تأتي مع كل وكيل دون جهد إضافي من فريقه.',
});

if (document.body.dataset.page === 'about') {
  UI.start([
    {sel: '#about-intro', title: 'tour_a1_t', body: 'tour_a1_b'}, {sel: '#agents', title: 'tour_a2_t', body: 'tour_a2_b'},
    {sel: '#answer-path', title: 'tour_a3_t', body: 'tour_a3_b'}, {sel: '#ops-loop', title: 'tour_a4_t', body: 'tour_a4_b'},
    {sel: '#controls', title: 'tour_a5_t', body: 'tour_a5_b'}]);
}
