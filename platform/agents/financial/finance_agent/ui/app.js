'use strict';
// Financial Agent page. The shared core below is a verbatim copy of platform/core/ui/app.js (a test keeps them equal).
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

// Financial Agent page. The browser never chooses the user: every call uses the signed session cookie.
(() => {
const {t, el, ltr, fmt} = UI;
const CATEGORIES = ['food', 'transport', 'shopping', 'bills', 'subscriptions', 'health', 'travel', 'other'];
Object.assign(UI.dict.en, {
  title_financial: 'Financial Agent · Secure AI Agent Platform',
  brand: 'Secure AI Agent Platform', nav_financial: 'Financial Agent', nav_ops: 'Security & Operations', nav_about: 'About',
  tour_open: 'Show the guided tour', tour_next: 'Next', tour_back: 'Back', tour_skip: 'Skip', tour_done: 'Done', logout: 'Sign out',
  fin_title: 'Financial Agent',
  fin_intro: 'Ask about your expenses in your own words. The agent answers only from your own records, hides personal data before anything reaches the AI model, and shows how it knows.',
  signin: 'Sign in', signin_intro: 'Each person sees only their own expenses. Five wrong passwords lock that name for 15 minutes.',
  username: 'Username', password: 'Password', login: 'Sign in', live: 'Live', synthetic: 'synthetic data', who: 'signed in as ',
  left: 'questions left this hour: {n} of {m}', expiry: 'session ends at ',
  tab_ask: 'Ask the agent', tab_exp: 'My expenses',
  ask_intro: 'Ask a question about your expenses. Every figure in the answer is checked against your own records before you see it.',
  exp_intro: 'Add an expense or browse a month. Only you can see these records; the agent reads them through read-only tools.',
  question: 'Your question', example: 'Example: How much did I spend in October 2026?', send: 'Ask', answer: 'Answer',
  ex1: 'How much did I spend in October 2026?', ex2: 'What did I spend most on in October 2026?', ex3: 'List my expenses in October 2026.',
  how: 'How we know', privacy: 'Privacy check', tech: 'Technical details',
  tools: 'Tools used: ', period: 'Period: ', source: 'Source: your own expenses (read-only, synthetic).', no_tools: 'No records were needed for this answer.',
  masked: 'Before the AI model saw your question, we masked: {c}. No personal values were sent.', nothing: 'Nothing personal needed masking; no personal values were sent.',
  add: 'Add an expense', date: 'Date', merchant: 'Merchant', category: 'Category', amount: 'Amount (SAR)', amount_h: 'Amount', note: 'Note', save: 'Add',
  list: 'My expenses', month: 'Month', empty: 'No expenses in this month yet.', total: 'Total for {m}: {v} in {n} expense(s).', saved: 'Expense added.',
  food: 'Food', transport: 'Transport', shopping: 'Shopping', bills: 'Bills', subscriptions: 'Subscriptions', health: 'Health', travel: 'Travel', other: 'Other',
  monthly_total: 'Expense totals', spending_by_category: 'Spending by category', find_transactions: 'Individual expenses',
  EMAIL_ADDRESS: 'email address', PHONE_NUMBER: 'phone number', PERSON_NAME: 'person name', CREDIT_CARD_NUMBER: 'card number',
  IBAN_CODE: 'bank account (IBAN)', STREET_ADDRESS: 'street address', LOCATION: 'location', DATE_OF_BIRTH: 'date of birth',
  e_wrong_username_or_password: 'Wrong username or password.', e_too_many_attempts: 'Too many wrong attempts for this name. Try again in 15 minutes.',
  e_username_and_password_required: 'Enter a username and a password.', e_sign_in_required: 'Your session ended. Please sign in again.',
  e_default: 'Something went wrong. Nothing was changed.',
  r_ungrounded_numbers: 'The answer contained a figure that is not in your records, so it was not shown. Try asking about a specific month.',
  r_ungrounded_claim: 'I can only answer from the expenses you entered (date, merchant, category, amount, note). I cannot confirm invoices, payments, refunds or whether something is recorded.',
  r_rate_limited: 'You reached the limit of 20 questions per hour.', r_token_budget_exhausted: 'Your daily AI budget is used up. Try again tomorrow.',
  r_question_length: 'Questions must be 1–500 characters.', r_redaction_unavailable: 'Privacy masking is unavailable right now, so nothing was sent to the AI model.',
  r_model_unavailable: 'The AI model is unavailable right now.', r_step_limit: 'The agent took too many steps and stopped.',
  r_tool_arguments_rejected: 'The agent asked for records in a way the platform does not allow, so it stopped.',
  r_default: 'The agent could not answer this safely, so nothing was shown.',
  tour_f0_t: 'Sign in', tour_f0_b: 'Sign in with your own name. You will only ever see your own records.',
  tour_f1_t: 'What this agent does', tour_f1_b: 'It answers questions about your own expenses — never anyone else’s.',
  tour_f2_t: 'Your session', tour_f2_b: 'Live status, how many questions you have left this hour, and when your session ends.',
  tour_f3_t: 'Ask', tour_f3_b: 'Type a question or pick an example. Up to 500 characters.',
  tour_f4_t: 'The answer and its proof', tour_f4_b: 'The answer comes first, then how we know (tools and period) and the privacy check.',
  tour_f5_t: 'Your records', tour_f5_b: 'Add expenses and browse a month here. The agent can read them but never change them.',
});
Object.assign(UI.dict.ar, {
  title_financial: 'الوكيل المالي · منصة وكلاء الذكاء الاصطناعي الآمنة',
  brand: 'منصة وكلاء الذكاء الاصطناعي الآمنة', nav_financial: 'الوكيل المالي', nav_ops: 'الأمن والعمليات', nav_about: 'عن المنصة',
  tour_open: 'عرض الجولة التعريفية', tour_next: 'التالي', tour_back: 'السابق', tour_skip: 'تخطٍّ', tour_done: 'تم', logout: 'تسجيل الخروج',
  fin_title: 'الوكيل المالي',
  fin_intro: 'اسأل عن مصروفاتك بكلماتك. يجيب الوكيل من سجلاتك فقط، ويخفي البيانات الشخصية قبل وصولها إلى نموذج الذكاء الاصطناعي، ويبيّن مصدر كل رقم.',
  signin: 'تسجيل الدخول', signin_intro: 'كل شخص يرى مصروفاته فقط. خمس محاولات خاطئة تقفل الاسم لمدة 15 دقيقة.',
  username: 'اسم المستخدم', password: 'كلمة المرور', login: 'دخول', live: 'مباشر', synthetic: 'بيانات تجريبية', who: 'مسجّل الدخول: ',
  left: 'الأسئلة المتبقية هذه الساعة: {n} من {m}', expiry: 'تنتهي الجلسة عند ',
  tab_ask: 'اسأل الوكيل', tab_exp: 'مصروفاتي',
  ask_intro: 'اطرح سؤالاً عن مصروفاتك. كل رقم في الجواب يُطابَق مع سجلاتك قبل أن تراه.',
  exp_intro: 'أضف مصروفاً أو تصفّح شهراً. لا يرى هذه السجلات غيرك، ويقرؤها الوكيل بأدوات للقراءة فقط.',
  question: 'سؤالك', example: 'مثال: كم صرفت في أكتوبر 2026؟', send: 'اسأل', answer: 'الجواب',
  ex1: 'كم صرفت في أكتوبر 2026؟', ex2: 'على ماذا صرفت أكثر في أكتوبر 2026؟', ex3: 'اعرض مصروفاتي في أكتوبر 2026.',
  how: 'كيف عرفنا', privacy: 'فحص الخصوصية', tech: 'تفاصيل تقنية',
  tools: 'الأدوات المستخدمة: ', period: 'الفترة: ', source: 'المصدر: مصروفاتك أنت (قراءة فقط، بيانات تجريبية).', no_tools: 'لم يحتج هذا الجواب إلى أي سجل.',
  masked: 'قبل أن يرى النموذج سؤالك أخفينا: {c}. لم تُرسَل أي قيمة شخصية.', nothing: 'لم يكن هناك ما يلزم إخفاؤه، ولم تُرسَل أي قيمة شخصية.',
  add: 'إضافة مصروف', date: 'التاريخ', merchant: 'الجهة', category: 'الفئة', amount: 'المبلغ (ر.س)', amount_h: 'المبلغ', note: 'ملاحظة', save: 'إضافة',
  list: 'مصروفاتي', month: 'الشهر', empty: 'لا توجد مصروفات في هذا الشهر بعد.', total: 'إجمالي {m}: {v} في {n} مصروف.', saved: 'أُضيف المصروف.',
  food: 'طعام', transport: 'مواصلات', shopping: 'تسوّق', bills: 'فواتير', subscriptions: 'اشتراكات', health: 'صحة', travel: 'سفر', other: 'أخرى',
  monthly_total: 'إجمالي المصروفات', spending_by_category: 'الإنفاق حسب الفئة', find_transactions: 'المصروفات بالتفصيل',
  EMAIL_ADDRESS: 'البريد الإلكتروني', PHONE_NUMBER: 'رقم الهاتف', PERSON_NAME: 'اسم شخص', CREDIT_CARD_NUMBER: 'رقم بطاقة',
  IBAN_CODE: 'حساب بنكي (IBAN)', STREET_ADDRESS: 'عنوان', LOCATION: 'موقع', DATE_OF_BIRTH: 'تاريخ الميلاد',
  e_wrong_username_or_password: 'اسم المستخدم أو كلمة المرور غير صحيحة.', e_too_many_attempts: 'محاولات خاطئة كثيرة لهذا الاسم. حاول بعد 15 دقيقة.',
  e_username_and_password_required: 'أدخل اسم المستخدم وكلمة المرور.', e_sign_in_required: 'انتهت جلستك. سجّل الدخول مرة أخرى.',
  e_default: 'حدث خطأ. لم يتغير شيء.',
  r_ungrounded_numbers: 'احتوى الجواب على رقم غير موجود في سجلاتك، فلم يُعرض. جرّب السؤال عن شهر محدد.',
  r_ungrounded_claim: 'أستطيع الإجابة فقط من المصروفات التي أدخلتها (التاريخ، الجهة، الفئة، المبلغ، الملاحظة). لا أستطيع تأكيد الفواتير أو المدفوعات أو الاسترداد أو تسجيل أي شيء.',
  r_rate_limited: 'وصلت إلى حد 20 سؤالاً في الساعة.', r_token_budget_exhausted: 'نفدت ميزانيتك اليومية للذكاء الاصطناعي. حاول غداً.',
  r_question_length: 'يجب أن يكون السؤال بين 1 و500 حرف.', r_redaction_unavailable: 'خدمة إخفاء البيانات غير متاحة الآن، فلم يُرسَل شيء إلى النموذج.',
  r_model_unavailable: 'نموذج الذكاء الاصطناعي غير متاح الآن.', r_step_limit: 'تجاوز الوكيل عدد الخطوات المسموح فتوقّف.',
  r_tool_arguments_rejected: 'طلب الوكيل السجلات بطريقة لا تسمح بها المنصة، فتوقّف.',
  r_default: 'تعذّر على الوكيل الإجابة بأمان، فلم يُعرض شيء.',
  tour_f0_t: 'تسجيل الدخول', tour_f0_b: 'سجّل الدخول باسمك. لن ترى أبداً إلا سجلاتك أنت.',
  tour_f1_t: 'ماذا يفعل هذا الوكيل', tour_f1_b: 'يجيب عن أسئلتك حول مصروفاتك أنت فقط — وليس مصروفات أي شخص آخر.',
  tour_f2_t: 'جلستك', tour_f2_b: 'الحالة المباشرة، وعدد أسئلتك المتبقية هذه الساعة، ووقت انتهاء الجلسة.',
  tour_f3_t: 'اسأل', tour_f3_b: 'اكتب سؤالاً أو اختر مثالاً، بحد أقصى 500 حرف.',
  tour_f4_t: 'الجواب ودليله', tour_f4_b: 'يظهر الجواب أولاً، ثم كيف عرفنا (الأدوات والفترة) وفحص الخصوصية.',
  tour_f5_t: 'سجلاتك', tour_f5_b: 'أضف مصروفاتك وتصفّح أي شهر هنا. يستطيع الوكيل قراءتها ولا يستطيع تغييرها أبداً.',
});

const $ = id => document.getElementById(id);
const fill = (s, v) => s.replace(/\{(\w+)\}/g, (_, k) => String(v[k]));
const err = code => (t('e_' + code) !== 'e_' + code ? t('e_' + code) : t('e_default'));
let csrf = null, me = null, last = null, expenses = [];

async function api(method, path, body) {
  const headers = {};
  if (body) headers['Content-Type'] = 'application/json';
  if (csrf && method === 'POST') headers['X-CSRF'] = csrf;
  const r = await fetch(path, {method, headers, credentials: 'same-origin', body: body ? JSON.stringify(body) : undefined});
  let value = {}; try { value = await r.json(); } catch (e) { value = {}; }
  return {ok: r.ok, status: r.status, value};
}
function strip() {
  if (!me) return;
  $('who').replaceChildren(t('who'), el('strong', {}, me.name));
  const l = me.limits || {};
  $('left').textContent = l.questions_this_hour !== undefined ? fill(t('left'), {n: l.questions_this_hour, m: l.questions_per_hour || 20}) : '';
  $('expiry').textContent = me.expires_at ? t('expiry') + fmt.time(new Date(me.expires_at * 1000)) : '';
}
function signedIn(value) {
  me = value; csrf = value.csrf;
  $('signin').hidden = true; $('app').hidden = false; $('logout').hidden = false;
  strip(); load();
}
function examples() {
  $('examples').replaceChildren(...['ex1', 'ex2', 'ex3'].map(k => {
    const b = el('button', {type: 'button'}, t(k));
    b.onclick = () => { $('question').value = t(k); $('count').textContent = String($('question').value.length); $('question').focus(); };
    return b;
  }));
}
function categories() {
  const current = $('category').value;
  $('category').replaceChildren(...CATEGORIES.map(c => el('option', {value: c}, t(c))));
  if (current) $('category').value = current;
}
function renderExpenses() {
  $('month-label').textContent = $('month').value ? fmt.month($('month').value) : '';
  $('rows').replaceChildren(...expenses.map(e => el('tr', {},
    el('td', {}, fmt.day(e.date)), el('td', {}, el('bdi', {}, e.merchant)), el('td', {}, t(e.category)),
    el('td', {class: 'num'}, fmt.money(e.amount_minor)), el('td', {}, el('bdi', {}, e.note || '')))));
  $('empty').hidden = expenses.length > 0;
  const sum = expenses.reduce((a, e) => a + e.amount_minor, 0);
  $('total').textContent = expenses.length ? fill(t('total'), {m: fmt.month($('month').value), v: fmt.money(sum), n: expenses.length}) : '';
}
async function load() {
  const r = await api('GET', '/api/expenses?month=' + encodeURIComponent($('month').value));
  if (!r.ok) { $('status').textContent = err(r.value.error); return; }
  expenses = r.value.expenses; renderExpenses();
}
// On the Arabic page an amount reads "830.49 ر.س" like the rest of the UI, whatever order the model used (display only;
// the answer was already checked against the records on the server).
function currency(text) {
  if (UI.lang !== 'ar') return text;
  return text.replace(/(?:SAR|ر\.?\s?س\.?|ريال)\s*(\d+(?:[.,]\d+)?)/g, '$1 ر.س').replace(/(\d+(?:[.,]\d+)?)\s*SAR\b/g, '$1 ر.س');
}
function renderAnswer() {
  if (!last) return;
  const v = last, answered = v.status === 'answered';
  $('answer').hidden = false;
  $('answer-text').hidden = !answered;
  $('answer-text').textContent = answered ? currency(UI.latin(v.answer)) : '';
  $('refusal').hidden = answered;
  $('refusal-text').textContent = answered ? '' : (t('r_' + v.reason) !== 'r_' + v.reason ? t('r_' + v.reason) : t('r_default'));
  const how = v.how_we_know;
  $('how').replaceChildren(...(how && how.tools.length ? [
    el('li', {}, t('tools') + how.tools.map(x => t(x)).join(UI.lang === 'ar' ? '، ' : ', ')),
    how.months.length ? el('li', {}, t('period') + how.months.map(m => fmt.month(m)).join(UI.lang === 'ar' ? '، ' : ', ')) : null,
    el('li', {}, t('source'))] : [el('li', {}, t('no_tools'))]));
  const masked = (v.privacy && v.privacy.masked_before_model) || [];
  $('privacy').replaceChildren(...(masked.length
    ? fill(t('masked'), {c: '\u0000'}).split('\u0000').flatMap((part, i) => i ? [el('strong', {}, masked.map(c => (t(c) !== c ? t(c) : ltr(c))).flatMap((x, j) => j ? [UI.lang === 'ar' ? '، ' : ', ', x] : [x])), part] : [part])
    : [t('nothing')]));
  $('raw').textContent = JSON.stringify(v, null, 2);
}
function spentLabel() { const v = $('spent_on').value; $('spent-label').textContent = /^\d{4}-\d{2}-\d{2}$/.test(v) ? fmt.day(v) : ''; }
function localized() { categories(); examples(); strip(); renderExpenses(); renderAnswer(); spentLabel(); }
$('spent_on').addEventListener('input', spentLabel);

$('login').onclick = async () => {
  const r = await api('POST', '/api/login', {username: $('username').value.trim(), password: $('password').value});
  $('password').value = '';
  if (r.ok) {
    $('status').textContent = ''; signedIn(r.value);
    let seen = null; try { seen = window.localStorage.getItem('tour:financial:app'); window.localStorage.setItem('tour:financial:app', '1'); } catch (e) { seen = '1'; }
    if (!seen) window.setTimeout(() => $('tour').onclick(), 300);  // first sign-in: show the full tour once
  } else $('status').textContent = err(r.value.error);
};
$('password').onkeydown = ev => { if (ev.key === 'Enter') $('login').onclick(); };
$('logout').onclick = async () => { await api('POST', '/api/logout', {}); window.location.reload(); };
$('month').onchange = load;
$('save').onclick = async () => {
  const body = {spent_on: $('spent_on').value, merchant: $('merchant').value, category: $('category').value,
                amount: UI.latin($('amount').value.trim()), note: $('note').value};
  const r = await api('POST', '/api/expenses', body);
  $('status').textContent = r.ok ? t('saved') : err(r.value.error);
  if (r.ok) { $('merchant').value = $('amount').value = $('note').value = ''; $('month').value = body.spent_on.slice(0, 7); load(); }
};
$('question').oninput = () => { $('count').textContent = String($('question').value.length); };
$('send').onclick = async () => {
  const question = $('question').value.trim();
  if (!question) return;
  $('send').disabled = true;
  try {
    const r = await api('POST', '/api/ask', {question, language: UI.lang});
    if (r.status === 401) { $('status').textContent = err('sign_in_required'); return; }
    last = r.value; if (r.value.limits && me) me.limits = r.value.limits;
    strip(); renderAnswer();
  } finally { $('send').disabled = false; }
};
for (const [tab, panel] of [['tab-ask', 'panel-ask'], ['tab-exp', 'panel-exp']]) {
  $(tab).onclick = () => {
    for (const [other, otherPanel] of [['tab-ask', 'panel-ask'], ['tab-exp', 'panel-exp']]) {
      $(other).setAttribute('aria-selected', String(other === tab)); $(otherPanel).hidden = other !== tab;
    }
  };
}
UI.onLang(localized);
(async () => {
  const now = new Date();
  $('month').value = now.toISOString().slice(0, 7); $('spent_on').value = now.toISOString().slice(0, 10); spentLabel();
  const r = await api('GET', '/api/me');
  if (r.ok) signedIn(r.value);
  UI.start([
    {sel: '#signin', title: 'tour_f0_t', body: 'tour_f0_b'},
    {sel: '#fin-intro', title: 'tour_f1_t', body: 'tour_f1_b'}, {sel: '#strip', title: 'tour_f2_t', body: 'tour_f2_b'},
    {sel: '#ask-card', title: 'tour_f3_t', body: 'tour_f3_b'}, {sel: '#answer', title: 'tour_f4_t', body: 'tour_f4_b'},
    {sel: '#tab-exp', title: 'tour_f5_t', body: 'tour_f5_b'}]);
  const tab = UI_PARAMS().get('tab');
  if (tab === 'expenses') $('tab-exp').onclick();
})();
})();
