'use strict';
const byId = (id) => document.getElementById(id);
let agent = 'infrastructure';
let csrf = null;
const tabs = [byId('tab-infrastructure'), byId('tab-financial')];
function selectTab(index, focus = false) {
  agent = index === 0 ? 'infrastructure' : 'financial';
  tabs.forEach((tab, i) => {
    tab.setAttribute('aria-selected', String(i === index));
    tab.tabIndex = i === index ? 0 : -1;
    byId(tab.getAttribute('aria-controls')).hidden = i !== index;
  });
  if (focus) tabs[index].focus();
  byId('result').hidden = true;
}
tabs.forEach((tab, index) => {
  tab.addEventListener('click', () => selectTab(index));
  tab.addEventListener('keydown', (event) => {
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      selectTab(event.key === 'Home' ? 0 : event.key === 'End' ? 1 : 1 - index, true);
    }
  });
});
async function bootstrap() {
  try {
    const response = await fetch('/api/bootstrap', {cache: 'no-store', credentials: 'omit'});
    const data = await response.json();
    if (!response.ok || data.mode !== 'offline_simulation' || data.synthetic_only !== true || typeof data.csrf !== 'string') throw new Error('blocked');
    csrf = data.csrf;
    byId('run').disabled = false;
    byId('status').textContent = 'جاهز للمحاكاة الاصطناعية · Ready for offline synthetic simulation';
  } catch (_) {
    byId('status').textContent = 'تعذر التحقق من حدود العرض · Private demo boundary unavailable';
  }
}
byId('run').addEventListener('click', async () => {
  byId('run').disabled = true;
  byId('result').hidden = true;
  byId('status').textContent = 'جارٍ التحقق والتشغيل · Validating and running…';
  try {
    const response = await fetch('/api/run', {
      method: 'POST', cache: 'no-store', credentials: 'omit',
      headers: {'Content-Type': 'application/json', 'X-Demo-CSRF': csrf},
      body: JSON.stringify({agent, language: byId('language').value,
        period: agent === 'financial' ? byId('period').value || null : null,
        scenario_id: agent === 'infrastructure' ? byId('scenario').value : null})
    });
    const data = await response.json();
    if (!response.ok) throw new Error('blocked');
    byId('badge').textContent = data.status;
    byId('answer').replaceChildren();
    const labels = {
      summary: 'الملخص · Summary', period: 'فترة التقرير · Reporting period',
      evidence_ids: 'معرّفات الأدلة · Evidence IDs', limitations: 'حدود النتيجة · Limitations',
      observed_failure: 'الفشل الملحوظ · Observed failure', suspected_cause: 'السبب المحتمل · Suspected cause',
      proposed_repair: 'الإصلاح المقترح · Proposed repair', status: 'حالة الطلب · Request status'
    };
    const entries = data.answer ? Object.entries(data.answer).filter(([key]) => !['kind', 'agent'].includes(key)) : [['status', data.question || data.reason || data.status]];
    for (const [label, value] of entries) {
      const item = document.createElement('p');
      const title = document.createElement('strong');
      title.textContent = (labels[label] || label) + ': ';
      item.append(title, document.createTextNode(Array.isArray(value) ? value.join(', ') : String(value)));
      byId('answer').append(item);
    }
    byId('facts').textContent = JSON.stringify(data.facts || [], null, 2);
    byId('audit').textContent = JSON.stringify({mode: data.mode, authentication: data.authentication,
      tenant_ref: data.tenant_ref, model_requests: data.model_requests, tool_executions: data.tool_executions,
      audit: data.audit}, null, 2);
    byId('result').hidden = false;
    byId('status').textContent = data.status === 'completed' ? 'اكتملت المحاكاة · Simulation completed' : data.status === 'clarification_required' ? 'يرجى تحديد الفترة أو السيناريو · Clarification required' : 'أوقف أحد ضوابط الأمان الطلب · Required security control blocked this run';
  } catch (_) {
    byId('status').textContent = 'تعذر إكمال الطلب. لم تتم إعادة المحاولة · Request failed; no retry was made';
  } finally {
    byId('run').disabled = csrf === null;
  }
});
bootstrap();
