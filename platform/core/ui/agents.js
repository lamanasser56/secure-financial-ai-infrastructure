/* Agents: passports. The passport data page, the stamp and the ALLOWED / RESTRICTED lists are built from /api/console/{agents,onboarding,topology}. */
(() => {
  'use strict';
  const {el} = Console;
  // Why a declared item has no live check. Keyed by guarantee id; the platform tenant (the ops agent) has its own reasons where they differ.
  const WHY_NOT_LIVE = {
    namespace: 'No live scan of this agent was seen by the ops agent, so only the manifest says it has its own namespace.',
    network: 'The live NetworkPolicy list of this namespace was not readable right now, so only the rendered policy says default-deny is in place.',
    model_key: 'The model key lives only in the gateway and the console never reads keys, so it is known from the manifest alone.',
    budget: 'Spend is held by the gateway. Reading it needs the gateway admin key, which the console never gets.',
    redaction: "No recent redactor event for this agent's own key was seen, so only the manifest says its text is redacted.",
    tools: "Tools are declared in the manifest. The platform cannot look inside the agent's code at runtime.",
    image: 'No ready pod was seen, so the signature cannot be inferred from a running pod.',
    ops: 'No recent scan of this agent was seen by the ops agent.',
    approval: 'An approval is one-use and is checked by the admission policy at the moment of a change. There is no standing state to read live.',
    rows: 'Row-level security lives in the database. The console has no read-only way to check it live.'
  };
  const WHY_PLATFORM = {
    namespace: 'The ops agent did not answer, so only its manifest says it runs in the ops namespace.',
    network: 'The ops agent does not list its own namespace, so only the rendered policy says default-deny is in place.',
    image: 'The ops agent watches other workloads, not its own pod, so no running digest is read for it.'
  };
  const why = (agent, id) => (agent && agent.kind === 'platform' && WHY_PLATFORM[id]) || WHY_NOT_LIVE[id] || 'No live source exists for it.';
  const STATE = {verified: ['VERIFIED LIVE', 'allowed', '✓'], declared: ['DECLARED · NOT CHECKED LIVE', 'declared', '✓'], failing: ['FAILING', 'denied', '!']};

  function explainGuarantee(g, from, agent) {
    const [eyebrow] = STATE[g.state];
    const blocks = [{label: 'In plain words', text: g.title + ': ' + g.detail + '.'},
                    {label: 'How it is known', text: g.state === 'declared' ? 'From the manifest only (' + g.source + ').'
                      : 'Seen through ' + g.source + (g.basis === 'inference' ? '. This is an inference, not a direct observation.' : '.')}];
    if (g.state === 'declared') blocks.push({label: 'Why it cannot be checked live', text: why(agent, g.id)});
    else blocks.push({label: 'Proof · ' + g.source, node: el('pre', {class: 'code'}, g.detail)});
    Console.explain({eyebrow: 'EXPLAIN · ' + eyebrow, live: g.state === 'verified', title: g.title, sub: g.id, blocks}, from);
  }
  Console.explainGuarantee = explainGuarantee;

  function explainStamp(agent, onb, from) {
    const c = onb.counts;
    const rows = onb.guarantees.map(g => el('div', {class: 'g'}, el('span', {class: 'ring ' + STATE[g.state][1]}, STATE[g.state][2]), el('div', {},
      el('b', {}, g.title), el('div', {class: 'muted'}, g.state === 'declared' ? 'Declared. ' + why(agent, g.id) : g.detail))));
    Console.explain({eyebrow: 'EXPLAIN · ' + (c.failing ? 'FAILING' : c.verified ? 'VERIFIED LIVE' : 'DECLARED · NOT CHECKED LIVE'), live: c.verified > 0 && !c.failing,
      title: 'Passport check', sub: agent.namespace,
      blocks: [{label: 'In plain words', text: c.verified + ' of ' + onb.total + ' guarantees were seen live just now. ' + c.declared + ' come from the manifest only.' +
                (c.failing ? ' ' + c.failing + ' failed a live check.' : '')},
               {label: 'How it works', text: "Live checks read the ops agent's snapshot and network policy list, and the redactor's audit lines. Declared items have no live source."},
               {label: 'Proof', node: el('div', {}, rows)},
               {label: 'Without it', text: 'A manifest alone is only a promise. The live checks show what is actually running.', cls: 'without'}], file: agent.manifest_source}, from);
  }

  const fill = (s, n) => (s + '<'.repeat(n)).slice(0, n);
  const up = s => s.toUpperCase().replace(/[^A-Z0-9]+/g, '<');
  // The two machine lines are built only from this agent's real values (name, namespace, running digest, budget, counts, health).
  function mrz(agent, onb) {
    const digest = agent.live && agent.live.image_digests[0], c = onb && onb.counts;
    const hex = digest ? digest.slice(7, 15).toUpperCase() : '<<<<<<<<';
    const budget = 'B' + String(Math.round(agent.budget_usd_month * 100)).padStart(4, '0');
    const counts = c ? 'V' + c.verified + 'D' + c.declared + 'F' + c.failing : 'V<D<F<';
    return [fill('P<PLT<' + up(agent.name), 44), fill(up(agent.namespace.replace('agent-', '')).slice(0, 8) + '<' + hex + '<' + budget + '<' + counts + '<' + (agent.health ? up(agent.health.state) : 'UNKNOWN'), 44)];
  }

  // The passport photo: a simple line icon chosen from what the manifest says the agent is (never from its name): the platform
  // tenant guards the platform (shield), an agent over the finance database handles money (bank), an agent whose tool searches
  // the documentation answers from docs (book); anything else gets the platform emblem.
  const ICONS = {
    shield: [['M30 7 L50 15 V30 C50 42 41 50 30 54 C19 50 10 42 10 30 V15 Z', '#F2F7FF'], ['M21 31 L28 38 L40 23', '#7CF0C0']],
    bank: [['M8 22 L30 9 L52 22 Z', '#F2F7FF'], ['M14 27 V44 M24 27 V44 M36 27 V44 M46 27 V44', '#7CF0C0'], ['M9 48 H51 M7 53 H53', '#F2F7FF']],
    book: [['M30 17 C24 12 16 12 8 14 V48 C16 46 24 46 30 51 C36 46 44 46 52 48 V14 C44 12 36 12 30 17 Z', '#F2F7FF'], ['M30 17 V51', '#7CF0C0'],
           ['M14 22 H24 M14 29 H24 M36 22 H46 M36 29 H46', '#7CF0C0']],
    emblem: [['M30 6 L52 18 V42 L30 54 L8 42 V18 Z', '#F2F7FF'], ['M30 18 L42 24 V36 L30 42 L18 36 V24 Z', '#7CF0C0']]
  };
  const iconOf = agent => agent.kind === 'platform' ? 'shield' : agent.data !== 'none' && agent.data.database === 'finance' ? 'bank'
    : (agent.tools || []).some(t => /docs/.test(t.id)) ? 'book' : 'emblem';
  const icon = (agent, attrs) => el('svg', {viewBox: '0 0 60 60', 'aria-hidden': 'true', ...attrs},
    ICONS[iconOf(agent)].map(([d, stroke]) => el('path', {d, fill: 'none', stroke, 'stroke-width': 2.5, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'})));
  const emblem = (agent, size) => icon(agent, {width: size, height: size});
  const cover = agent => el('svg', {class: 'cover', viewBox: '0 0 44 58', 'aria-hidden': 'true'}, el('rect', {x: 1, y: 1, width: 42, height: 56, rx: 4, fill: '#14406E', stroke: '#F2F7FF', 'stroke-opacity': 0.7}),
    el('g', {transform: 'translate(8 10) scale(0.47)'}, ICONS[iconOf(agent)].map(([d, stroke]) => el('path', {d, fill: 'none', stroke, 'stroke-width': 3.4, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}))),
    el('text', {x: 22, y: 50, 'text-anchor': 'middle', 'font-size': 6, 'font-family': 'Barlow Semi Condensed', fill: '#9DB6D6'}, 'PASSPORT'));

  // One list row: plain text; a small LIVE tag only when its guarantee was verified in the cluster now; FAILING when a live check contradicts it.
  function listItem(kind, label, g, fallbackId, agent) {
    const state = g ? g.state : 'declared';
    const open = e => g ? explainGuarantee(g, e.currentTarget, agent) : Console.explain({eyebrow: 'EXPLAIN · DECLARED · NOT CHECKED LIVE', title: label,
      blocks: [{label: 'Why it cannot be checked live', text: why(agent, fallbackId)}]}, e.currentTarget);
    return el('li', {}, el('button', {type: 'button', onclick: open, 'aria-label': label + ' — ' + state},
      el('span', {class: 'mark', 'aria-hidden': 'true'}, kind === 'ok' ? '✓' : '✕'), label,
      state === 'verified' ? el('span', {class: 'tag-live'}, 'LIVE') : state === 'failing' ? el('span', {class: 'tag-fail'}, 'FAILING') : null));
  }

  function passport(agent, onb, topology) {
    const g = id => onb && onb.guarantees.find(x => x.id === id);
    const tenants = new Set((topology && topology.nodes || []).filter(n => n.kind === 'agent').map(n => n.id));
    const denied = (topology && topology.denied || []).filter(d => d.from === agent.node);
    const digest = agent.live && agent.live.image_digests[0];
    const failing = onb ? onb.guarantees.filter(x => x.state === 'failing') : [];
    const data = agent.data === 'none' ? 'none' : agent.data.database + ' · own rows';
    const field = (label, value) => el('div', {class: 'field'}, el('div', {class: 'label'}, label), el('b', {title: value}, value));
    let stamp = null;
    if (onb) {
      const c = onb.counts, kind = c.failing ? 'failing' : c.verified ? '' : 'declared';
      stamp = el('button', {type: 'button', class: 'stamp ' + kind + (Console.reduced() ? '' : ' land'), 'aria-label': 'Passport check, open the evidence',
        onclick: e => explainStamp(agent, onb, e.currentTarget)},
        c.failing ? 'FAILING' : c.verified ? 'VERIFIED' : 'DECLARED',
        el('small', {}, c.failing ? failing.map(x => x.title).join(' · ') : c.verified + ' live · ' + c.declared + ' declared'));
    }
    const [m1, m2] = mrz(agent, onb);
    const restricted = [];
    if (denied.some(d => d.to === 'internet')) restricted.push(listItem('no', 'No internet access', g('network'), 'network', agent));
    if (denied.some(d => tenants.has(d.to))) restricted.push(listItem('no', 'Cannot reach other agents', g('network'), 'network', agent));
    if (g('redaction')) restricted.push(listItem('no', 'Personal data hidden from the model', g('redaction'), 'redaction', agent));
    if (g('approval')) restricted.push(listItem('no', 'Changes nothing without the owner\'s approval', g('approval'), 'approval', agent));
    if (agent.data !== 'none' && agent.data.user_entry === 'own-rows') restricted.push(listItem('no', "Sees only the signed-in user's rows", null, 'rows', agent));
    const card = el('article', {class: 'passport', 'aria-label': 'Passport of ' + Console.title(agent)},
      el('div', {class: 'band'}, el('span', {}, 'AGENT PLATFORM'), el('span', {}, 'AGENT PASSPORT · P<PLT<01')),
      el('div', {class: 'page'}, el('div', {}, el('div', {class: 'emblem'}, emblem(agent, 96)), el('div', {class: 'digest'},
          Console.shortDigest(digest) || (agent.kind === 'platform' ? 'own pod not observed' : 'no running image seen'),
          agent.live && agent.live.image_digests.length > 1 ? ' +' + (agent.live.image_digests.length - 1) : '')),
        el('div', {}, el('div', {class: 'label'}, 'Name'), el('h2', {class: 'name'}, Console.title(agent), Console.healthChip(agent.health)),
          el('div', {class: 'fields'}, field('Namespace', agent.namespace), field('Team', agent.team), field('Runtime', agent.runtime || '—'),
            field('Model', agent.model || '—'), field('Budget', '$' + agent.budget_usd_month.toFixed(2) + ' / month'), field('Data', data)))),
      el('div', {class: 'mrz', 'aria-hidden': 'true'}, el('div', {}, m1), el('div', {}, m2)),
      stamp);
    const lists = el('div', {class: 'lists'},
      el('div', {class: 'ok'}, el('h3', {}, 'ALLOWED'), el('ul', {}, agent.tools.length ? agent.tools.map(t => listItem('ok', t.description, t.access === 'approval' ? g('approval') : g('tools'), 'tools', agent))
        : el('li', {class: 'muted'}, 'No tools.'))),
      el('div', {class: 'no'}, el('h3', {}, 'RESTRICTED'), el('ul', {}, restricted.length ? restricted : el('li', {class: 'muted'}, 'No restrictions are shown without live or rendered data.'))));
    const legend = el('p', {class: 'legend'}, el('span', {class: 'tag-live'}, 'LIVE'), '= checked in the cluster now; others are declared in the manifest');
    const note = failing.length ? el('div', {class: 'failnote', role: 'alert'}, 'Failing: ' + failing.map(x => x.title + ' — ' + x.detail).join('; ')) : null;
    const cta = el('div', {class: 'cta'}, el('button', {type: 'button', class: 'btn', onclick: e => onb && explainStamp(agent, onb, e.currentTarget), disabled: !onb}, 'See the evidence'),
      agent.kind === 'platform' ? el('a', {class: 'btn allowed', href: '#/ops'}, 'Open Ops →') : [
        el('a', {class: 'btn allowed', href: 'http://127.0.0.1:' + agent.port + '/', target: '_blank', rel: 'noopener'}, 'Try this agent →'),
        el('span', {class: 'hint'}, 'Needs: make agent-forward A=' + agent.name)]);
    return el('div', {}, card, note, lists, legend, cta);
  }

  Console.screens.agents = (view, arg, alive) => {
    view.append(Console.head('Agent passports', 'Every agent gets an identity, a set of permissions, and proof.', el('a', {class: 'btn inverse', href: '#/onboard'}, 'Issue a passport →')));
    const body = el('div', {}, el('p', {class: 'muted'}, 'Loading…'));
    view.append(body);
    let selected = arg, last = '';
    Console.every(async () => {
      const data = await Console.loadAgents();
      if (!alive()) return;
      const key = JSON.stringify(data) + selected;
      if (key === last) return;
      last = key;
      if (!data) { body.replaceChildren(Console.empty('The console cannot reach its data.', 'No passports are shown until the API answers.')); return; }
      if (!data.agents.length) { body.replaceChildren(Console.empty('No agents onboarded yet.', 'Add platform/agents/<name>/agent.yaml and run make onboard.')); return; }
      if (!data.agents.some(a => a.name === selected)) selected = data.agents[0].name;
      const show = (flip) => {
        const agent = data.agents.find(a => a.name === selected);
        const rail = el('nav', {class: 'rail', 'aria-label': 'Agents'}, data.agents.map(a => el('button', {type: 'button', 'aria-current': a.name === selected ? 'true' : 'false',
          onclick: () => { selected = a.name; history.replaceState(null, '', '#/agents/' + encodeURIComponent(a.name)); show(true); }}, cover(a),
          el('span', {}, el('b', {}, Console.title(a)), el('span', {class: 'mono'}, a.namespace)))));
        const page = passport(agent, data.onboarding[agent.name], data.topology);
        body.replaceChildren(el('div', {class: 'passports'}, rail, page));
        // The flip is a one-shot animation with no fill: when it ends the element has no transform at all (nothing left to blur the text).
        if (flip && !Console.reduced()) page.animate([{transform: 'perspective(1100px) rotateY(-75deg)', opacity: 0}, {transform: 'perspective(1100px) rotateY(0deg)', opacity: 1}],
          {duration: 380, easing: 'ease-out'});
      };
      show(false);
    }, 10000);
  };
})();
