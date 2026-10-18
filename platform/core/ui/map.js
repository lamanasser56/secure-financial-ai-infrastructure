/* Map: the cluster drawing from /api/console/topology; agents, health and activity beside it. Every part opens the Explain drawer. */
(() => {
  'use strict';
  const {el, $, getJSON} = Console;
  const W = 948;
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

  // Drawn at the size of its panel on the 1440 x 900 frame (948 x 672), so 1 unit = 1 px there; more agents make it taller.
  function drawing(data) {
    const {agents, topology} = data;
    const nodes = Object.fromEntries(topology.nodes.map(n => [n.id, n]));
    const AX = 48, AW = 210, AH = 96, GAP = 64, TOP = 84;
    const cells = ['redactor', 'gateway', 'audit'].filter(id => nodes[id]);
    const PX = 356, PW = 230, HEAD = 44, CH = 92, PH = HEAD + CH * cells.length;
    const agentsH = agents.length * AH + Math.max(0, agents.length - 1) * GAP;
    const PY = TOP + Math.max(0, (agentsH - PH) / 2), A0 = TOP + Math.max(0, (PH - agentsH) / 2);
    const bottom = Math.max(PY + PH, A0 + agentsH) + 28;
    const IY = bottom + 64, H = Math.max(672, IY + 62);
    const busX = (AX + AW + PX) / 2, midY = PY + PH / 2;
    const ayTop = i => A0 + i * (AH + GAP);
    const out = [el('defs', {}, el('pattern', {id: 'hatch', width: 10, height: 10, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)'},
      el('line', {x1: 0, y1: 0, x2: 0, y2: 10, stroke: '#F2F7FF', 'stroke-opacity': 0.35, 'stroke-width': 2.5})))];
    out.push(el('rect', {x: 20, y: 52, width: 600, height: bottom - 52, fill: 'none', stroke: '#F2F7FF', 'stroke-opacity': 0.35, 'stroke-dasharray': '7 6'}));
    out.push(text(32, 40, 't-label', 'PRIVATE CLUSTER'));

    // allowed paths: agent -> bus -> platform (one line per agent, a dot travels along it)
    const openNetwork = (focus) => from => Console.explainTopic('network', from, focus);
    if (agents.length && cells.length) {
      out.push(el('line', {x1: busX, y1: Math.min(ayTop(0) + AH / 2, midY), x2: busX, y2: Math.max(ayTop(agents.length - 1) + AH / 2, midY), class: 'edge'}));
      out.push(el('line', {x1: busX, y1: midY, x2: PX, y2: midY, class: 'edge'}));
      agents.forEach((a, i) => {
        const y = ayTop(i) + AH / 2, d = `M${AX + AW},${y} L${busX},${y} L${busX},${midY} L${PX},${midY}`;
        out.push(part(Console.title(a) + ' network path', openNetwork([a.namespace]),
          el('path', {d: `M${AX + AW},${y} L${busX},${y}`, class: 'edge'}), el('circle', {cx: AX + AW, cy: y, r: 5, class: 'dot'}),
          moving(d), Console.reduced() ? el('circle', {cx: busX, cy: y, r: 5, class: 'dot'}) : null));
      });
      out.push(el('circle', {cx: PX, cy: midY, r: 5, class: 'dot'}));
    }
    // agents (the muted line names the runtime by its first word: "python", as in agent.yaml)
    agents.forEach((a, i) => {
      const y = ayTop(i);
      const what = a.kind === 'platform' ? 'acts with approval' : a.data === 'none' ? 'no data' : 'own rows only';
      out.push(part(Console.title(a), from => agentExplain(a, from),
        el('rect', {x: AX, y, width: AW, height: AH, class: 'shape'}), text(AX + 18, y + 42, 't-name', Console.title(a)),
        text(AX + 18, y + 70, 't-sub', ((a.runtime || '').split(' ')[0] || 'runtime unknown') + ' · ' + what)));
    });
    // denied: agent <-> agent (only pairs the topology says are denied)
    const denied = topology.denied || [];
    for (let i = 0; i + 1 < agents.length; i++) {
      const a = agents[i].node, b = agents[i + 1].node;
      if (!denied.some(d => (d.from === a && d.to === b) || (d.from === b && d.to === a))) continue;
      const y1 = ayTop(i) + AH, y2 = ayTop(i + 1), x = AX + AW / 2, my = (y1 + y2) / 2;
      out.push(part(Console.title(agents[i]) + ' to ' + Console.title(agents[i + 1]) + ': denied', openNetwork([agents[i].namespace, agents[i + 1].namespace]), el('line', {x1: x, y1, x2: x, y2, class: 'edge deny'}),
        el('rect', {x: x - 42, y: my - 14, width: 84, height: 28, class: 'tag deny'}), el('text', {x, y: my + 5, class: 't-tag', 'text-anchor': 'middle'}, '✕ why?'),
        el('text', {x: x + 60, y: my + 8, class: 'cross'}, '✕')));
    }
    // platform
    if (cells.length) {
      out.push(el('rect', {x: PX, y: PY, width: PW, height: PH, class: 'shape'}), el('rect', {x: PX, y: PY, width: PW, height: HEAD, fill: 'url(#hatch)', stroke: '#F2F7FF', 'stroke-opacity': 0.7}),
        text(PX + PW / 2, PY + 29, 't-head', 'PLATFORM', 'middle'));
      cells.forEach((id, i) => {
        const y = PY + HEAD + i * CH;
        out.push(part(CELLS[id][0], from => Console.explainTopic(id, from), el('rect', {x: PX, y, width: PW, height: CH, class: 'cell'}),
          text(PX + 18, y + 40, 't-item', CELLS[id][0]), text(PX + 18, y + 64, 't-sub', CELLS[id][1])));
      });
    }
    // platform -> Google (private link), only what the topology declares
    const EX = 700, EW = 220, EH = 84;
    const cellY = id => PY + HEAD + cells.indexOf(id) * CH + CH / 2;
    (topology.edges || []).filter(e => nodes[e.to] && nodes[e.to].kind === 'external' && EXTERNAL[e.to] && cells.includes(e.from)).forEach(e => {
      const y = cellY(e.from), by = y - EH / 2;
      out.push(part(EXTERNAL[e.to][0] + ' over a private link', from => Console.explainTopic('private-link', from),
        el('line', {x1: PX + PW, y1: y, x2: EX, y2: y, class: 'edge'}), el('circle', {cx: PX + PW, cy: y, r: 5, class: 'dot'}), el('circle', {cx: EX, cy: y, r: 5, class: 'dot'}),
        moving(`M${PX + PW},${y} L${EX},${y}`),
        el('rect', {x: EX, y: by, width: EW, height: EH, class: 'shape'}), text(EX + 18, by + 36, 't-item', EXTERNAL[e.to][0]), text(EX + 18, by + 60, 't-sub', EXTERNAL[e.to][1])));
    });
    if (cells.includes('gateway') && cells.includes('redactor') && (topology.edges || []).some(e => e.to === 'model-provider' || e.to === 'dlp')) {
      const ty = (cellY('redactor') + cellY('gateway')) / 2, tx = (PX + PW + EX) / 2;
      out.push(part('Private link', from => Console.explainTopic('private-link', from), el('rect', {x: tx - 46, y: ty - 14, width: 92, height: 28, class: 'tag'}),
        el('text', {x: tx, y: ty + 5, class: 't-tag', 'text-anchor': 'middle'}, 'private link')));
    }
    // internet: no route
    if (nodes.internet) {
      const open = from => Console.explainTopic('internet', from, agents.map(a => a.namespace)), noRoute = denied.some(d => d.to === 'internet');
      out.push(part('Internet: ' + (noRoute ? 'no way out' : 'see how it works'), open,
        el('path', {d: `M${busX},${bottom - 8} L${busX},${IY} L${EX},${IY}`, class: 'edge deny'}), el('rect', {x: EX, y: IY - EH / 2, width: EW, height: EH, class: 'shape dash'}),
        text(EX + 18, IY - 4, 't-item', 'Internet'), text(EX + 18, IY + 22, 't-deny', noRoute ? 'no way out · why?' : 'why?'),
        noRoute ? el('text', {x: busX + 14, y: IY - 10, class: 'cross'}, '✕') : null));
    }
    return el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'group', 'aria-label': 'Cluster drawing: agents, platform, Google services and the internet'}, out);
  }

  const kindChip = k => el('span', {class: 'chip ' + (k === 'blocked' ? 'denied' : 'allowed')}, k);

  // The numbers beside the headline, each only when real data gives it. "Protected" is an agent whose passport stamp reads VERIFIED
  // (checked live, nothing failing): shown only while live checks are available and every agent's checks came back. There is no
  // "blocked today": /activity is a short window of recent events, not a count for the day, so no such number exists to show.
  function stats(data) {
    if (!data || !data.topology) return null;
    const items = [[data.topology.nodes.filter(n => n.kind === 'agent').length, 'agents', 'Agents in the cluster drawing (/api/console/topology)']];
    const checks = data.agents.map(a => data.onboarding[a.name]);
    if (data.liveAvailable && checks.every(Boolean))
      items.push([checks.filter(o => o.counts.verified > 0 && !o.counts.failing).length, 'protected', 'Agents whose passport is VERIFIED: checked live just now, nothing failing']);
    return el('dl', {class: 'stats'}, items.map(([n, word, why]) => el('div', {title: why}, el('dt', {}, word), el('dd', {}, String(n)))));
  }
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
      el('section', {class: 'panel', 'aria-label': 'Live activity'}, el('div', {class: 'label'}, 'Live activity'), events),
      el('div', {class: 'btns'}, el('a', {class: 'btn inverse', href: '#/onboard'}, 'Onboard an agent'), el('a', {class: 'btn denied', href: '#/break'}, 'Try to break it')));
  }

  Console.screens.map = (view, arg, alive) => {
    const numbers = el('div', {});
    view.append(el('div', {class: 'head'}, el('div', {class: 'title-row'}, el('h1', {}, 'Every agent gets its own room.'), numbers),
      el('span', {class: 'hint'}, 'Click any part to see how it works.')));
    const body = el('div', {}, el('p', {class: 'muted'}, 'Loading…'));
    view.append(body);
    let last = '';
    Console.every(async () => {
      const [data, act] = await Promise.all([Console.loadAgents(), getJSON('/api/console/activity?limit=3')]);
      if (!alive()) return;
      const key = JSON.stringify([data, act.data]);
      if (key === last) return;  // nothing changed: keep focus and the running animation
      last = key;
      numbers.replaceChildren(...[stats(data)].filter(Boolean));
      if (!data || !data.topology) { body.replaceChildren(Console.empty('The console cannot reach its data.', 'Nothing is shown until the API answers.')); return; }
      body.replaceChildren(el('div', {class: 'map'}, el('div', {class: 'panel cluster'}, drawing(data)), side(data, act.ok ? act.data : null)));
    }, 10000);
  };
})();
