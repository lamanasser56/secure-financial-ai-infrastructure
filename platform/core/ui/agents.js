/* Agents: passports. The passport data page, the stamp and the ALLOWED / RESTRICTED lists are built from /api/console/{agents,onboarding,topology}. */
(() => {
  'use strict';
  const {el, $} = Console;
  const WHY_NOT_LIVE = {
    namespace: 'No live scan of this agent was seen by the ops agent, so only the manifest says it has its own namespace.',
    network: 'The live NetworkPolicy list of this namespace was not readable right now, so only the rendered policy says default-deny is in place.',
    model_key: 'The model key lives only in the gateway and the console never reads keys, so it is known from the manifest alone.',
    budget: 'Spend is held by the gateway. Reading it needs the gateway admin key, which the console never gets.',
    redaction: "No recent redactor event for this agent's own key was seen, so only the manifest says its text is redacted.",
    tools: "Tools are declared in the manifest. The platform cannot look inside the agent's code at runtime.",
    image: 'No ready pod was seen, so the signature cannot be inferred from a running pod.',
    ops: 'No recent scan of this agent was seen by the ops agent.',
    rows: 'Row-level security lives in the database. The console has no read-only way to check it live.'
  };
  const STATE = {verified: ['VERIFIED LIVE', 'allowed', '✓'], declared: ['DECLARED · NOT CHECKED LIVE', 'declared', '✓'], failing: ['FAILING', 'denied', '!']};

  function explainGuarantee(g, from) {
    const [eyebrow] = STATE[g.state];
    const blocks = [{label: 'In plain words', text: g.title + ': ' + g.detail + '.'},
                    {label: 'How it is known', text: g.state === 'declared' ? 'From the manifest only (' + g.source + ').'
                      : 'Seen through ' + g.source + (g.basis === 'inference' ? '. This is an inference, not a direct observation.' : '.')}];
    if (g.state === 'declared') blocks.push({label: 'Why it cannot be checked live', text: WHY_NOT_LIVE[g.id] || 'No live source exists for it.'});
    else blocks.push({label: 'Proof · ' + g.source, node: el('pre', {class: 'code'}, g.detail)});
    Console.explain({eyebrow: 'EXPLAIN · ' + eyebrow, live: g.state === 'verified', title: g.title, sub: g.id, blocks}, from);
  }
  Console.explainGuarantee = explainGuarantee;

  function explainStamp(agent, onb, from) {
    const c = onb.counts;
    const rows = onb.guarantees.map(g => el('div', {class: 'g'}, el('span', {class: 'ring ' + STATE[g.state][1]}, STATE[g.state][2]), el('div', {},
      el('b', {}, g.title), el('div', {class: 'muted'}, g.state === 'declared' ? 'Declared. ' + (WHY_NOT_LIVE[g.id] || '') : g.detail))));
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

  const emblem = size => el('svg', {viewBox: '0 0 60 60', width: size, height: size, 'aria-hidden': 'true'},
    el('path', {d: 'M30 6 L52 18 V42 L30 54 L8 42 V18 Z', fill: 'none', stroke: '#F2F7FF', 'stroke-width': 2.5}),
    el('path', {d: 'M30 18 L42 24 V36 L30 42 L18 36 V24 Z', fill: 'none', stroke: '#7CF0C0', 'stroke-width': 2}), el('circle', {cx: 30, cy: 30, r: 3.5, fill: '#F2F7FF'}));
  const cover = () => el('svg', {class: 'cover', viewBox: '0 0 44 58', 'aria-hidden': 'true'}, el('rect', {x: 1, y: 1, width: 42, height: 56, rx: 4, fill: '#14406E', stroke: '#F2F7FF', 'stroke-opacity': 0.7}),
    el('path', {d: 'M22 12 L36 20 V34 L22 42 L8 34 V20 Z', fill: 'none', stroke: '#F2F7FF', 'stroke-width': 1.6}), el('circle', {cx: 22, cy: 27, r: 3, fill: '#7CF0C0'}), el('text', {x: 22, y: 50, 'text-anchor': 'middle', 'font-size': 6, 'font-family': 'Barlow Semi Condensed', fill: '#9DB6D6'}, 'PASSPORT'));

  function listItem(kind, label, g, fallbackId, from) {
    const state = g ? g.state : 'declared';
    const mark = state === 'failing' ? '!' : kind === 'ok' ? '✓' : '✕';
    const open = e => g ? explainGuarantee(g, e.currentTarget) : Console.explain({eyebrow: 'EXPLAIN · DECLARED · NOT CHECKED LIVE', title: label, blocks: [{label: 'Why it cannot be checked live', text: WHY_NOT_LIVE[fallbackId]}]}, e.currentTarget);
    return el('li', {class: state === 'declared' ? 'decl' : ''}, el('button', {type: 'button', onclick: open, 'aria-label': label + ' — ' + state}, el('span', {class: 'mark'}, mark), label,
      state === 'declared' ? el('span', {class: 'chip declared', 'aria-hidden': 'true'}, 'declared') : null));
  }

  function passport(agent, onb, topology, select) {
    const g = id => onb && onb.guarantees.find(x => x.id === id);
    const denied = (topology && topology.denied || []).filter(d => d.from === 'agent-' + agent.name);
    const digest = agent.live && agent.live.image_digests[0];
    const failing = onb ? onb.guarantees.filter(x => x.state === 'failing') : [];
    const data = agent.data === 'none' ? 'none' : agent.data.database + ' · own rows';
    const field = (label, value) => el('div', {class: 'field'}, el('div', {class: 'label'}, label), el('b', {}, value));
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
    if (denied.some(d => d.to === 'internet')) restricted.push(listItem('no', 'No internet access', g('network'), 'network'));
    if (denied.some(d => d.to.startsWith('agent-'))) restricted.push(listItem('no', 'Cannot reach other agents', g('network'), 'network'));
    if (g('redaction')) restricted.push(listItem('no', 'Personal data hidden from the model', g('redaction'), 'redaction'));
    if (agent.data !== 'none' && agent.data.user_entry === 'own-rows') restricted.push(listItem('no', "Sees only the signed-in user's rows", null, 'rows'));
    const card = el('article', {class: 'passport', 'aria-label': 'Passport of ' + Console.display(agent.name)},
      el('div', {class: 'band'}, el('span', {}, 'AGENT PLATFORM'), el('span', {}, 'AGENT PASSPORT · P<PLT<01')),
      stamp,
      el('div', {class: 'page'}, el('div', {}, el('div', {class: 'emblem'}, emblem(84)), el('div', {class: 'digest'},
          Console.shortDigest(digest) || 'no running image seen', agent.live && agent.live.image_digests.length > 1 ? ' +' + (agent.live.image_digests.length - 1) : '')),
        el('div', {}, el('div', {class: 'label'}, 'Name'), el('h2', {class: 'name'}, Console.display(agent.name), Console.healthChip(agent.health)),
          el('div', {class: 'fields'}, field('Namespace', agent.namespace), field('Team', agent.team), field('Runtime', agent.runtime || '—'),
            field('Model', agent.model || '—'), field('Budget', '$' + agent.budget_usd_month.toFixed(2) + ' / month'), field('Data', data)))),
      el('div', {class: 'mrz', 'aria-hidden': 'true'}, el('div', {}, m1), el('div', {}, m2)));
    const lists = el('div', {class: 'lists'},
      el('div', {class: 'ok'}, el('h3', {}, 'ALLOWED'), el('ul', {}, agent.tools.length ? agent.tools.map(t => listItem('ok', t.description, g('tools'), 'tools')) : el('li', {class: 'muted'}, 'No tools.'))),
      el('div', {class: 'no'}, el('h3', {}, 'RESTRICTED'), el('ul', {}, restricted.length ? restricted : el('li', {class: 'muted'}, 'No restrictions are shown without live or rendered data.'))));
    const note = failing.length ? el('div', {class: 'failnote', role: 'alert'}, 'Failing: ' + failing.map(x => x.title + ' — ' + x.detail).join('; ')) : null;
    const cta = el('div', {class: 'cta'}, el('button', {type: 'button', class: 'btn', onclick: e => onb && explainStamp(agent, onb, e.currentTarget), disabled: !onb}, 'See the evidence'),
      el('a', {class: 'btn allowed', href: 'http://127.0.0.1:' + agent.port + '/', target: '_blank', rel: 'noopener'}, 'Try this agent →'),
      el('span', {class: 'hint'}, 'Needs: make agent-forward A=' + agent.name));
    return el('div', {}, card, note, lists, cta);
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
          onclick: () => { selected = a.name; history.replaceState(null, '', '#/agents/' + encodeURIComponent(a.name)); show(true); }}, cover(),
          el('span', {}, el('b', {}, Console.display(a.name)), el('span', {class: 'mono'}, a.namespace)))));
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
