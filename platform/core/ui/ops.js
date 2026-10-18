/* Ops (minimal): the incident timeline and owner approvals, over the existing /api/operations protocol (session cookie + CSRF token). */
(() => {
  'use strict';
  const {el, $} = Console;
  let csrf = null;
  // The outcome of the last approval in this page, kept here so the 6 s refresh (which redraws the panel and drops the
  // finished proposal) cannot erase it. Shown in the approvals panel until the next approval replaces it.
  let lastResult = null;

  async function call(request) {
    if (csrf === null) {
      const boot = await fetch('/api/bootstrap', {credentials: 'same-origin'});
      if (!boot.ok) return {ok: false, error: 'bootstrap_' + boot.status};
      csrf = (await boot.json()).csrf;
    }
    try {
      const response = await fetch('/api/operations', {method: 'POST', credentials: 'same-origin', body: JSON.stringify(request),
        headers: {'Content-Type': 'application/json', 'X-Demo-CSRF': csrf}});
      const data = await response.json();
      if (response.status === 403 && data.error === 'csrf_rejected') csrf = null;
      return response.ok ? {ok: true, data} : {ok: false, error: data.error || 'status_' + response.status};
    } catch (e) {
      return {ok: false, error: 'unreachable'};
    }
  }
  const words = s => String(s || '').toLowerCase().replace(/_/g, ' ');
  const stageChip = stage => el('span', {class: 'chip ' + ({denied: 'denied', failed: 'denied', verified: 'allowed', executed: 'allowed', approved: 'allowed'}[stage] || 'muted')}, stage);

  function pending(p, refresh) {
    const input = el('input', {type: 'password', id: 'pass-' + p.request_id, autocomplete: 'off', maxlength: 128});
    const msg = el('div', {class: 'msg', role: 'status'});
    const approve = el('button', {type: 'button', class: 'btn allowed', onclick: async () => {
      approve.disabled = true; msg.textContent = 'Checking…';
      const a = await call({operation: 'approve', request_id: p.request_id, operator_secret: input.value});
      input.value = '';
      const keep = text => { msg.textContent = text; lastResult = {text, target: p.target, action: p.action, at: Date.now() / 1000}; };
      if (!a.ok) { keep('Refused: ' + words(a.error)); approve.disabled = false; return; }
      const x = await call({operation: 'execute', request_id: p.request_id, approval_id: a.data.approval_id});
      keep(x.ok ? 'Result: ' + words(x.data.result) + (x.data.code ? ' · ' + words(x.data.code) : '') : 'Refused: ' + words(x.error));
      setTimeout(refresh, 800);
    }}, 'Approve');
    return el('div', {class: 'pend'}, el('div', {}, el('b', {}, words(p.action) + ' · ' + p.target), el('div', {class: 'muted'}, 'Finding: ' + words(p.finding))),
      el('div', {}, el('label', {for: input.id}, 'Owner passphrase'), input), approve, msg,
      el('div', {class: 'hint'}, 'Valid once, for this action on this service, for 5 minutes.'));
  }

  // Status board, from live data only: every agent (the ops agent's own row is this live answer), then the platform services.
  const SERVICES = {'platform.gateway': 'Model gateway', 'platform.redactor': 'Redactor', 'apps.app': 'Front door (console)', 'apps.fault-demo': 'Fault demo'};
  function statusBoard(board, agents) {
    const row = (name, id, detail, chip) => el('div', {class: 'row'}, el('div', {class: 'who'}, el('b', {}, name), el('span', {}, id + ' · ' + detail)), chip);
    const finding = b => el('span', {class: 'chip ' + (b.finding === 'HEALTHY' ? 'allowed' : 'denied')}, words(b.finding));
    const ready = b => b.available + ' of ' + b.desired + ' ready' + (b.observe_only ? ' · watched read-only' : '');
    const byTarget = Object.fromEntries(board.map(b => [b.target_id, b]));
    const used = new Set();
    const rows = agents.map(a => {
      if (a.kind === 'platform') return row(Console.title(a), a.namespace + '/' + a.name, 'answered just now', el('span', {class: 'chip allowed'}, 'running'));
      const b = byTarget[a.node + '.agent'];
      if (!b) return row(Console.title(a), a.namespace, 'not in the ops agent\'s scan', el('span', {class: 'chip muted'}, 'not seen'));
      used.add(b.target_id);
      return row(Console.title(a), a.namespace, ready(b), finding(b));
    });
    board.filter(b => !used.has(b.target_id)).forEach(b => rows.push(row(SERVICES[b.target_id] || b.target_id, b.target_id, ready(b), finding(b))));
    return rows.length ? rows : el('p', {class: 'muted'}, 'Nothing reported yet.');
  }

  Console.screens.ops = (view, arg, alive) => {
    view.append(Console.head('Security & Operations', 'What the ops agent saw, and what waits for the owner.'));
    const body = el('div', {}, el('p', {class: 'muted'}, 'Loading…'));
    view.append(body);
    let last = '';
    const refresh = async () => {
      const [r, agents] = await Promise.all([call({operation: 'overview'}), Console.getJSON('/api/console/agents')]);
      if (!alive()) return;
      Console.setLive(r.ok);
      if (!r.ok) { body.replaceChildren(Console.empty('The ops agent cannot be reached.', 'Reason: ' + words(r.error))); last = ''; return; }
      const key = JSON.stringify([r.data, agents.data, lastResult]);
      if (key === last) return;
      if (body.contains(document.activeElement) && document.activeElement.tagName === 'INPUT') return;  // do not wipe a passphrase being typed
      last = key;
      const d = r.data;
      // The "Explain" step: the ops agent's own explanation of an open incident (model text, redacted, display only), placed right
      // after the incident's latest diagnosis. It can never change the action. Without one, the step says so.
      const incidents = Object.fromEntries((d.board || []).filter(b => b.finding !== 'HEALTHY').map(b => [b.target_id, b]));
      const explainRow = b => el('li', {class: 'explain'}, el('span', {class: 'chip muted'}, 'Explain'), el('div', {},
        b.explanation ? [el('p', {}, b.explanation), el('p', {class: 'hint'}, 'AI explanation — for information only; it cannot change the action.')]
          : el('p', {class: 'muted'}, 'No explanation yet.')));
      const shown = new Set(), timeline = [];
      (d.timeline || []).slice(-20).reverse().forEach(e => {
        if (e.stage === 'diagnosed' && incidents[e.target] && !shown.has(e.target)) { shown.add(e.target); timeline.push(explainRow(incidents[e.target])); }
        timeline.push(el('li', {}, el('time', {}, Console.ago(e.at)),
          el('span', {}, e.target + (e.code ? ' · ' + words(e.code) : e.finding ? ' · ' + words(e.finding) : e.action ? ' · ' + words(e.action) : '')), stageChip(e.stage)));
      });
      Object.values(incidents).filter(b => !shown.has(b.target_id)).forEach(b => timeline.unshift(explainRow(b)));
      const board = statusBoard(d.board || [], agents.ok ? agents.data.agents : []);
      body.replaceChildren(el('div', {class: 'ops'},
        el('section', {class: 'panel', 'aria-label': 'Incident timeline'}, el('div', {class: 'label'}, 'Incident timeline'),
          timeline.length ? el('ul', {class: 'tl'}, timeline) : el('p', {class: 'muted'}, 'No events yet.'), el('div', {class: 'label'}, 'Status board'), board),
        el('section', {class: 'panel', 'aria-label': 'Approvals'}, el('div', {class: 'label'}, 'Needs approval'),
          (d.pending || []).length ? d.pending.map(p => pending(p, refresh)) : el('p', {class: 'muted'}, 'No pending approvals.'),
          lastResult ? el('div', {class: 'last-result'}, el('div', {class: 'label'}, 'Last approval'),
            el('div', {class: 'msg', role: 'status'}, lastResult.text),
            el('div', {class: 'hint'}, words(lastResult.action) + ' · ' + lastResult.target + ' · ' + Console.ago(lastResult.at))) : null,
          el('div', {class: 'label'}, 'Policy denials'), el('p', {class: 'muted'}, (d.denials || []).length ? (d.denials.length + ' recorded. Latest: ' + words(d.denials[d.denials.length - 1].code)) : 'None recorded.'))));
    };
    Console.every(refresh, 6000);
  };
})();
