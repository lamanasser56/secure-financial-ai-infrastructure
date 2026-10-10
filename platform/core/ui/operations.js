'use strict';
const node = id => document.getElementById(id);
const words = {
  en: {'heading':'Security & Operations','language-label':'Language','operations-tab':'Operations','security-tab':'Security','services-heading':'Services and storage','refresh':'Refresh registered targets','target-label':'Registered target','observe':'Observe','explain':'Model explanation','incident-heading':'Incident, evidence and unknowns','policy-heading':'Policy and proposed action','propose':'Propose exact action','approval-heading':'Operator approval','approval-help':'Read operator-approval.secret in private server state. Review action, target and evidence before approving. Models cannot approve.','approve':'Approve proposal','execute':'Execute once','outcome-heading':'Verified outcome','security-heading':'Digest-linked security evidence','security-help':'Retained scan and native signature receipts. Current application qualification is separate.','security-refresh':'Evaluate registered evidence','budget-heading':'Budgets and expiry','financial':'Open financial conversation','notice':'Actual local monitoring and approved actions remain available without LiteLLM. Model explanation is disabled unless a scoped local stub client is configured; live mode is disabled.'},
  ar: {'heading':'وكيل الأمن والعمليات','language-label':'اللغة','operations-tab':'العمليات','security-tab':'الأمن','services-heading':'الخدمات والتخزين','refresh':'تحديث الأهداف المسجلة','target-label':'الهدف المسجل','observe':'فحص','explain':'شرح النموذج','incident-heading':'الحادث والأدلة والمجهول','policy-heading':'قرار السياسة والإجراء المقترح','propose':'اقتراح الإجراء المحدد','approval-heading':'موافقة المشغّل','approval-help':'اقرأ operator-approval.secret من حالة الخادم الخاصة. راجع الإجراء والهدف والدليل قبل الموافقة. لا يستطيع النموذج منح الموافقة.','approve':'الموافقة على المقترح','execute':'تنفيذ مرة واحدة','outcome-heading':'النتيجة المتحقق منها','security-heading':'أدلة الأمن المرتبطة ببصمة الصورة','security-help':'أدلة فحص وتحقق توقيع محفوظة. تأهيل التطبيق الحالي منفصل.','security-refresh':'تقييم الأدلة المسجلة','budget-heading':'الحدود والانتهاء','financial':'فتح المحادثة المالية','notice':'الفحص المحلي والإجراءات المعتمدة متاحان عند تعطل LiteLLM. شرح النموذج معطّل ما لم يُضبط عميل اختبار محلي محدود. الوضع الحي معطّل.'}
};
let csrf, observation, proposal, approval, busy = false, latestBudgets;
words.en.diagnose='Diagnose current evidence'; words.ar.diagnose='تشخيص الدليل الحالي';
Object.assign(words.en,{'activity-heading':'Agent activity','pending-heading':'Pending approvals','timeline-heading':'Timeline: observed → diagnosed → proposed → approved → executed → verified','denials-heading':'Policy denials'});
Object.assign(words.ar,{'activity-heading':'نشاط الوكيل','pending-heading':'موافقات معلّقة','timeline-heading':'الخط الزمني: رُصد ← شُخّص ← اقتُرح ← وُوفق ← نُفّذ ← تُحقّق','denials-heading':'حالات الرفض بالسياسة'});
const clusterActions={restart:['Rollout restart','إعادة تشغيل متدرجة'],rollback:['Rollback to previous revision','الرجوع إلى المراجعة السابقة'],scale:['Bounded scale','تحجيم ضمن الحدود']};
function items(id, rows, render) { node(id).replaceChildren(...rows.map(r => { const li=document.createElement('li'); li.textContent=render(r); return li; })); }
function activity(value) {
  if (!value || !value.timeline) return;
  node('activity').hidden=false;
  items('pending', value.pending||[], p => p.target+' · '+p.action+' · '+p.finding+' · '+p.request_id);
  items('timeline', (value.timeline||[]).slice(-30).reverse(), e => new Date(e.at*1000).toLocaleTimeString()+' '+e.stage+' '+(e.target||'')+(e.code?' '+e.code:'')+(e.action?' '+e.action:''));
  items('denials', value.denials||[], e => new Date(e.at*1000).toLocaleTimeString()+' '+(e.target||'')+' '+e.code);
}
function show(id, value) { node(id).textContent = JSON.stringify(value, null, 2); }
function budgets(value) { latestBudgets=value; show('budgets',value); node('expiry').textContent=(node('language').value==='ar'?'انتهاء جلسة المشغّل: ':'Operator session expires: ')+new Date(value.expiry_epoch*1000).toLocaleString(node('language').value==='ar'?'ar-SA':'en-GB')+(node('language').value==='ar'?' — لا تحديث تلقائي أو إعادة محاولة.':' — No automatic refresh or retry.'); }
function localize() {
  const lang = node('language').value;
  document.documentElement.lang = lang; document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
  Object.entries(words[lang]).forEach(([id, value]) => { node(id).textContent = value; });
  const labels=Object.assign({restore:['Restore failed owned service','استعادة الخدمة المملوكة المتعطلة'],test_failure:['Controlled owned service failure','تعطيل اختباري للخدمة المملوكة'],recover:['Stop registered orphan','إيقاف العملية اليتيمة المسجلة'],clean:['Clean registered cache','تنظيف ذاكرة مؤقتة مسجلة']},clusterActions);
  Array.from(node('action').options).forEach(x=>{x.textContent=labels[x.value][lang==='ar'?1:0];});
  if(latestBudgets){budgets(latestBudgets);if(latestBudgets.live_enabled)node('notice').textContent=lang==='ar'?'تجربة حية اصطناعية مُشرفة ومحدودة. لا بيانات شخصية أو ترقية لسلطة التنقيح. قرارات السياسة والموافقة من الخادم.':'Bounded supervised synthetic live trial. No personal data or redaction promotion. Server policy and approval remain authoritative.';}
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
  node('financial').href=value.financial_ui;
  if (value.actions) { node('action').replaceChildren(...value.actions.map(a => { const x=document.createElement('option'); x.value=a; x.textContent=clusterActions[a][node('language').value==='ar'?1:0]; return x; })); }
  activity(value);
}
node('language').onchange = localize;
node('refresh').onclick = refresh;
node('observe').onclick = async () => { observation=await call('observe',{target_id:node('target').value}); proposal=approval=null; show('incident',observation); show('proposal',null); show('approval',null); };
node('diagnose').onclick = async () => { if(!observation || !observation.evidence_id)return; const value=await call('diagnose',{target_id:observation.target_id,evidence_id:observation.evidence_id});show('diagnosis',value);if(value.permitted_action)node('action').value=value.permitted_action; };
node('explain').onclick = async () => { const value=await call('explain',{target_id:node('target').value});if(value && value.evidence)observation=value.evidence;show('diagnosis',value); };
node('propose').onclick = async () => { if(!observation || observation.target_id!==node('target').value)return; proposal=await call('propose',{target_id:observation.target_id,action:node('action').value,evidence_id:observation.evidence_id}); approval=null; show('proposal',proposal); };
node('approve').onclick = async () => { if(!proposal || !proposal.request_id)return; const secret=node('operator-secret').value; node('operator-secret').value=''; approval=await call('approve',{request_id:proposal.request_id,operator_secret:secret}); show('approval',approval); };
node('execute').onclick = async () => { if(!approval || !approval.approval_id)return; const saved=approval; approval=null; show('outcome',await call('execute',{request_id:saved.request_id,approval_id:saved.approval_id})); };
node('security-refresh').onclick = async () => { show('security-evidence',await call('security')); };
for(const name of ['operations','security'])node(name+'-tab').onclick=()=>{for(const other of ['operations','security']){node(other).hidden=other!==name;node(other+'-tab').setAttribute('aria-selected',String(other===name));}};
async function start(){localize();const response=await fetch('/api/bootstrap',{credentials:'same-origin'});const value=await response.json();csrf=value.csrf;await refresh();}
start().catch(()=>{node('status').textContent='PRIVATE_STARTUP_BLOCKED';});
