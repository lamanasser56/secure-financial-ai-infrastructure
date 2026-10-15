'use strict';
// Security & Operations page: status board, incident flow (proposal -> owner approval -> execute once -> verify),
// timeline, denials and the security checklist. Uses UI from app.js. textContent only; no automatic retry of actions.
(() => {
const {t, el, ltr, fmt} = UI;
Object.assign(UI.dict.en, {
  ops_title: 'Security & Operations Agent',
  ops_intro: "This agent watches the platform's services, explains problems in plain language, and fixes them only after your approval. It can restart or resize a service — it can never change what a service runs.",
  tab_ops: 'Operations', tab_sec: 'Security', live: 'Live', refresh: 'Refresh', checked: 'Checked at ', auto: ' · refreshes every 20 seconds',
  ops_tab_intro: "Each card is one service the agent watches. Select a card to see what happened, the agent's proposal and your approval.",
  board_title: 'Service status', tracker_label: 'Incident steps',
  ai_title: 'AI explanation — for information only, it cannot change the action', explain: 'Explain in plain language', ai_none: 'No AI explanation is available for this service right now.',
  prop_title: 'Proposed action', passphrase: 'Owner passphrase', approve: 'Approve', execute: 'Execute once',
  approve_note: 'Your approval is valid once, for this action on this service, for 5 minutes.', expires: 'Proposal expires at ',
  approved: 'Approved. The approval is valid once for 5 minutes — execute it now.',
  pending_title: 'Pending approvals', pending_empty: 'No pending approvals.',
  denials_title: 'Policy denials', denials_empty: 'No policy denials yet — denials appear here when a request breaks a rule.',
  timeline_title: 'Timeline', timeline_intro: 'Only meaningful changes are listed; repeated healthy checks are folded into one line.', timeline_empty: 'No activity yet.',
  tech: 'Technical details',
  sec_tab_intro: 'What the platform checked before running anything. Live checks run now against the cluster; the others were verified by the attack suite.',
  sec_run: 'Run the live checks', sec_when: 'Live checks ran at ', pass: 'Pass', fail: 'Fail', live_check: 'Live check', verified: 'Verified by the attack suite',
  s_idle: 'Idle — scaled to zero', s_ok: 'Healthy — no action needed', s_degraded: 'Degraded — not ready to serve', s_crash: 'Failing — keeps crashing',
  s_oom: 'Failing — runs out of memory', s_pull: 'Failing — the image cannot be pulled', s_admission: 'Blocked — the image is not signed and attested',
  s_pending: 'Waiting — no room to start', watched: 'Watched only — the agent never changes it', ready: ' ready', of: ' of ',
  w_ok: 'The service is running normally.', w_degraded: 'The service is running but does not answer its health check, so it receives no traffic.',
  w_crash: 'The service starts and stops again and again.', w_oom: 'The service uses more memory than it is allowed.',
  w_pull: 'The service cannot start because its image cannot be downloaded.', w_admission: 'The platform refused to start an image that is not signed and attested.',
  w_pending: 'The service is waiting for room on a node.', w_idle: 'The service is switched off on purpose (0 instances).',
  e_CrashLoopBackOff: 'keeps crashing', e_restarts: 'restarted {n} times', e_NotReady: 'running but not ready', e_OOMKilled: 'ran out of memory',
  e_ImagePullBackOff: 'image could not be pulled', e_ErrImagePull: 'image could not be pulled', e_InvalidImageName: 'invalid image name',
  'e_FailedCreate:admission': 'image rejected by the signature check', e_Unschedulable: 'waiting for room on a node', e_NoPods: 'no instances running',
  own_RAISE_MEMORY_LIMIT_OR_FIX_WORKLOAD: 'Owner action required — no automated fix: raise the memory limit or fix the workload, then redeploy.',
  own_DEPLOY_VALID_SIGNED_DIGEST: 'Owner action required — no automated fix: deploy a valid, signed image.',
  own_DEPLOY_ATTESTED_IMAGE: 'Owner action required — no automated fix: deploy an image with a valid attestation.',
  own_NOTIFY_AGENT_TEAM: "Owner action required — the agent only watches this service: tell the agent's team.",
  a_restart: 'Restart the service', a_scale: 'Add one instance (within its limit)',
  st_observed: 'Detected', st_diagnosed: 'Diagnosed', st_proposed: 'Proposed', st_approved: 'Approved', st_executed: 'Executed', st_verified: 'Verified', st_awaiting: 'Awaiting your approval',
  ev_observed: 'problem detected', ev_diagnosed: 'diagnosis: ', ev_proposed: 'proposed: ', ev_approved: 'approved by the owner', ev_executed: 'executed once: ',
  ev_verified: 'verified: healthy again', ev_failed: 'failed: ', ev_denied: 'denied: ', healthy_since: 'healthy since ',
  out_VERIFIED: 'Verified: the service is healthy again ({a} of {d} ready).', out_NOT_VERIFIED: 'Executed, but the service did not become healthy in time. Nothing was retried.',
  r_UNKNOWN_OR_USED_REQUEST: 'This proposal was already used, replaced or expired. Nothing was changed.',
  r_EXPIRED_OR_STALE: 'Approval expired — approvals are valid for 5 minutes.', r_ALREADY_USED: 'This approval was already used once.',
  r_SIGNATURE_INVALID: 'The approval signature is not valid.', r_CLAIMS_INVALID: 'The approval is malformed.', r_BINDING_MISMATCH: 'The approval was for a different action or service.',
  r_EVIDENCE_CHANGED: 'The situation changed after the proposal, so the approval no longer applies. Nothing was changed.',
  r_OBJECT_CHANGED: 'The service changed after you approved, so nothing was changed. A new proposal will appear.',
  r_TARGET_REPLACED: 'The service was replaced after the proposal, so nothing was changed.',
  r_CONFLICT_OBJECT_CHANGED: 'Someone changed the service at the same moment; the platform refused the change (409).',
  r_SUPERSEDED: 'Replaced by a newer proposal.', r_ADMISSION_REJECTED: 'The cluster policy refused this change.',
  r_NOT_REGISTERED_OR_NOT_ALLOWLISTED: 'This service or action is not allowed for the agent.', r_VERIFICATION_TIMEOUT: 'The service did not become healthy in time.',
  r_APPROVAL_DENIED: 'Wrong passphrase, or this proposal is no longer pending.', r_NO_AGENT_PROPOSAL: 'There is no current proposal for this service.',
  r_ROLLOUT_COMPLETE_AND_HEALTHY: 'healthy again', r_default: 'Refused by policy.',
  n_gateway: 'AI gateway', t_gateway: 'LiteLLM', n_redactor: 'Privacy masking', t_redactor: 'Google SDP', n_app: 'Front door', t_app: 'platform app',
  n_fault: 'Demo workload', t_fault: 'fault-demo', n_financial: 'Financial Agent', t_financial: 'tenant #1',  tour_o1_t: 'What this agent does', tour_o1_b: 'It watches services, explains problems and proposes a fix. It never acts without your approval.',
  tour_o2_t: 'Service status', tour_o2_b: 'One card per service, with a colour, an icon and words. Select a card to open its incident.',
  tour_o3_t: 'The incident', tour_o3_b: 'What happened in plain words, the steps so far, an optional AI explanation, and the proposed action with your approval.',
  tour_o4_t: 'Approvals and denials', tour_o4_b: 'Pending approvals wait here. Anything the policy refused is listed with its reason.',
  tour_o5_t: 'Timeline', tour_o5_b: 'Every meaningful change, newest first.', tour_o6_t: 'Security checks', tour_o6_b: 'The Security tab lists what the platform verifies before anything runs.',
});
Object.assign(UI.dict.ar, {
  ops_title: 'وكيل الأمن والعمليات',
  ops_intro: 'يراقب هذا الوكيل خدمات المنصة، ويشرح المشكلات بلغة بسيطة، ولا يصلحها إلا بعد موافقتك. يستطيع إعادة تشغيل الخدمة أو تغيير حجمها فقط — ولا يستطيع أبداً تغيير ما تشغّله.',
  tab_ops: 'العمليات', tab_sec: 'الأمن', live: 'مباشر', refresh: 'تحديث', checked: 'آخر فحص: ', auto: ' · يتحدث كل 20 ثانية',
  ops_tab_intro: 'كل بطاقة خدمة يراقبها الوكيل. اختر بطاقة لترى ما حدث، واقتراح الوكيل، وموافقتك.',
  board_title: 'حالة الخدمات', tracker_label: 'مراحل الحادثة',
  ai_title: 'شرح الذكاء الاصطناعي — للعلم فقط، ولا يغيّر الإجراء', explain: 'اشرح بلغة بسيطة', ai_none: 'لا يتوفر شرح من الذكاء الاصطناعي لهذه الخدمة الآن.',
  prop_title: 'الإجراء المقترح', passphrase: 'عبارة مرور المالك', approve: 'موافقة', execute: 'تنفيذ مرة واحدة',
  approve_note: 'موافقتك صالحة مرة واحدة، لهذا الإجراء على هذه الخدمة، لمدة 5 دقائق.', expires: 'ينتهي الاقتراح عند ',
  approved: 'تمت الموافقة. الموافقة صالحة مرة واحدة لمدة 5 دقائق — نفّذها الآن.',
  pending_title: 'موافقات معلّقة', pending_empty: 'لا توجد موافقات معلّقة.',
  denials_title: 'حالات الرفض بالسياسة', denials_empty: 'لا توجد حالات رفض بعد — تظهر هنا عندما يخالف طلبٌ إحدى القواعد.',
  timeline_title: 'الخط الزمني', timeline_intro: 'تظهر التغييرات المهمة فقط، وتُدمج الفحوص السليمة المتكررة في سطر واحد.', timeline_empty: 'لا يوجد نشاط بعد.',
  tech: 'تفاصيل تقنية',
  sec_tab_intro: 'ما الذي فحصته المنصة قبل تشغيل أي شيء. الفحوص المباشرة تعمل الآن على العنقود، والبقية تحقق منها اختبار الهجمات.',
  sec_run: 'شغّل الفحوص المباشرة', sec_when: 'آخر تشغيل للفحوص المباشرة: ', pass: 'ناجح', fail: 'فاشل', live_check: 'فحص مباشر', verified: 'تحقق منه اختبار الهجمات',
  s_idle: 'متوقفة — بلا نسخ عاملة', s_ok: 'سليمة — لا حاجة لأي إجراء', s_degraded: 'متدهورة — غير جاهزة للخدمة', s_crash: 'متعطلة — تتوقف باستمرار',
  s_oom: 'متعطلة — تنفد ذاكرتها', s_pull: 'متعطلة — تعذّر تنزيل الصورة', s_admission: 'محجوبة — الصورة غير موقّعة ومعتمدة',
  s_pending: 'بانتظار — لا مكان لتشغيلها', watched: 'مراقبة فقط — لا يغيّرها الوكيل أبداً', ready: ' جاهزة', of: ' من ',
  w_ok: 'الخدمة تعمل بشكل طبيعي.', w_degraded: 'الخدمة تعمل لكنها لا تجتاز فحص الجاهزية، فلا تصلها أي طلبات.',
  w_crash: 'الخدمة تبدأ ثم تتوقف مرة بعد مرة.', w_oom: 'الخدمة تستهلك ذاكرة أكثر من المسموح.',
  w_pull: 'لا تستطيع الخدمة البدء لأن صورتها لا يمكن تنزيلها.', w_admission: 'رفضت المنصة تشغيل صورة غير موقّعة ومعتمدة.',
  w_pending: 'الخدمة تنتظر مكاناً على أحد الخوادم.', w_idle: 'الخدمة متوقفة عمداً (0 نسخ).',
  e_CrashLoopBackOff: 'تتوقف باستمرار', e_restarts: 'أُعيد تشغيلها {n} مرة', e_NotReady: 'تعمل لكنها غير جاهزة', e_OOMKilled: 'نفدت ذاكرتها',
  e_ImagePullBackOff: 'تعذّر تنزيل الصورة', e_ErrImagePull: 'تعذّر تنزيل الصورة', e_InvalidImageName: 'اسم صورة غير صالح',
  'e_FailedCreate:admission': 'رفض فحصُ التوقيع الصورة', e_Unschedulable: 'تنتظر مكاناً على أحد الخوادم', e_NoPods: 'لا توجد نسخ عاملة',
  own_RAISE_MEMORY_LIMIT_OR_FIX_WORKLOAD: 'مطلوب إجراء من المالك — لا يوجد إصلاح آلي: ارفع حد الذاكرة أو أصلح الحمل ثم أعد النشر.',
  own_DEPLOY_VALID_SIGNED_DIGEST: 'مطلوب إجراء من المالك — لا يوجد إصلاح آلي: انشر صورة صالحة وموقّعة.',
  own_DEPLOY_ATTESTED_IMAGE: 'مطلوب إجراء من المالك — لا يوجد إصلاح آلي: انشر صورة تحمل اعتماداً صالحاً.',
  own_NOTIFY_AGENT_TEAM: 'مطلوب إجراء من المالك — الوكيل يراقب هذه الخدمة فقط: أبلغ فريق الوكيل.',
  a_restart: 'إعادة تشغيل الخدمة', a_scale: 'إضافة نسخة واحدة (ضمن الحد)',
  st_observed: 'رُصدت', st_diagnosed: 'شُخّصت', st_proposed: 'اقتُرح إجراء', st_approved: 'وُوفق عليه', st_executed: 'نُفّذ', st_verified: 'تُحقّق منه', st_awaiting: 'بانتظار موافقتك',
  ev_observed: 'رُصدت مشكلة', ev_diagnosed: 'التشخيص: ', ev_proposed: 'اقتراح: ', ev_approved: 'وافق المالك', ev_executed: 'نُفّذ مرة واحدة: ',
  ev_verified: 'تحقق: عادت سليمة', ev_failed: 'فشل: ', ev_denied: 'رُفض: ', healthy_since: 'سليمة منذ ',
  out_VERIFIED: 'تم التحقق: عادت الخدمة سليمة ({a} من {d} جاهزة).', out_NOT_VERIFIED: 'نُفّذ الإجراء لكن الخدمة لم تعد سليمة في الوقت المحدد. لم تُكرَّر أي محاولة.',
  r_UNKNOWN_OR_USED_REQUEST: 'هذا الاقتراح استُخدم أو استُبدل أو انتهت صلاحيته. لم يتغير شيء.',
  r_EXPIRED_OR_STALE: 'انتهت صلاحية الموافقة — الموافقات صالحة لمدة 5 دقائق.', r_ALREADY_USED: 'هذه الموافقة استُخدمت من قبل.',
  r_SIGNATURE_INVALID: 'توقيع الموافقة غير صالح.', r_CLAIMS_INVALID: 'الموافقة غير سليمة البنية.', r_BINDING_MISMATCH: 'الموافقة كانت لإجراء أو خدمة أخرى.',
  r_EVIDENCE_CHANGED: 'تغيّر الوضع بعد الاقتراح، فلم تعد الموافقة سارية. لم يتغير شيء.',
  r_OBJECT_CHANGED: 'تغيّرت الخدمة بعد موافقتك، فلم يُغيَّر شيء. سيظهر اقتراح جديد.',
  r_TARGET_REPLACED: 'استُبدلت الخدمة بعد الاقتراح، فلم يتغير شيء.',
  r_CONFLICT_OBJECT_CHANGED: 'غيّر أحدٌ الخدمة في اللحظة نفسها، فرفضت المنصة التغيير (409).',
  r_SUPERSEDED: 'استُبدل باقتراح أحدث.', r_ADMISSION_REJECTED: 'رفضت سياسة العنقود هذا التغيير.',
  r_NOT_REGISTERED_OR_NOT_ALLOWLISTED: 'هذه الخدمة أو هذا الإجراء غير مسموح للوكيل.', r_VERIFICATION_TIMEOUT: 'لم تعد الخدمة سليمة في الوقت المحدد.',
  r_APPROVAL_DENIED: 'عبارة المرور خاطئة، أو لم يعد هذا الاقتراح معلّقاً.', r_NO_AGENT_PROPOSAL: 'لا يوجد اقتراح حالي لهذه الخدمة.',
  r_ROLLOUT_COMPLETE_AND_HEALTHY: 'عادت سليمة', r_default: 'رفضته السياسة.',
  n_gateway: 'بوابة الذكاء الاصطناعي', t_gateway: 'LiteLLM', n_redactor: 'إخفاء البيانات', t_redactor: 'Google SDP', n_app: 'الواجهة', t_app: 'تطبيق المنصة',
  n_fault: 'حمل تجريبي', t_fault: 'fault-demo', n_financial: 'الوكيل المالي', t_financial: 'المستأجر رقم 1',  tour_o1_t: 'ماذا يفعل هذا الوكيل', tour_o1_b: 'يراقب الخدمات، ويشرح المشكلات، ويقترح إصلاحاً. لا يتصرف أبداً دون موافقتك.',
  tour_o2_t: 'حالة الخدمات', tour_o2_b: 'بطاقة لكل خدمة، بلون وأيقونة وكلمات. اختر بطاقة لفتح حادثتها.',
  tour_o3_t: 'الحادثة', tour_o3_b: 'ما حدث بكلمات بسيطة، والمراحل حتى الآن، وشرح اختياري من الذكاء الاصطناعي، والإجراء المقترح مع موافقتك.',
  tour_o4_t: 'الموافقات والرفض', tour_o4_b: 'الموافقات المعلّقة تنتظر هنا، وكل ما رفضته السياسة يظهر مع سببه.',
  tour_o5_t: 'الخط الزمني', tour_o5_b: 'كل تغيير مهم، الأحدث أولاً.', tour_o6_t: 'فحوص الأمن', tour_o6_b: 'تبويب الأمن يعرض ما تتحقق منه المنصة قبل تشغيل أي شيء.',
});

const node = id => document.getElementById(id);
const NAMES = {'platform.gateway': 'gateway', 'platform.redactor': 'redactor', 'apps.app': 'app', 'apps.fault-demo': 'fault',
               'agent-financial.agent': 'financial'};
const STATE = {HEALTHY: ['s_ok', 'ok', '✓', 'w_ok'], READINESS_FAILING: ['s_degraded', 'warn', '!', 'w_degraded'],
  CRASH_LOOP: ['s_crash', 'bad', '✕', 'w_crash'], OOM_KILLED: ['s_oom', 'bad', '✕', 'w_oom'], IMAGE_PULL: ['s_pull', 'bad', '✕', 'w_pull'],
  ADMISSION_DENIED: ['s_admission', 'bad', '✕', 'w_admission'], PENDING: ['s_pending', 'warn', '…', 'w_pending']};
const STAGES = ['observed', 'diagnosed', 'proposed', 'approved', 'executed', 'verified'];
let csrf = null, overview = null, selected = null, approval = null, busy = false, explanations = {}, outcome = null, security = null;

const fill = (s, v) => s.replace(/\{(\w+)\}/g, (_, k) => String(v[k]));
function serviceName(id) {
  const k = NAMES[id];
  return k ? t('n_' + k) + ' · ' + t('t_' + k) : id;
}
function serviceNode(id) {
  const k = NAMES[id];
  return k ? [el('span', {class: 'name'}, t('n_' + k)), ' · ', el('span', {class: 'tool'}, ltr(t('t_' + k)))] : [ltr(id)];
}
function state(b) {
  if (b.finding === 'HEALTHY' && b.desired === 0) return ['s_idle', 'info', '–', 'w_idle'];
  return STATE[b.finding] || ['s_degraded', 'warn', '!', 'w_degraded'];
}
const chip = (cls, icon, text) => el('span', {class: 'chip ' + cls}, el('span', {class: 'i', 'aria-hidden': 'true'}, icon), text);
const reason = code => { const base = String(code || '').split(':')[0]; return t('r_' + base) !== 'r_' + base ? t('r_' + base) : t('r_default'); };
const when = at => fmt.time(new Date(at * 1000));

async function call(operation, fields = {}) {
  const response = await fetch('/api/operations', {method: 'POST', credentials: 'same-origin',
    headers: {'Content-Type': 'application/json', 'X-Demo-CSRF': csrf}, body: JSON.stringify({operation, ...fields})});
  let value = {}; try { value = await response.json(); } catch (e) { value = {error: 'invalid_response'}; }
  return {ok: response.ok, value};
}
function setBusy(on) { busy = on; document.querySelectorAll('main button').forEach(b => { b.disabled = on; }); }

function renderBoard() {
  const board = node('board');
  board.replaceChildren(...(overview.board || []).map(b => {
    const [label, cls, icon] = state(b);
    const card = el('button', {type: 'button', class: 'svc', 'aria-pressed': String(b.target_id === selected)},
      el('span', {}, ...serviceNode(b.target_id)), chip(cls, icon, t(label)),
      el('span', {class: 'line'}, b.available + t('of') + b.desired + t('ready')),
      b.observe_only ? el('span', {class: 'line'}, t('watched')) : null);
    card.onclick = () => { selected = b.target_id; outcome = null; approval = null; render(); };
    return card;
  }));
}
function episode(id) {
  const events = (overview.timeline || []).filter(e => e.target === id);
  let start = 0;
  events.forEach((e, i) => { if (e.stage === 'diagnosed' && e.finding !== 'HEALTHY') start = i; });
  return events.slice(Math.max(0, start - 1));
}
function renderIncident() {
  const b = (overview.board || []).find(x => x.target_id === selected);
  node('incident').hidden = !b;
  if (!b) return;
  const [label, cls, icon, what] = state(b);
  node('inc-title').replaceChildren(...serviceNode(b.target_id));
  node('inc-chip').replaceChildren(chip(cls, icon, t(label)));
  node('inc-what').textContent = t(what);
  node('inc-evidence').replaceChildren(...(b.finding === 'HEALTHY' ? [] : b.evidence).map(e => el('li', {},
    ltr(e.name), ': ', t('e_' + e.reason), e.restarts ? ' · ' + fill(t('e_restarts'), {n: e.restarts}) : '')));
  const pending = (overview.pending || []).filter(p => p.target === b.target_id).slice(-1)[0];
  const ep = b.finding === 'HEALTHY' && !outcome ? [] : episode(b.target_id);
  const lastProposal = ep.map(e => e.stage).lastIndexOf('proposed');
  const done = new Set(ep.filter((e, i) => i <= lastProposal || lastProposal < 0 || !['denied', 'failed'].includes(e.stage)).map(e => e.stage).filter(x => STAGES.includes(x)));
  if (pending) ['approved', 'executed', 'verified'].forEach(x => done.delete(x));
  if (pending) done.add('proposed');
  if (approval) done.add('approved');
  const lastEv = ep[ep.length - 1];
  const stopped = !pending && !approval && lastEv && (lastEv.stage === 'denied' || lastEv.stage === 'failed');
  const next = STAGES.find(s => !done.has(s));
  node('tracker').hidden = !ep.length && !pending;
  node('tracker').replaceChildren(...STAGES.map(s => el('li', {class: done.has(s) ? 'done' : (s === next ? (stopped ? 'stop' : 'now') : '')},
    el('span', {'aria-hidden': 'true'}, done.has(s) ? '✓' : (s === next ? '●' : '○')),
    t(s === 'approved' && next === 'approved' && !stopped ? 'st_awaiting' : 'st_' + s))));
  const owner = b.owner_action && t('own_' + b.owner_action);
  node('owner-action').hidden = !owner || b.finding === 'HEALTHY';
  node('owner-text').textContent = owner || '';
  const ai = explanations[b.target_id];  // the Arabic text when the page is Arabic and the model gave one
  node('ai-box').hidden = ai === undefined;
  node('ai-text').textContent = ai ? ((UI.lang === 'ar' && ai.ar) || ai.en) : t('ai_none');
  node('explain').hidden = b.finding === 'HEALTHY' || b.observe_only;
  node('proposal').hidden = !pending && !approval;
  if (pending) {
    node('prop-action').textContent = t('a_' + pending.action);
    node('prop-target').replaceChildren(...serviceNode(pending.target));
    node('prop-expiry').textContent = pending.expires_at ? t('expires') + when(pending.expires_at) : '';
    node('proposal').dataset.request = pending.request_id;
  }
  node('approve').hidden = Boolean(approval);
  node('passphrase').closest('label').hidden = Boolean(approval);
  node('execute').hidden = !approval;
  node('outcome').hidden = !outcome;
  if (outcome) {
    node('outcome').className = 'notice ' + outcome.cls;
    node('outcome-icon').textContent = outcome.icon;
    node('outcome-text').textContent = outcome.text;
  }
}
function line(e) {
  const name = serviceName(e.target);
  if (e.stage === 'observed') return name + ': ' + t('ev_observed');
  if (e.stage === 'diagnosed') return name + ': ' + t('ev_diagnosed') + t(state({finding: e.finding, desired: 1})[0]);
  if (e.stage === 'proposed') return name + ': ' + t('ev_proposed') + t('a_' + e.action);
  if (e.stage === 'approved') return name + ': ' + t('ev_approved');
  if (e.stage === 'executed') return name + ': ' + t('ev_executed') + t('a_' + e.action);
  if (e.stage === 'verified') return name + ': ' + t('ev_verified');
  return name + ': ' + t('ev_' + e.stage) + reason(e.code);
}
function renderTimeline() {
  const rows = [], healthy = {}, open = {};  // open[target]: the finding of the episode in progress
  (overview.timeline || []).forEach(e => {
    const isHealthy = (e.stage === 'diagnosed' && e.finding === 'HEALTHY') || (e.stage === 'observed' && e.available >= e.desired);
    if (isHealthy) { open[e.target] = null; if (!healthy[e.target]) { healthy[e.target] = e; rows.push({e, healthy: true}); } return; }
    if (e.stage === 'denied' && e.code === 'SUPERSEDED') return;
    healthy[e.target] = null;
    // One episode = one sequence: a re-observation of the same problem (new evidence, same finding) adds no lines,
    // and a re-proposal of the same action in the episode replaces its line (latest time).
    if (e.stage === 'observed' && open[e.target]) return;
    if (e.stage === 'diagnosed') { if (open[e.target] === e.finding) return; open[e.target] = e.finding; }
    const same = rows.findIndex(r => r.e.stage === 'proposed' && r.e.target === e.target && r.e.action === e.action && r.episode === open[e.target]);
    if (e.stage === 'proposed' && same >= 0) { rows.splice(same, 1); }
    rows.push({e, episode: open[e.target]});
  });
  const shown = rows.slice(-25).reverse();
  node('timeline').replaceChildren(...shown.map(({e, healthy: h}) => el('li', {}, el('time', {}, when(e.at)),
    el('span', {}, h ? serviceName(e.target) + ': ' + t('healthy_since') + when(e.at) : line(e)))));
  node('timeline-empty').hidden = shown.length > 0;
  const pend = overview.pending || [];
  node('pending').replaceChildren(...pend.map(p => el('li', {}, el('time', {}, when(p.created_at)),
    el('span', {}, serviceName(p.target) + ': ' + t('a_' + p.action) + (p.expires_at ? ' · ' + t('expires') + when(p.expires_at) : '')))));
  node('pending-empty').hidden = pend.length > 0;
  const den = (overview.denials || []).filter(d => d.code !== 'SUPERSEDED').slice(-10).reverse();
  node('denials').replaceChildren(...den.map(d => el('li', {}, el('time', {}, when(d.at)),
    el('span', {}, (d.target ? serviceName(d.target) + ': ' : '') + reason(d.code)))));
  node('denials-empty').hidden = den.length > 0;
}
function render() {
  if (!overview) return;
  if (!selected || !(overview.board || []).some(b => b.target_id === selected)) {
    const first = (overview.board || []).find(b => b.finding !== 'HEALTHY' && !b.observe_only) || (overview.board || [])[0];
    selected = first && first.target_id;
  }
  node('checked').textContent = t('checked') + fmt.time(new Date()) + t('auto');
  renderBoard(); renderIncident(); renderTimeline();
  node('raw').textContent = JSON.stringify(overview, null, 2);
  renderSecurity();
}
async function refresh() {
  if (busy) return;
  const r = await call('overview');
  if (r.ok) { overview = r.value; node('status').textContent = ''; render(); } else node('status').textContent = reason(r.value.error);
}
const CHECKS = [['chk_netpol', 'NO_NETWORK_POLICY'], ['chk_root', 'RUNS_AS_ROOT', 'PRIVILEGED'], ['chk_rbac', 'UNEXPECTED_ROLE_BINDING'], ['chk_admission', 'IMAGE_REJECTED']];
const VERIFIED = ['chk_signed', 'chk_scan', 'chk_public', 'chk_egress', 'chk_spec', 'chk_redact'];
const CASES = {chk_signed: 'unsigned_image_rejected', chk_public: 'no_public_exposure', chk_egress: 'egress_containment', chk_spec: 'ops_stale_approval_refused', chk_redact: 'financial_redaction_down_no_model_call'};
function renderSecurity() {
  const items = CHECKS.map(([key, ...codes]) => {
    const bad = security ? (security.findings || []).filter(f => codes.includes(f.finding)) : null;
    const ok = bad !== null && bad.length === 0;
    return el('li', {}, security ? chip(ok ? 'ok' : 'bad', ok ? '✓' : '✕', t(ok ? 'pass' : 'fail')) : chip('', '…', t('live_check')),
      el('div', {}, el('strong', {}, t(key)), el('div', {class: 'how'}, t('live_check') + ' · ' + t(key + '_h'))));
  }).concat(VERIFIED.map(key => el('li', {}, chip('ok', '✓', t('pass')),
    el('div', {}, el('strong', {}, t(key)), el('div', {class: 'how'}, t('verified') + ' · ' + t(key + '_h'), CASES[key] ? [' ', ltr(CASES[key])] : null)))));
  node('checklist').replaceChildren(...items);
}
async function runSecurity() {
  setBusy(true);
  try {
    const r = await call('security');
    if (r.ok) { security = r.value; node('sec-when').textContent = t('sec_when') + fmt.time(new Date()); node('sec-raw').textContent = JSON.stringify(r.value, null, 2); }
    else node('status').textContent = reason(r.value.error);
    renderSecurity();
  } finally { setBusy(false); }
}
node('refresh').onclick = refresh;
node('sec-run').onclick = runSecurity;
node('explain').onclick = async () => {
  setBusy(true);
  try {
    const r = await call('explain', {target_id: selected});
    const items = r.ok ? (r.value.explanations || []).filter(x => x && x.untrusted_text) : [];
    const last = items[items.length - 1];
    explanations[selected] = last ? {en: last.untrusted_text, ar: last.untrusted_text_ar ? UI.latin(last.untrusted_text_ar) : null} : null;
    renderIncident();
  } finally { setBusy(false); }
};
node('approve').onclick = async () => {
  const request_id = node('proposal').dataset.request, secret = node('passphrase').value;
  node('passphrase').value = '';
  if (!request_id || !secret) return;
  setBusy(true);
  try {
    const r = await call('approve', {request_id, operator_secret: secret});
    if (r.ok) { approval = r.value; outcome = {cls: 'info', icon: '✓', text: t('approved')}; }
    else outcome = {cls: 'bad', icon: '✕', text: reason(r.value.error)};
    renderIncident();
  } finally { setBusy(false); }
};
node('execute').onclick = async () => {
  if (!approval) return;
  const saved = approval; approval = null;
  setBusy(true);
  try {
    const r = await call('execute', {request_id: saved.request_id, approval_id: saved.approval_id});
    const v = r.value || {};
    const b = (overview.board || []).find(x => x.target_id === selected) || {desired: 1};
    if (v.result === 'VERIFIED') outcome = {cls: 'ok', icon: '✓', text: fill(t('out_VERIFIED'), {a: b.desired, d: b.desired})};
    else if (v.result === 'NOT_VERIFIED') outcome = {cls: 'warn', icon: '!', text: t('out_NOT_VERIFIED')};
    else outcome = {cls: 'bad', icon: '✕', text: reason(v.code || v.error)};
  } finally { setBusy(false); }
  await refresh();
};
for (const [tab, panel] of [['tab-ops', 'panel-ops'], ['tab-sec', 'panel-sec']]) {
  node(tab).onclick = () => {
    for (const [other, otherPanel] of [['tab-ops', 'panel-ops'], ['tab-sec', 'panel-sec']]) {
      node(other).setAttribute('aria-selected', String(other === tab)); node(otherPanel).hidden = other !== tab;
    }
    if (tab === 'tab-sec' && !security) runSecurity();
  };
}
UI.onLang(() => { render(); renderSecurity(); });
UI.start([
  {sel: '#ops-intro', title: 'tour_o1_t', body: 'tour_o1_b'}, {sel: '#board-card', title: 'tour_o2_t', body: 'tour_o2_b'},
  {sel: '#incident', title: 'tour_o3_t', body: 'tour_o3_b'}, {sel: '#pending-card', title: 'tour_o4_t', body: 'tour_o4_b'},
  {sel: '#timeline-card', title: 'tour_o5_t', body: 'tour_o5_b'}, {sel: '#tab-sec', title: 'tour_o6_t', body: 'tour_o6_b'}]);
(async () => {
  const response = await fetch('/api/bootstrap', {credentials: 'same-origin'});
  csrf = (await response.json()).csrf;
  await refresh();
  if (UI_PARAMS().get('tab') === 'security') node('tab-sec').onclick();
  window.setInterval(() => { if (!document.hidden && !approval) refresh(); }, 20000);
})().catch(() => { node('status').textContent = t('r_default'); });
})();
