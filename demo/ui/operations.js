'use strict';
const node = id => document.getElementById(id);
const words = {
  en: {'heading':'Security & Operations','language-label':'Language','operations-tab':'Operations','security-tab':'Security','services-heading':'Services and storage','refresh':'Refresh registered targets','target-label':'Registered target','observe':'Observe','explain':'Model explanation','incident-heading':'Incident, evidence and unknowns','policy-heading':'Policy and proposed action','propose':'Propose exact action','approval-heading':'Operator approval','approval-help':'Read operator-approval.secret in private server state. Review action, target and evidence before approving. Models cannot approve.','approve':'Approve proposal','execute':'Execute once','outcome-heading':'Verified outcome','security-heading':'Digest-linked security evidence','security-help':'Retained scan and native signature receipts. Current application qualification is separate.','security-refresh':'Evaluate registered evidence','budget-heading':'Budgets and expiry','financial':'Open financial conversation','notice':'Actual local monitoring and approved actions remain available without LiteLLM. Model explanation is disabled unless a scoped local stub client is configured; live mode is disabled.'},
  ar: {'heading':'وكيل الأمن والعمليات','language-label':'اللغة','operations-tab':'العمليات','security-tab':'الأمن','services-heading':'الخدمات والتخزين','refresh':'تحديث الأهداف المسجلة','target-label':'الهدف المسجل','observe':'فحص','explain':'شرح النموذج','incident-heading':'الحادث والأدلة والمجهول','policy-heading':'قرار السياسة والإجراء المقترح','propose':'اقتراح الإجراء المحدد','approval-heading':'موافقة المشغّل','approval-help':'اقرأ operator-approval.secret من حالة الخادم الخاصة. راجع الإجراء والهدف والدليل قبل الموافقة. لا يستطيع النموذج منح الموافقة.','approve':'الموافقة على المقترح','execute':'تنفيذ مرة واحدة','outcome-heading':'النتيجة المتحقق منها','security-heading':'أدلة الأمن المرتبطة ببصمة الصورة','security-help':'أدلة فحص وتحقق توقيع محفوظة. تأهيل التطبيق الحالي منفصل.','security-refresh':'تقييم الأدلة المسجلة','budget-heading':'الحدود والانتهاء','financial':'فتح المحادثة المالية','notice':'الفحص المحلي والإجراءات المعتمدة متاحان عند تعطل LiteLLM. شرح النموذج معطّل ما لم يُضبط عميل اختبار محلي محدود. الوضع الحي معطّل.'}
};
let csrf, observation, proposal, approval, busy = false, latestBudgets;
function show(id, value) { node(id).textContent = JSON.stringify(value, null, 2); }
function budgets(value) { latestBudgets=value; show('budgets',value); node('expiry').textContent=(node('language').value==='ar'?'انتهاء جلسة المشغّل: ':'Operator session expires: ')+new Date(value.expiry_epoch*1000).toLocaleString(node('language').value==='ar'?'ar-SA':'en-GB')+(node('language').value==='ar'?' — لا تحديث تلقائي أو إعادة محاولة.':' — No automatic refresh or retry.'); }
function localize() {
  const lang = node('language').value;
  document.documentElement.lang = lang; document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
  Object.entries(words[lang]).forEach(([id, value]) => { node(id).textContent = value; });
  node('action').options[0].textContent = lang === 'ar' ? 'استعادة عملية مسجلة يتيمة' : 'Recover registered orphan';
  node('action').options[1].textContent = lang === 'ar' ? 'تنظيف ذاكرة مؤقتة مسجلة' : 'Clean registered cache';
  if(latestBudgets)budgets(latestBudgets);
}
async function call(operation, fields = {}) {
  if (busy) return null;
  busy = true;
  document.querySelectorAll('button').forEach(x => { x.disabled = true; });
  try {
    const response = await fetch('/api/operations', {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json','X-Demo-CSRF':csrf}, body:JSON.stringify({operation, ...fields})});
    const value = await response.json();
    if (value.budgets) budgets(value.budgets);
    node('status').textContent = response.ok ? 'OK' : value.error;
    return value;
  } finally { busy = false; document.querySelectorAll('button').forEach(x => { x.disabled = false; }); }
}
async function refresh() {
  const value = await call('overview'); if (!value || !value.targets) return;
  node('target').replaceChildren(...value.targets.map(t => { const x=document.createElement('option'); x.value=t.target_id; x.textContent=t.target_id + (t.mutable?'':' [read-only]'); return x; }));
  budgets(value.budgets);
}
node('language').onchange = localize;
node('refresh').onclick = refresh;
node('observe').onclick = async () => { observation=await call('observe',{target_id:node('target').value}); proposal=approval=null; show('incident',observation); show('proposal',null); show('approval',null); };
node('explain').onclick = async () => { show('incident',await call('explain',{target_id:node('target').value})); };
node('propose').onclick = async () => { if(!observation || observation.target_id!==node('target').value)return; proposal=await call('propose',{target_id:observation.target_id,action:node('action').value,evidence_id:observation.evidence_id}); approval=null; show('proposal',proposal); };
node('approve').onclick = async () => { if(!proposal || !proposal.request_id)return; const secret=node('operator-secret').value; node('operator-secret').value=''; approval=await call('approve',{request_id:proposal.request_id,operator_secret:secret}); show('approval',approval); };
node('execute').onclick = async () => { if(!approval || !approval.approval_id)return; const saved=approval; approval=null; show('outcome',await call('execute',{request_id:saved.request_id,approval_id:saved.approval_id})); };
node('security-refresh').onclick = async () => { show('security-evidence',await call('security')); };
for(const name of ['operations','security'])node(name+'-tab').onclick=()=>{for(const other of ['operations','security']){node(other).hidden=other!==name;node(other+'-tab').setAttribute('aria-selected',String(other===name));}};
async function start(){localize();const response=await fetch('/api/bootstrap',{credentials:'same-origin'});const value=await response.json();csrf=value.csrf;await refresh();}
start().catch(()=>{node('status').textContent='PRIVATE_STARTUP_BLOCKED';});
