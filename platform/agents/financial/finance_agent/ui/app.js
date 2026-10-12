'use strict';
// Minimal, functional page (the full UI redesign comes later). textContent only; no innerHTML.
const $ = id => document.getElementById(id);
const CATEGORIES = ['food', 'transport', 'shopping', 'bills', 'health', 'travel', 'other'];
const T = {
  en: {title: 'Financial Agent', logout: 'Sign out', intro: 'Add your expenses, then ask about them in your own words. The agent reads only your own records, hides personal data before anything reaches the AI model, and shows how it knows.',
    signin: 'Sign in', username: 'Username', password: 'Password', login: 'Sign in', add: 'Add an expense', date: 'Date', merchant: 'Merchant',
    category: 'Category', amount: 'Amount (SAR)', note: 'Note', save: 'Add', list: 'My expenses', month: 'Month', show: 'Show',
    empty: 'No expenses in this month yet.', ask: 'Ask the agent', send: 'Ask', how: 'How we know', privacy: 'Privacy check',
    hello: 'Signed in as ', saved: 'Expense added.', masked: 'Masked before the AI model saw it: ', nothing: 'Nothing personal needed masking.',
    tools: 'Tools used: ', months: 'Month: ', source: 'Source: your own expenses (read-only).', limits: 'Questions left this hour: ',
    food: 'Food', transport: 'Transport', shopping: 'Shopping', bills: 'Bills', health: 'Health', travel: 'Travel', other: 'Other',
    monthly_total: 'monthly total', spending_by_category: 'spending by category', find_transactions: 'transaction lookup',
    reasons: {ungrounded_numbers: 'The answer contained a number that is not in your records, so it was not shown.',
      ungrounded_claim: 'I can only answer from the expenses you entered (date, merchant, category, amount, note). I cannot confirm invoices, payments, refunds or whether something is recorded.',
      rate_limited: 'You reached the limit of 20 questions per hour.', token_budget_exhausted: 'Your daily AI budget is used up.',
      question_length: 'Questions must be 1–500 characters.', redaction_unavailable: 'Privacy masking is unavailable, so nothing was sent to the AI model.',
      model_unavailable: 'The AI model is unavailable right now.', step_limit: 'The agent took too many steps and stopped.',
      default: 'The agent could not answer this safely, so nothing was shown.'}},
  ar: {title: 'الوكيل المالي', logout: 'تسجيل الخروج', intro: 'أضف مصروفاتك ثم اسأل عنها بكلماتك. يقرأ الوكيل سجلاتك أنت فقط، ويخفي البيانات الشخصية قبل وصولها إلى نموذج الذكاء الاصطناعي، ويبيّن مصدر كل رقم.',
    signin: 'تسجيل الدخول', username: 'اسم المستخدم', password: 'كلمة المرور', login: 'دخول', add: 'إضافة مصروف', date: 'التاريخ', merchant: 'الجهة',
    category: 'الفئة', amount: 'المبلغ (ر.س)', note: 'ملاحظة', save: 'إضافة', list: 'مصروفاتي', month: 'الشهر', show: 'عرض',
    empty: 'لا توجد مصروفات في هذا الشهر بعد.', ask: 'اسأل الوكيل', send: 'اسأل', how: 'كيف عرفنا', privacy: 'فحص الخصوصية',
    hello: 'مسجّل الدخول باسم ', saved: 'أُضيف المصروف.', masked: 'أُخفي قبل وصوله إلى النموذج: ', nothing: 'لم يكن هناك ما يلزم إخفاؤه.',
    tools: 'الأدوات المستخدمة: ', months: 'الشهر: ', source: 'المصدر: مصروفاتك أنت (قراءة فقط).', limits: 'الأسئلة المتبقية هذه الساعة: ',
    food: 'طعام', transport: 'مواصلات', shopping: 'تسوّق', bills: 'فواتير', health: 'صحة', travel: 'سفر', other: 'أخرى',
    monthly_total: 'إجمالي الشهر', spending_by_category: 'الإنفاق حسب الفئة', find_transactions: 'البحث في العمليات',
    reasons: {ungrounded_numbers: 'احتوى الجواب على رقم غير موجود في سجلاتك، فلم يُعرض.',
      ungrounded_claim: 'أستطيع الإجابة فقط من المصروفات التي أدخلتها (التاريخ، الجهة، الفئة، المبلغ، الملاحظة). لا أستطيع تأكيد الفواتير أو المدفوعات أو الاسترداد أو تسجيل أي شيء.',
      rate_limited: 'وصلت إلى حد 20 سؤالاً في الساعة.', token_budget_exhausted: 'نفدت ميزانيتك اليومية للذكاء الاصطناعي.',
      question_length: 'يجب أن يكون السؤال بين 1 و500 حرف.', redaction_unavailable: 'خدمة الإخفاء غير متاحة، فلم يُرسل شيء إلى النموذج.',
      model_unavailable: 'النموذج غير متاح الآن.', step_limit: 'تجاوز الوكيل عدد الخطوات المسموح فتوقّف.',
      default: 'تعذّر على الوكيل الإجابة بأمان، فلم يُعرض شيء.'}}
};
let lang = 'en', csrf = null;
const t = key => T[lang][key] || key;
function localize() {
  document.documentElement.lang = lang; document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
  document.querySelectorAll('[data-t]').forEach(el => { el.textContent = t(el.dataset.t); });
  $('lang').textContent = lang === 'ar' ? 'English' : 'العربية';
  $('category').replaceChildren(...CATEGORIES.map(c => { const o = document.createElement('option'); o.value = c; o.textContent = t(c); return o; }));
}
async function api(method, path, body) {
  const headers = {}; if (body) headers['Content-Type'] = 'application/json'; if (csrf && method === 'POST') headers['X-CSRF'] = csrf;
  const r = await fetch(path, {method, headers, credentials: 'same-origin', body: body ? JSON.stringify(body) : undefined});
  let value = {}; try { value = await r.json(); } catch (e) { value = {}; }
  return {ok: r.ok, status: r.status, value};
}
const money = minor => (minor / 100).toFixed(2);
function signedIn(value) {
  csrf = value.csrf; $('signin').hidden = true; $('app').hidden = false; $('logout').hidden = false;
  $('who').textContent = t('hello') + value.name; limits(value.limits); load();
}
function limits(l) { if (l) $('limits').textContent = t('limits') + l.questions_this_hour; }
async function load() {
  const r = await api('GET', '/api/expenses?month=' + encodeURIComponent($('month').value));
  if (!r.ok) { $('status').textContent = r.value.error || ''; return; }
  $('rows').replaceChildren(...r.value.expenses.map(e => {
    const tr = document.createElement('tr');
    [e.date, e.merchant, t(e.category), money(e.amount_minor), e.note].forEach(v => { const td = document.createElement('td'); const b = document.createElement('bdi'); b.textContent = v; td.append(b); tr.append(td); });
    return tr;
  }));
  $('empty').hidden = r.value.expenses.length > 0;
}
$('lang').onclick = () => { lang = lang === 'en' ? 'ar' : 'en'; localize(); };
$('login').onclick = async () => {
  const r = await api('POST', '/api/login', {username: $('username').value.trim(), password: $('password').value});
  $('password').value = '';
  if (r.ok) signedIn(Object.assign(r.value, {limits: null})); else $('status').textContent = r.value.error || '';
};
$('logout').onclick = async () => { await api('POST', '/api/logout', {}); location.reload(); };
$('load').onclick = load;
$('save').onclick = async () => {
  const body = {spent_on: $('spent_on').value, merchant: $('merchant').value, category: $('category').value, amount: $('amount').value.trim(), note: $('note').value};
  const r = await api('POST', '/api/expenses', body);
  $('status').textContent = r.ok ? t('saved') : (r.value.error || '');
  if (r.ok) { $('merchant').value = $('amount').value = $('note').value = ''; load(); }
};
$('question').oninput = () => { $('count').textContent = $('question').value.length; };
$('send').onclick = async () => {
  const r = await api('POST', '/api/ask', {question: $('question').value, language: lang});
  const v = r.value; $('answer').hidden = false; limits(v.limits);
  $('answer-text').textContent = v.status === 'answered' ? v.answer : (T[lang].reasons[v.reason] || T[lang].reasons.default);
  $('how').textContent = v.how_we_know ? t('tools') + v.how_we_know.tools.map(t).join('، ') + ' · ' + t('months') + v.how_we_know.months.join(', ') + ' · ' + t('source') : '';
  const masked = (v.privacy && v.privacy.masked_before_model) || [];
  $('privacy').textContent = masked.length ? t('masked') + masked.join(', ') : t('nothing');
};
(async () => {
  localize();
  const now = new Date(); $('month').value = now.toISOString().slice(0, 7); $('spent_on').value = now.toISOString().slice(0, 10);
  const r = await api('GET', '/api/me'); if (r.ok) signedIn(r.value);
})();
