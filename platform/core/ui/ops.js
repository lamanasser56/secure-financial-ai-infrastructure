/* Ops: read-only observations, explicit scan coverage and the owner's approve-and-execute action. */
(() => {
  'use strict';
  const {el} = Console;
  let csrf = null, booting = null, lastResult = null;
  const actions = new Map(); // UI duplicate suppression; the executor remains the authorization authority.
  const words = value => String(value || '').toLowerCase().replace(/_/g, ' ');
  const now = () => Date.now() / 1000;
  const timestamp = value => Number.isFinite(value) && value > 0 && value <= now() + 5;
  const fresh = (value, maxAge) => timestamp(value) && Number.isFinite(maxAge) && maxAge > 0 && now() - value <= maxAge;
  const errorCode = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,80}$/.test(value) ? value : 'invalid_response';
  async function json(path, options = {}, timeout = 20000) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), timeout);
    let response;
    try {
      response = await fetch(path, {credentials: 'same-origin', ...options, signal: controller.signal});
      Console.captureSource(response);
      let data;
      try {
        data = await response.json();
        if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('invalid response');
      } catch (error) { Console.observeAPI(response.status, false); throw error; }
      Console.observeAPI(response.status);
      return {response, data};
    } catch (error) { if (!response) Console.observeAPI(0); throw error; }
    finally { clearTimeout(timer); }
  }
  async function bootstrap() {
    if (csrf !== null) return;
    if (!booting) booting = (async () => {
      const {response, data} = await json('/api/bootstrap', {}, 10000);
      if (!response.ok || typeof data.csrf !== 'string' || !data.csrf || data.csrf.length > 512) throw new Error('bootstrap unavailable');
      csrf = data.csrf;
    })().finally(() => { booting = null; });
    await booting;
  }
  async function call(request) {
    try {
      await bootstrap();
      const {response, data} = await json('/api/operations', {method: 'POST', body: JSON.stringify(request),
        headers: {'Content-Type': 'application/json', 'X-Demo-CSRF': csrf}}, request.operation === 'execute' ? 210000 : 20000);
      if (response.status === 403 && data.error === 'csrf_rejected') csrf = null;
      return response.ok ? {ok: true, data} : {ok: false, error: errorCode(data.error || 'status_' + response.status)};
    } catch { return {ok: false, error: 'unavailable'}; }
  }
  const stageChip = stage => el('span', {class: 'chip ' + ({denied: 'denied', failed: 'denied', verified: 'allowed', executed: 'allowed', approved: 'allowed'}[stage] || 'muted')}, stage);

  function pending(p, report, refresh) {
    const input = el('input', {type: 'password', id: 'pass-' + p.request_id, autocomplete: 'off', maxlength: 128, required: true});
    const msg = el('div', {class: 'msg', role: 'status'});
    const prior = actions.get(p.request_id);
    if (prior) msg.textContent = prior.text;
    const expired = () => !timestamp(p.created_at) || !Number.isFinite(p.expires_at) || now() >= p.expires_at;
    const approve = el('button', {type: 'submit', class: 'btn allowed', disabled: expired() || (prior && prior.locked)}, 'Approve & execute');
    const keep = (text, locked = true, busy = false) => {
      const outcome = {text, locked, busy, request_id: p.request_id, target: p.target, action: p.action, at: now()};
      actions.set(p.request_id, outcome);
      if (actions.size > 100) for (const [id, value] of actions) if (!value.busy) { actions.delete(id); break; }
      lastResult = outcome; msg.textContent = text; report(outcome);
      approve.disabled = locked || expired();
    };
    const form = el('form', {class: 'pend', onsubmit: async event => {
      event.preventDefault();
      if ((actions.get(p.request_id) || {}).locked) return;
      if (expired()) { keep('Proposal expired or its time is unavailable. Refresh observations.'); return; }
      const secret = input.value;
      input.value = '';
      keep('Approving…', true, true);
      const approved = await call({operation: 'approve', request_id: p.request_id, operator_secret: secret});
      if (!approved.ok) { keep('Approval unavailable or refused: ' + words(approved.error) + '. No execution was requested.', false); return; }
      if (approved.data.request_id !== p.request_id || typeof approved.data.approval_id !== 'string' || !/^[A-Za-z0-9._-]{1,128}$/.test(approved.data.approval_id)) {
        keep('Invalid approval response. No execution was requested.'); return;
      }
      keep('Approved. Executing this action once…', true, true);
      const executed = await call({operation: 'execute', request_id: p.request_id, approval_id: approved.data.approval_id});
      if (!executed.ok) keep('Execution outcome unavailable or refused: ' + words(executed.error) + '. Check the incident timeline; do not assume the change failed.');
      else if (executed.data.result === 'VERIFIED') keep('Verified: ' + words(executed.data.code || 'verified') + '.');
      else if (executed.data.result === 'NOT_VERIFIED') keep('Not verified: ' + words(executed.data.code || 'verification_unavailable') + '.');
      else keep('Execution outcome unavailable: unrecognized response. Check the incident timeline.');
      refresh();
    }}, el('div', {}, el('b', {}, words(p.action) + ' · ' + p.target),
      el('div', {class: 'muted'}, 'Finding: ' + words(p.finding)),
      el('div', {class: 'hint', 'data-proposal-time': ''}, timestamp(p.created_at) ? 'Proposed ' + Console.ago(p.created_at) : 'Proposal time unavailable')),
      el('div', {}, el('label', {for: input.id}, 'Owner passphrase'), input), approve, msg,
      el('div', {class: 'hint'}, expired() ? 'Expired or unavailable proposal time.' : 'Approving immediately requests this change from the separate executor. Bound to this action, target and evidence; one use.'));
    return form;
  }

  const SERVICES = {'platform.gateway': 'Model gateway · provider', 'platform.gateway-boundary': 'Model gateway · boundary',
    'platform.redactor': 'Model gateway · redactor', 'apps.financial-frontdoor': 'Data broker', 'ops.ops-executor': 'Approval executor',
    'apps.app': 'Console', 'apps.fault-demo': 'Fault demo'};
  function statusBoard(board, agents, maxAge) {
    const observation = b => b ? {target: b.target_id, finding: b.finding, desired: b.desired, available: b.available,
      observed_at: b.observed_at, observe_only: b.observe_only} : null;
    const row = (name, id, detail, state, facts = {}, file = 'platform/core/kubernetes/ops/workloads.yaml') => el('tr', {},
      el('td', {}, el('button', {type: 'button', class: 'btn link', 'aria-label': name + ' — observations', onclick: event => Console.explain({
        eyebrow: 'EXPLAIN · WORKLOAD OBSERVATION', title: name, sub: id,
        blocks: [{label: 'Observation', text: detail + '. These are readiness facts, not a security or signature verdict.'},
                 {label: 'Source', text: 'ops-agent /v1/snapshot; expected workloads come from the selected release. Readiness needs recent observations of every expected worker.'},
                 {label: 'Returned facts', node: Console.proofBox(facts)}], file}, event.currentTarget)}, name)),
      el('td', {}, detail), el('td', {}, el('span', {class: 'chip ' + ({healthy: 'allowed', 'api answered': 'allowed', degraded: 'denied', failed: 'denied'}[state] || 'muted')}, state)));
    const byTarget = Object.fromEntries(board.map(b => [b.target_id, b])), used = new Set();
    const declared = (agents.find(a => a.kind === 'platform') || {}).watched_targets || [];
    for (const target of declared) if (!byTarget[target.target_id]) {
      byTarget[target.target_id] = {...target, observed_at: null, available: 0, desired: target.replicas};
    }
    const rows = agents.map(a => {
      if (a.kind === 'platform') return row(Console.title(a), a.namespace, 'Its API answered this refresh · it does not report on its own Pod', 'api answered',
        {api: 'answered (this screen read /v1/snapshot from it)', own_pod: 'not observed here: an observer does not vouch for itself',
         own_pod_checked_by: 'make demo-check (workload readiness and image digests)'}, a.manifest_source);
      if (!Array.isArray(a.workloads) || !a.workloads.length) return row(Console.title(a), a.namespace, 'workload inventory unavailable', 'unknown');
      a.workloads.forEach(w => used.add(w.target_id));
      const parts = a.workloads.map(w => ({expected: w, observed: byTarget[w.target_id]}));
      const current = parts.filter(p => p.observed && fresh(p.observed.observed_at, maxAge));
      const total = parts.reduce((n, p) => n + Math.max(p.expected.replicas, p.observed ? p.observed.desired : 0), 0);
      const ready = current.reduce((n, p) => n + p.observed.available, 0);
      const healthy = current.length === parts.length && current.every(p => p.observed.finding === 'HEALTHY' && p.observed.available >= Math.max(p.expected.replicas, p.observed.desired));
      return row(Console.title(a), a.namespace, current.length + ' / ' + parts.length + ' observed · ' + ready + ' / ' + total + ' ready',
        healthy ? 'healthy' : current.length ? 'degraded' : 'not observed',
        {expected: a.workloads, observations: parts.map(p => observation(p.observed)), max_age_seconds: maxAge}, a.manifest_source);
    });
    Object.values(byTarget).filter(b => !used.has(b.target_id)).forEach(b => {
      const declaredTarget = declared.find(target => target.target_id === b.target_id);
      const required = Math.max(b.desired, declaredTarget && Number.isFinite(declaredTarget.replicas) ? declaredTarget.replicas : 0);
      const current = fresh(b.observed_at, maxAge), healthy = current && b.finding === 'HEALTHY' && b.available >= required;
      const stopped = current && required === 0 && b.available === 0 && b.finding === 'HEALTHY';  // declared with 0 replicas
      rows.push(row(SERVICES[b.target_id] || b.target_id, b.target_id,
        stopped ? 'Stopped by design · the release declares 0 replicas (make fault starts it for the demo)'
          : current ? b.available + ' / ' + required + ' ready' + (b.observe_only ? ' · read-only observation' : '') : 'no recent timestamped scan',
        stopped ? 'stopped' : current ? healthy ? 'healthy' : 'failed' : 'not observed',
        {expected: declaredTarget || null, observation: observation(b), max_age_seconds: maxAge}));
    });
    return rows.length ? el('table', {class: 'x', 'aria-label': 'Observed workloads'},
      el('thead', {}, el('tr', {}, ['Workload', 'Observation', 'State'].map(label => el('th', {scope: 'col'}, label)))), el('tbody', {}, rows))
      : el('p', {class: 'muted'}, 'Nothing observed yet.');
  }

  const scanShape = data => data && Array.isArray(data.findings) && data.findings.every(f => f && typeof f.namespace === 'string' && typeof f.finding === 'string')
    && Array.isArray(data.namespaces) && data.namespaces.length && data.namespaces.every(ns => typeof ns === 'string') && Array.isArray(data.unreadable);

  function posture(response, previous) {
    const data = response.ok ? response.data : previous;
    const shaped = scanShape(data);
    const complete = shaped && data.source === 'ops-agent /v1/posture' && data.complete === true && !data.unreadable.length
      && data.network && data.namespaces.every(ns => Object.hasOwn(data.network, ns)) && !data.findings.some(f => f.finding === 'UNREADABLE');
    const current = response.ok && shaped && fresh(data.checked_at, data.max_age_seconds) && fresh(data.started_at, data.max_age_seconds) && data.started_at <= data.checked_at;
    const title = !response.ok ? 'Posture unavailable' : !current ? 'Scan stale or timestamp unavailable' : !complete ? 'Scan incomplete' : data.findings.length + (data.findings.length === 1 ? ' finding' : ' findings') + ' · completed scan';
    const info = shaped ? (timestamp(data.checked_at) ? 'Checked ' + new Date(data.checked_at * 1000).toISOString() : 'Check time unavailable')
      + ' · ' + data.namespaces.length + ' namespaces' : 'No valid scan result.';
    const detail = el('button', {type: 'button', class: 'btn link', disabled: !shaped, onclick: event => Console.explain({
      eyebrow: 'EXPLAIN · POSTURE SCAN', title: 'Security posture',
      blocks: [{label: 'Source', text: 'ops-agent /v1/posture · read-only Kubernetes API lists. ' + info},
               {label: 'Coverage', text: 'Checks default-deny policy presence, pod non-root flags, exact declared RBAC and image-rejection events in: ' + data.namespaces.join(', ') + '. These checks are not a full security assessment.'},
               {label: 'Availability', text: current && complete ? 'Completed current scan.' : 'No complete current verdict. Unreadable namespaces: ' + (data.unreadable.join(', ') || 'none reported') + '.'},
               {label: 'Returned facts', node: Console.proofBox(data)}], file: 'platform/core/src/agent_platform/ops/authority.json'}, event.currentTarget)}, 'Scan details →');
    const list = shaped && data.findings.length ? el('ul', {}, data.findings.map(f => el('li', {},
      f.namespace + ' · ' + f.finding + (f.binding ? ' · ' + f.binding : f.role ? ' · ' + f.role : f.pod ? ' · ' + f.pod : '')))) : null;
    return el('div', {}, el('h2', {}, title), el('p', {class: 'hint'}, 'Source: ops-agent /v1/posture'), el('p', {class: 'muted'}, info),
      !current || !complete ? el('p', {class: 'muted'}, 'No complete current verdict.') : null,
      !response.ok && shaped ? el('p', {class: 'hint'}, 'Last returned scan; no current result.') : null, list, detail);
  }

  Console.screens.ops = (view, arg, alive) => {
    // Only a click disables the button, until its refresh lands; background polls never touch it (it looked unusable every
    // 6 s). A click during a poll queues one more refresh.
    const refreshButton = el('button', {type: 'button', class: 'btn inverse', onclick: () => refresh(true)}, 'Refresh Ops');
    view.append(Console.head('Security & Operations', 'Observed workloads, scoped checks and owner actions.', refreshButton));
    const board = el('section', {class: 'panel', 'aria-label': 'Workload observations'}, 'Loading…');
    const scans = el('section', {class: 'panel', 'aria-label': 'Security posture'}, 'Loading scan…');
    const approvals = el('section', {class: 'panel', 'aria-label': 'Approvals'});
    const result = el('section', {class: 'panel', 'aria-label': 'Last action'});
    const timelineBox = el('section', {class: 'panel', 'aria-label': 'Incident timeline'});
    view.append(el('div', {class: 'ops'}, el('div', {}, board, timelineBox), el('div', {}, scans, approvals, result)));
    let busy = false, again = false, previousScan = null;
    const cards = new Map();
    function showResult() {
      if (!alive()) return;
      result.hidden = !lastResult;
      result.replaceChildren(...(lastResult ? [el('div', {class: 'label'}, 'Last action'), el('div', {class: 'msg', role: 'status'}, lastResult.text),
        el('div', {class: 'hint'}, words(lastResult.action) + ' · ' + lastResult.target + ' · ' + Console.ago(lastResult.at))] : []));
    }
    async function refresh(manual) {
      if (!alive()) return;
      if (busy) { again = again || manual === true; return; }
      busy = true;
      if (manual === true) { refreshButton.disabled = true; refreshButton.setAttribute('aria-busy', 'true'); }
      try {
        const [overview, security, agents] = await Promise.all([call({operation: 'overview'}), call({operation: 'security'}), Console.getJSON('/api/console/agents')]);
        if (!alive()) return;
        Console.setSourcesUnavailable(!overview.ok || !security.ok || !agents.ok || agents.data.live_available !== true);
        scans.replaceChildren(el('div', {class: 'label'}, 'Security posture'), posture(security, previousScan));
        if (security.ok && scanShape(security.data)) previousScan = security.data;
        if (!overview.ok || !['board', 'pending', 'timeline', 'denials'].every(key => Array.isArray(overview.data[key]))) {
          board.replaceChildren(Console.empty('Ops observations unavailable.', 'Refresh to retry. No healthy state is inferred.'));
          approvals.replaceChildren(el('div', {class: 'label'}, 'Needs approval'), el('p', {class: 'muted'}, 'Pending proposals unavailable.'));
          timelineBox.replaceChildren(el('p', {class: 'muted'}, 'Incident timeline unavailable.'));
          showResult(); return;
        }
        const d = overview.data;
        const knownAgents = agents.ok && Array.isArray(agents.data.agents);
        board.replaceChildren(el('div', {}, el('div', {class: 'label'}, 'Workload observations'),
          el('p', {class: 'hint'}, 'Source: ops-agent /v1/snapshot · recent observations'),
          knownAgents ? null : el('p', {class: 'muted'}, 'Agent inventory unavailable; showing individual returned workloads.'),
          statusBoard(d.board, knownAgents ? agents.data.agents : [], d.max_age_seconds)));
        const proposed = d.pending || [], current = new Set(proposed.map(p => p.request_id));
        for (const id of cards.keys()) if (!current.has(id)) cards.delete(id);
        const nodes = proposed.map(p => {
          const key = JSON.stringify([p.request_id, p.target, p.action, p.arguments, p.evidence_digest, p.created_at, p.expires_at]);
          if (!cards.has(p.request_id) || cards.get(p.request_id).key !== key) cards.set(p.request_id, {key, node: pending(p, showResult, refresh)});
          const node = cards.get(p.request_id).node;
          node.querySelector('button[type=submit]').disabled = (actions.get(p.request_id) || {}).locked || !timestamp(p.created_at) || !Number.isFinite(p.expires_at) || now() >= p.expires_at;
          node.querySelector('[data-proposal-time]').textContent = timestamp(p.created_at) ? 'Proposed ' + Console.ago(p.created_at) + (now() >= p.expires_at ? ' · expired' : '') : 'Proposal time unavailable';
          return node;
        });
        // Reusing proposal nodes preserves a typed passphrase while other observations keep refreshing.
        const heading = approvals.querySelector('.label') || el('div', {class: 'label'}, 'Needs approval');
        if (nodes.length) {
          for (const child of [...approvals.children]) if (child !== heading && !nodes.includes(child)) child.remove();
          if (!approvals.contains(heading)) approvals.prepend(heading);
          nodes.forEach(node => { if (!approvals.contains(node)) approvals.append(node); });
        } else approvals.replaceChildren(heading, el('p', {class: 'muted'}, 'No pending approvals.'));
        const events = (d.timeline || []).slice(-20).reverse();
        const incidents = d.board.filter(b => b.finding !== 'HEALTHY');
        const timeline = events.map(e => el('li', {}, el('time', {}, Console.ago(e.at)), el('span', {}, e.target + ' · ' + words(e.code || e.finding || e.action)), stageChip(e.stage)));
        const explanations = incidents.map(b => el('div', {}, el('b', {}, b.target_id + ' · Explain'),
          b.explanation ? el('p', {}, b.explanation + ' · AI text, display only; it cannot change the action.')
            : el('p', {class: 'muted'}, b.observe_only ? 'Read-only observation. Owner action: ' + words(b.owner_action || 'inspect_workload') + '.'
              : b.automated_fix ? 'Not needed: an automated fix is proposed.' : 'No explanation yet.')));
        timelineBox.replaceChildren(el('details', {}, el('summary', {}, 'Incident timeline · ' + events.length + ' events'),
          el('ul', {class: 'tl'}, timeline), explanations,
          el('p', {class: 'hint'}, 'Recent operation denials: ' + (d.denials || []).length + '. This count is separate from posture findings.')));
        showResult();
      } finally {
        busy = false;
        if (alive()) {
          refreshButton.disabled = false; refreshButton.removeAttribute('aria-busy');
          if (again) { again = false; refresh(true); }
        }
      }
    }
    const visible = () => { if (!document.hidden) refresh(); };
    document.addEventListener('visibilitychange', visible);
    Console.onExit(() => document.removeEventListener('visibilitychange', visible));
    showResult();
    Console.every(refresh, 6000);
  };
})();
