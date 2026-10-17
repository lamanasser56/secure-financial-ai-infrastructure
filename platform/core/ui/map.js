/* Map: the cluster drawing from /api/console/topology; agents, health and activity beside it. Every part opens the Explain drawer. */
(() => {
  'use strict';
  const {el, $, getJSON} = Console;
  const W = 760;
  const EXTERNAL = {'model-provider': ['Google AI', 'the model'], dlp: ['Google DLP', 'finds personal data']};
  const CELLS = {redactor: ['Redactor', 'hides personal data'], gateway: ['Model gateway', 'one key, one budget'], audit: ['Audit', 'every request recorded']};

  function agentExplain(agent, from) {
    Console.explain({eyebrow: agent.live ? 'EXPLAIN · VERIFIED LIVE' : 'EXPLAIN · NOT SEEN LIVE', live: !!agent.live, title: Console.title(agent), sub: agent.namespace,
      blocks: [{label: 'In plain words', text: agent.description},
               {label: 'How it works', text: 'Runs in its own namespace (' + agent.namespace + '). It reaches only: ' + (agent.reaches.length ? agent.reaches.join(', ') : 'nothing') + '.'},
               {label: 'Proof' + (agent.live ? ' · ' + agent.live.source : ''), node: Console.proofBox(agent.live)},
               {label: 'Without it', text: "One compromised agent could read another agent's data or borrow its key.", cls: 'without'}],
      file: agent.manifest_source}, from);
  }

  // A clickable part of the drawing: a real button (role, name, keyboard) wrapping its shapes.
  const part = (label, open, ...shapes) => el('g', {class: 'part', role: 'button', tabindex: '0', 'aria-label': label + ' — how it works',
    onclick: e => open(e.currentTarget), onkeydown: e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(e.currentTarget); } }}, ...shapes);
  const text = (x, y, cls, s, anchor) => el('text', {x, y, class: cls, 'text-anchor': anchor || 'start'}, s);
  // A dot travelling along an allowed path. With reduced motion there is no moving dot, only the fixed ones at the ends.
  const moving = d => Console.reduced() ? null : el('circle', {r: 4, class: 'dot'}, el('animateMotion', {dur: '3.2s', repeatCount: 'indefinite', path: d}));

  function drawing(data) {
    const {agents, topology} = data;
    const nodes = Object.fromEntries(topology.nodes.map(n => [n.id, n]));
    const AX = 30, AW = 190, AH = 64, GAP = 46, TOP = 70;
    const cells = ['redactor', 'gateway', 'audit'].filter(id => nodes[id]);
    const PX = 300, PW = 200, PY = TOP, HEAD = 30, CH = 62, PH = HEAD + CH * cells.length;
    const agentsH = agents.length * AH + (agents.length - 1) * GAP;
    const bottom = Math.max(PY + PH, TOP + agentsH) + 30;
    const IY = bottom + 50, H = IY + 40;
    const busX = 262, midY = PY + PH / 2;
    const ayTop = i => TOP + i * (AH + GAP);
    const out = [el('defs', {}, el('pattern', {id: 'hatch', width: 8, height: 8, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)'},
      el('line', {x1: 0, y1: 0, x2: 0, y2: 8, stroke: '#F2F7FF', 'stroke-opacity': 0.35, 'stroke-width': 2})))];
    out.push(el('rect', {x: 8, y: 30, width: 520, height: bottom - 30 + 20, fill: 'none', stroke: '#F2F7FF', 'stroke-opacity': 0.35, 'stroke-dasharray': '6 5'}));
    out.push(text(20, 24, 't-sub', 'PRIVATE CLUSTER'));

    // allowed paths: agent -> bus -> platform (one line per agent, a dot travels along it)
    const openNetwork = (focus) => from => Console.explainTopic('network', from, focus);
    if (agents.length && cells.length) {
      out.push(el('line', {x1: busX, y1: ayTop(0) + AH / 2, x2: busX, y2: Math.max(ayTop(agents.length - 1) + AH / 2, midY), class: 'edge'}));
      out.push(el('line', {x1: busX, y1: midY, x2: PX, y2: midY, class: 'edge'}));
      agents.forEach((a, i) => {
        const y = ayTop(i) + AH / 2, d = `M${AX + AW},${y} L${busX},${y} L${busX},${midY} L${PX},${midY}`;
        out.push(part(Console.title(a) + ' network path', openNetwork([a.namespace]),
          el('path', {d: `M${AX + AW},${y} L${busX},${y}`, class: 'edge'}), el('circle', {cx: AX + AW, cy: y, r: 4, class: 'dot'}),
          moving(d), Console.reduced() ? el('circle', {cx: busX, cy: y, r: 4, class: 'dot'}) : null));
      });
      out.push(el('circle', {cx: PX, cy: midY, r: 4, class: 'dot'}));
    }
    // agents
    agents.forEach((a, i) => {
      const y = ayTop(i);
      const what = a.kind === 'platform' ? 'acts with approval' : a.data === 'none' ? 'no data' : 'own rows only';
      out.push(part(Console.title(a), from => agentExplain(a, from),
        el('rect', {x: AX, y, width: AW, height: AH, class: 'shape'}), text(AX + 14, y + 28, 't-name', Console.title(a)),
        text(AX + 14, y + 48, 't-sub', (a.runtime || 'runtime unknown') + ' · ' + what)));
    });
    // denied: agent <-> agent (only pairs the topology says are denied)
    const denied = topology.denied || [];
    for (let i = 0; i + 1 < agents.length; i++) {
      const a = agents[i].node, b = agents[i + 1].node;
      if (!denied.some(d => (d.from === a && d.to === b) || (d.from === b && d.to === a))) continue;
      const y1 = ayTop(i) + AH, y2 = ayTop(i + 1), x = AX + AW / 2, my = (y1 + y2) / 2;
      out.push(part(Console.title(agents[i]) + ' to ' + Console.title(agents[i + 1]) + ': denied', openNetwork([agents[i].namespace, agents[i + 1].namespace]), el('line', {x1: x, y1, x2: x, y2, class: 'edge deny'}),
        el('rect', {x: x - 34, y: my - 11, width: 68, height: 22, class: 'tag deny'}), el('text', {x: x - 25, y: my + 4, class: 't-tag'}, '✕ why?'),
        el('text', {x: x + 44, y: my + 5, class: 'cross'}, '✕')));
    }
    // platform
    if (cells.length) {
      out.push(el('rect', {x: PX, y: PY, width: PW, height: PH, class: 'shape'}), el('rect', {x: PX, y: PY, width: PW, height: HEAD, fill: 'url(#hatch)', stroke: '#F2F7FF', 'stroke-opacity': 0.7}),
        text(PX + PW / 2 - 4, PY + 21, 't-name', 'PLATFORM', 'middle'));
      cells.forEach((id, i) => {
        const y = PY + HEAD + i * CH;
        out.push(part(CELLS[id][0], from => Console.explainTopic(id, from), el('rect', {x: PX, y, width: PW, height: CH, class: 'cell'}),
          text(PX + 14, y + 27, 't-name', CELLS[id][0]), text(PX + 14, y + 46, 't-sub', CELLS[id][1])));
      });
    }
    // platform -> Google (private link), only what the topology declares
    const EX = 604, EW = 146, EH = 58;
    const cellY = id => PY + HEAD + cells.indexOf(id) * CH + CH / 2;
    (topology.edges || []).filter(e => nodes[e.to] && nodes[e.to].kind === 'external' && EXTERNAL[e.to] && cells.includes(e.from)).forEach(e => {
      const y = cellY(e.from), by = y - EH / 2;
      out.push(part(EXTERNAL[e.to][0] + ' over a private link', from => Console.explainTopic('private-link', from),
        el('line', {x1: PX + PW, y1: y, x2: EX, y2: y, class: 'edge'}), el('circle', {cx: PX + PW, cy: y, r: 4, class: 'dot'}), el('circle', {cx: EX, cy: y, r: 4, class: 'dot'}),
        moving(`M${PX + PW},${y} L${EX},${y}`),
        el('rect', {x: EX, y: by, width: EW, height: EH, class: 'shape'}), text(EX + 14, by + 26, 't-name', EXTERNAL[e.to][0]), text(EX + 14, by + 45, 't-sub', EXTERNAL[e.to][1])));
    });
    if (cells.includes('gateway') && cells.includes('redactor') && (topology.edges || []).some(e => e.to === 'model-provider' || e.to === 'dlp')) {
      const ty = (cellY('redactor') + cellY('gateway')) / 2;
      out.push(part('Private link', from => Console.explainTopic('private-link', from), el('rect', {x: 506, y: ty - 11, width: 74, height: 22, class: 'tag'}),
        el('text', {x: 512, y: ty + 4, class: 't-tag'}, 'private link')));
    }
    // internet: no route
    if (nodes.internet) {
      const open = from => Console.explainTopic('internet', from, agents.map(a => a.namespace)), noRoute = denied.some(d => d.to === 'internet');
      out.push(part('Internet: ' + (noRoute ? 'no way out' : 'see how it works'), open,
        el('path', {d: `M${busX},${bottom - 6} L${busX},${IY} L${EX},${IY}`, class: 'edge deny'}), el('rect', {x: EX, y: IY - 29, width: EW, height: EH, class: 'shape dash'}),
        text(EX + 14, IY - 3, 't-name', 'Internet'), text(EX + 14, IY + 15, 't-deny', noRoute ? 'no way out · why?' : 'why?'),
        noRoute ? el('text', {x: busX + 10, y: IY - 8, class: 'cross'}, '✕') : null));
    }
    return el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'group', 'aria-label': 'Cluster drawing: agents, platform, Google services and the internet'}, out);
  }

  const kindChip = k => el('span', {class: 'chip ' + (k === 'blocked' ? 'denied' : 'allowed')}, k);
  // Plain words for the redactor's category codes (runtime/phase3/trusted_runtime.py SUPPORTED_ENTITIES). Unknown codes: "personal data".
  const CATEGORY = {EMAIL_ADDRESS: 'an email address', PHONE_NUMBER: 'a phone number', CREDIT_CARD: 'a card number', IBAN_CODE: 'a bank account number (IBAN)',
                    SAUDI_BANK_ACCOUNT: 'a bank account number', SAUDI_NATIONAL_ID: 'a national ID number', SAUDI_RESIDENT_ID: 'a residence ID number',
                    SAUDI_VAT_ID: 'a VAT number'};
  const plainCategories = codes => {
    const said = [...new Set((codes || []).map(c => CATEGORY[c] || 'personal data'))];
    return said.length ? said.length > 1 ? said.slice(0, -1).join(', ') + ' and ' + said[said.length - 1] : said[0] : 'personal data';
  };
  Console.plainCategories = plainCategories;
  function eventText(e) {
    if (e.kind === 'masked') return 'Hid ' + plainCategories(e.categories) + (e.caller ? ' · ' + e.caller : '');
    if (e.kind === 'approved') return 'Approved' + (e.action ? ' ' + e.action : '') + (e.target ? ' · ' + e.target : '');
    return (e.code || e.reason || 'refused').toLowerCase().replace(/_/g, ' ') + (e.target ? ' · ' + e.target : e.caller ? ' · ' + e.caller : '');
  }

  function side(data, activity) {
    const rows = data.agents.map(a => {
      const link = el('a', {href: '#/agents/' + encodeURIComponent(a.name), class: 'who'}, el('b', {}, Console.title(a)),
        el('span', {}, Console.countsText((data.onboarding[a.name] || {}).counts)));
      return el('div', {class: 'row'}, link, Console.healthChip(a.health));
    });
    const events = activity && activity.events.length ? activity.events.map(e => el('div', {class: 'ev'}, kindChip(e.kind), el('span', {}, eventText(e)), el('time', {}, Console.ago(e.at))))
      : [el('p', {class: 'muted'}, activity && Object.values(activity.sources).includes('unavailable') && !activity.events.length ?
        'No activity yet. Some activity sources are not reachable.' : 'No activity yet.')];
    return el('div', {class: 'side'},
      el('section', {class: 'panel', 'aria-label': 'Agents'}, el('div', {class: 'label'}, 'Agents'), rows.length ? rows : el('p', {class: 'muted'}, 'No agents onboarded.')),
      el('section', {class: 'panel', 'aria-label': 'Latest activity'}, el('div', {class: 'label'}, 'Latest activity'), events),
      el('div', {class: 'btns'}, el('a', {class: 'btn inverse', href: '#/agents'}, 'Passports →'), el('a', {class: 'btn denied', href: '#/break'}, 'Break it →')));
  }

  Console.screens.map = (view, arg, alive) => {
    view.append(Console.head('Every agent gets its own room.', null, el('span', {class: 'hint'}, 'Click any part to see how it works.')));
    const body = el('div', {}, el('p', {class: 'muted'}, 'Loading…'));
    view.append(body);
    let last = '';
    Console.every(async () => {
      const [data, act] = await Promise.all([Console.loadAgents(), getJSON('/api/console/activity?limit=3')]);
      if (!alive()) return;
      const key = JSON.stringify([data, act.data]);
      if (key === last) return;  // nothing changed: keep focus and the running animation
      last = key;
      if (!data || !data.topology) { body.replaceChildren(Console.empty('The console cannot reach its data.', 'Nothing is shown until the API answers.')); return; }
      body.replaceChildren(el('div', {class: 'map'}, el('div', {class: 'panel cluster'}, drawing(data)), side(data, act.ok ? act.data : null)));
    }, 10000);
  };
})();
