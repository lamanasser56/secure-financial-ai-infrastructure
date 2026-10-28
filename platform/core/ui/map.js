/* Map: a presentation of the current topology. Model-path grouping never changes that data. */
(() => {
  'use strict';
  const {el, $, getJSON} = Console;
  const W = 918;
  const EXTERNAL = {'model-provider': ['Google AI', 'the model'], dlp: ['Google DLP', 'checks identifiers']};
  const COMPONENT = {'gateway-boundary': 'Redaction gateway', redactor: 'Redactor', gateway: 'Model gateway'};
  const GROUPS = [
    {id: 'model-path', name: 'Model gateway', sub: 'identifiers masked first', members: ['gateway-boundary', 'redactor', 'gateway'], height: 180},
    {id: 'data-path', name: 'Data broker', sub: 'your rows only, read-only', members: ['financial-frontdoor'], height: 96},
    {id: 'change-path', name: 'Approval executor', sub: 'changes need your signature', members: ['ops-executor'], height: 96}
  ];
  const AUDIT = 'Audit · request events', AUDIT_HEIGHT = 28;

  function agentExplain(agent, from) {
    Console.explain({eyebrow: agent.live ? 'EXPLAIN · VERIFIED LIVE' : 'EXPLAIN · NOT SEEN LIVE', live: !!agent.live, title: Console.title(agent), sub: agent.namespace,
      blocks: [{label: 'In plain words', text: agent.description},
        {label: 'How it works', text: 'Runs in its own namespace (' + agent.namespace + '). It reaches only: ' + (agent.reaches.length ? agent.reaches.join(', ') : 'nothing') + '.'},
        {label: 'Proof' + (agent.live ? ' · ' + agent.live.source : ''), node: Console.proofBox(agent.live)},
        {label: 'Without it', text: "One compromised agent could read another agent's data or borrow its key.", cls: 'without'}],
      file: agent.manifest_source}, from);
  }
  const part = (label, open, ...shapes) => {
    const node = el('g', {class: 'part', role: 'button', tabindex: '0', 'aria-label': label + ' — how it works',
      onclick: event => open(event.currentTarget), onkeydown: event => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(event.currentTarget); }
      }}, ...shapes);
    // Reuse the original selection/focus treatment for clickable lines and tags too.
    node.querySelectorAll('.edge, .tag').forEach(shape => shape.classList.add('shape'));
    return node;
  };
  const text = (x, y, cls, value, anchor) => el('text', {x, y, class: cls, 'text-anchor': anchor || 'start'}, value);
  const moving = path => Console.reduced() ? null : el('circle', {r: 4, class: 'dot'}, el('animateMotion', {dur: '3.2s', repeatCount: 'indefinite', path}));
  const network = focus => from => Console.explainTopic('network', from, focus);
  const actorCaption = a => ((a.runtime || '').split(' ')[0] || 'runtime unknown') + ' · ' +
    (a.kind === 'platform' ? 'acts with approval' : a.data === 'none' ? 'no data' : 'own rows only');
  const hatch = () => el('defs', {}, el('pattern', {id: 'hatch', width: 10, height: 10, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)'},
    el('line', {x1: 0, y1: 0, x2: 0, y2: 10, stroke: '#F2F7FF', 'stroke-opacity': 0.35, 'stroke-width': 2.5})));

  function model(data) {
    const nodes = Object.fromEntries(data.topology.nodes.map(node => [node.id, node]));
    const groups = GROUPS.filter(group => group.members.some(id => nodes[id])).map(group => ({...group,
      sub: group.members.every(id => nodes[id]) ? group.sub : 'declaration incomplete'}));
    const members = new Set(groups.flatMap(group => group.members.filter(id => nodes[id])));
    const edges = data.topology.edges || [], denied = data.topology.denied || [];
    const reaches = actor => edges.some(edge => edge.from === actor.node && members.has(edge.to));
    const providers = [...new Map(edges.filter(edge => nodes[edge.from] && GROUPS[0].members.includes(edge.from)
      && nodes[edge.to] && nodes[edge.to].kind === 'external' && EXTERNAL[edge.to]).map(edge => [edge.to, edge])).values()]
      .sort((a, b) => (a.to === 'model-provider' ? -1 : 1) - (b.to === 'model-provider' ? -1 : 1));
    return {nodes, groups, denied, reaches, providers, agents: data.agents};
  }

  async function modelExplain(from, alive, nodes) {
    const topics = GROUPS[0].members;
    const replies = await Promise.all(topics.map(topic => nodes[topic]
      ? getJSON('/api/console/explain/' + topic) : Promise.resolve({ok: false})));
    if (!alive()) return;
    const blocks = [{label: 'Path', text: 'Redaction gateway → Redactor → Model gateway.'}], observations = [];
    let masking = null;
    topics.forEach((topic, index) => {
      const reply = replies[index];
      if (!reply.ok) { blocks.push({label: COMPONENT[topic], text: 'This part is unavailable in the current declaration or its explanation could not be read.'}); return; }
      const data = reply.data, code = Console.codeURL(data.file);
      blocks.push({label: COMPONENT[topic], node: el('div', {}, el('div', {class: 'mono muted'}, topic),
        el('p', {}, topic === 'gateway' ? data.title + '. ' + data.plain : data.plain),
        data.attack_proof ? Console.attackProof(data.attack_proof)
          : el('p', {class: 'muted'}, data.proof ? 'Observed state: ' + (data.proof.state || 'source answered') : 'Declared · nothing current proves it'))});
      if (topic === 'redactor') masking = data.how;
      observations.push(el('div', {}, el('div', {class: 'label'}, COMPONENT[topic]), Console.proofBox(data.proof),
        code ? el('a', {href: code, class: 'btn link', target: '_blank', rel: 'noopener'}, 'View component code →') : null));
    });
    if (masking) blocks.push({label: 'Supported masking patterns', text: masking});
    blocks.push({label: 'Observations', node: el('div', {}, observations)});
    Console.explain({eyebrow: 'EXPLAIN · MODEL PATH', title: 'Model gateway', blocks,
      file: 'platform/core/src/agent_platform/gateway_boundary.py'}, from);
  }

  function platformCell(group, x, y, width, height, openModel, nodes) {
    const open = group.id === 'model-path' ? from => openModel(from, nodes) : from => Console.explainTopic(group.members[0], from);
    const cell = part(group.name, open, el('rect', {x, y, width, height, class: 'shape cell'}),
      text(x + 18, y + height / 2 - 8, 't-item', group.name), text(x + 18, y + height / 2 + 17, 't-sub', group.sub));
    cell.setAttribute('data-platform-group', group.id);
    return cell;
  }
  function auditStrip(x, y, width) {
    const strip = part(AUDIT, from => Console.explainTopic('audit', from),
      el('rect', {x, y, width, height: AUDIT_HEIGHT, class: 'shape cell'}), text(x + 18, y + 18, 't-sub', AUDIT));
    strip.setAttribute('data-audit-strip', '');
    return strip;
  }

  function drawing(data, openModel, compact) {
    const view = model(data);
    if (compact) return verticalDrawing(view, openModel);
    const {agents, nodes, groups, denied, reaches, providers} = view;
    const AX = 32, AW = 210, AH = 96, GAP = 64, TOP = 72;
    const busX = AX + AW + 28, PX = busX + 28, PW = 230, HEAD = 44;
    const PH = HEAD + groups.reduce((sum, group) => sum + group.height, 0) + (nodes.audit ? AUDIT_HEIGHT : 0);
    const agentsH = agents.length * AH + Math.max(0, agents.length - 1) * GAP;
    const PY = TOP + Math.max(0, (agentsH - PH) / 2), A0 = TOP + Math.max(0, (PH - agentsH) / 2);
    const bottom = Math.max(PY + PH, A0 + agentsH) + 28, IY = bottom + 64, H = Math.max(672, IY + 62);
    const ayTop = index => A0 + index * (AH + GAP), entryY = PY + HEAD / 2;
    const out = [hatch(), el('rect', {x: 14, y: 52, width: PX + PW - 2, height: bottom - 52, fill: 'none',
      stroke: '#F2F7FF', 'stroke-opacity': 0.35, 'stroke-dasharray': '7 6'}), text(26, 40, 't-label', 'PRIVATE CLUSTER')];
    const allowed = agents.map((actor, index) => ({actor, index})).filter(({actor}) => reaches(actor));
    if (allowed.length && groups.length) {
      const ys = allowed.map(({index}) => ayTop(index) + AH / 2);
      out.push(part('Platform network paths', network(allowed.map(({actor}) => actor.namespace)),
        el('rect', {x: busX - 12, y: Math.min(entryY, ...ys) - 12, width: PX - busX + 24, height: Math.abs(Math.max(entryY, ...ys) - Math.min(entryY, ...ys)) + 24, class: 'hit'}),
        el('line', {x1: busX, y1: Math.min(entryY, ...ys), x2: busX, y2: Math.max(entryY, ...ys), class: 'edge'}),
        el('line', {x1: busX, y1: entryY, x2: PX, y2: entryY, class: 'edge'}), el('circle', {cx: PX, cy: entryY, r: 5, class: 'dot'})));
      allowed.forEach(({actor, index}) => {
        const y = ayTop(index) + AH / 2, path = `M${AX + AW},${y} L${busX},${y} L${busX},${entryY} L${PX},${entryY}`;
        out.push(part(Console.title(actor) + ' network path', network([actor.namespace]),
          el('path', {d: `M${AX + AW},${y} L${busX},${y}`, class: 'edge'}),
          el('circle', {cx: AX + AW, cy: y, r: 5, class: 'dot'}), moving(path),
          Console.reduced() ? el('circle', {cx: busX, cy: y, r: 5, class: 'dot'}) : null));
      });
    }
    agents.forEach((actor, index) => {
      const y = ayTop(index);
      out.push(part(Console.title(actor), from => agentExplain(actor, from), el('rect', {x: AX, y, width: AW, height: AH, class: 'shape'}),
        text(AX + 18, y + 42, 't-name', Console.title(actor)), text(AX + 18, y + 70, 't-sub', actorCaption(actor))));
    });
    for (let index = 0; index + 1 < agents.length; index++) {
      const first = agents[index], second = agents[index + 1];
      if (!denied.some(edge => (edge.from === first.node && edge.to === second.node) || (edge.from === second.node && edge.to === first.node))) continue;
      const y1 = ayTop(index) + AH, y2 = ayTop(index + 1), x = AX + AW / 2, y = (y1 + y2) / 2;
      out.push(part(Console.title(first) + ' to ' + Console.title(second) + ': denied', network([first.namespace, second.namespace]),
        el('line', {x1: x, y1, x2: x, y2, class: 'edge deny'}), el('rect', {x: x - 42, y: y - 14, width: 84, height: 28, class: 'tag deny'}),
        text(x, y + 5, 't-tag', '✕ why?', 'middle'), text(x + 60, y + 8, 'cross', '✕')));
    }
    const positions = new Map();
    if (groups.length) {
      out.push(el('rect', {x: PX, y: PY, width: PW, height: PH, class: 'shape'}),
        el('rect', {x: PX, y: PY, width: PW, height: HEAD, fill: 'url(#hatch)', stroke: '#F2F7FF', 'stroke-opacity': 0.7}),
        text(PX + PW / 2, PY + 29, 't-head', 'PLATFORM', 'middle'));
      let y = PY + HEAD;
      groups.forEach(group => { positions.set(group.id, y); out.push(platformCell(group, PX, y, PW, group.height, openModel, nodes)); y += group.height; });
      if (nodes.audit) out.push(auditStrip(PX, y, PW));
    }
    const EX = 694, EW = 208, EH = 84, modelY = positions.get('model-path');
    providers.forEach((edge, index) => {
      if (modelY === undefined) return;
      const y = modelY + 42 + index * 96;
      const connector = part(EXTERNAL[edge.to][0] + ' over a private link', from => Console.explainTopic('private-link', from),
        el('line', {x1: PX + PW, y1: y, x2: EX, y2: y, class: 'edge'}),
        el('circle', {cx: PX + PW, cy: y, r: 5, class: 'dot'}), el('circle', {cx: EX, cy: y, r: 5, class: 'dot'}),
        moving(`M${PX + PW},${y} L${EX},${y}`), el('rect', {x: EX, y: y - EH / 2, width: EW, height: EH, class: 'shape'}),
        text(EX + 18, y - 6, 't-item', EXTERNAL[edge.to][0]), text(EX + 18, y + 18, 't-sub', EXTERNAL[edge.to][1]));
      connector.setAttribute('data-connects-from', 'model-path');
      connector.setAttribute('data-connects-to', edge.to);
      out.push(connector);
    });
    if (providers.length && modelY !== undefined) {
      const x = (PX + PW + EX) / 2, y = modelY + (providers.length > 1 ? 90 : 96);
      out.push(part('Private link', from => Console.explainTopic('private-link', from),
        el('rect', {x: x - 70, y: y - 14, width: 140, height: 28, class: 'tag'}), text(x, y + 5, 't-tag', 'private link · why?', 'middle')));
    }
    if (nodes.internet) {
      const blocked = agents.filter(actor => denied.some(edge => edge.from === actor.node && edge.to === 'internet'));
      const all = agents.length > 0 && blocked.length === agents.length;
      out.push(part('Internet: ' + (all ? 'no way out' : 'policy details'), from => Console.explainTopic('internet', from, (blocked.length ? blocked : agents).map(actor => actor.namespace)),
        blocked.length ? el('path', {d: `M${busX},${agents.length ? ayTop(agents.length - 1) + AH / 2 : bottom - 8} L${busX},${IY} L${EX},${IY}`, class: 'hit-line'}) : null,
        blocked.length ? el('path', {d: `M${busX},${agents.length ? ayTop(agents.length - 1) + AH / 2 : bottom - 8} L${busX},${IY} L${EX},${IY}`, class: 'edge deny'}) : null,
        el('rect', {x: EX, y: IY - EH / 2, width: EW, height: EH, class: 'shape' + (blocked.length ? ' dash' : '')}),
        text(EX + 18, IY - 4, 't-item', 'Internet'), text(EX + 18, IY + 22, blocked.length ? 't-deny' : 't-sub', all ? 'no way out · why?' : 'policy details · why?'),
        blocked.length ? text(busX + 14, IY - 10, 'cross', '✕') : null));
    }
    return svg(out, W, H, 'Cluster drawing: agents, three platform groups, request events, Google services and the internet', 'diagram');
  }

  function svg(out, width, height, label, layout) {
    const node = el('svg', {viewBox: `0 0 ${width} ${height}`, role: 'group', 'aria-label': label, 'data-map-layout': layout}, out);
    node.style.maxHeight = height + 'px';
    return node;
  }

  function verticalDrawing(view, openModel) {
    const {agents, nodes, groups, denied, reaches, providers} = view;
    const width = 320, x = 16, box = 288, out = [hatch(), text(x, 28, 't-label', 'PRIVATE CLUSTER')];
    let y = 52;
    agents.forEach(actor => {
      out.push(part(Console.title(actor), from => agentExplain(actor, from), el('rect', {x, y, width: box, height: 84, class: 'shape'}),
        text(x + 18, y + 34, 't-name', Console.title(actor)), text(x + 18, y + 61, 't-sub', actorCaption(actor))));
      y += 92;
      if (reaches(actor)) {
        const path = `M${x + 12},${y + 14} L${x + 78},${y + 14}`;
        out.push(part(Console.title(actor) + ' network path', network([actor.namespace]),
          el('rect', {x, y, width: box, height: 28, class: 'shape'}), el('path', {d: path, class: 'edge'}),
          el('circle', {cx: x + 12, cy: y + 14, r: 4, class: 'dot'}), el('circle', {cx: x + 78, cy: y + 14, r: 4, class: 'dot'}),
          moving(path), text(x + 92, y + 19, 't-sub', 'Allowed platform paths')));
        y += 36;
      }
      if (denied.some(edge => edge.from === actor.node)) {
        out.push(part(Console.title(actor) + ': denied paths', network([actor.namespace]),
          el('rect', {x, y, width: box, height: 28, class: 'shape'}), el('line', {x1: x + 12, y1: y + 14, x2: x + 78, y2: y + 14, class: 'edge deny'}),
          text(x + 44, y + 20, 'cross', '✕'), text(x + 92, y + 19, 't-sub', 'Denied paths · why?')));
        y += 36;
      }
      y += 16;
    });
    out.push(el('rect', {x, y, width: box, height: 36, fill: 'url(#hatch)', stroke: '#F2F7FF', 'stroke-opacity': 0.7}),
      text(x + box / 2, y + 25, 't-head', 'PLATFORM', 'middle'));
    y += 36;
    groups.forEach(group => { out.push(platformCell(group, x, y, box, 96, openModel, nodes)); y += 96; });
    if (nodes.audit) { out.push(auditStrip(x, y, box)); y += AUDIT_HEIGHT; }
    out.splice(1, 0, el('rect', {x: 4, y: 40, width: width - 8, height: y - 28, fill: 'none', stroke: '#F2F7FF', 'stroke-opacity': 0.35, 'stroke-dasharray': '7 6'}));
    y += 48;
    providers.forEach(edge => {
      out.push(part(EXTERNAL[edge.to][0] + ' over a private link', from => Console.explainTopic('private-link', from),
        el('rect', {x, y, width: box, height: 84, class: 'shape'}), text(x + 18, y + 32, 't-item', EXTERNAL[edge.to][0]),
        text(x + 18, y + 58, 't-sub', 'Model gateway → private link')));
      y += 100;
    });
    if (nodes.internet) {
      const blocked = agents.filter(actor => denied.some(edge => edge.from === actor.node && edge.to === 'internet'));
      const all = agents.length > 0 && blocked.length === agents.length;
      out.push(part('Internet: ' + (all ? 'no way out' : 'policy details'), from => Console.explainTopic('internet', from, (blocked.length ? blocked : agents).map(actor => actor.namespace)),
        el('rect', {x, y, width: box, height: 84, class: 'shape' + (blocked.length ? ' dash' : '')}),
        text(x + 18, y + 32, 't-item', 'Internet'), text(x + 18, y + 58, blocked.length ? 't-deny' : 't-sub', all ? 'no way out · why?' : 'policy details · why?')));
      y += 100;
    }
    return svg(out, width, y + 12, 'Platform map: vertical list of agents, three platform groups, request events and external services', 'list');
  }

  const kindChip = k => el('span', {class: 'chip ' + (k === 'blocked' ? 'denied' : 'allowed')}, k);

  // Count the facts actually observed, without turning partial coverage into a protection verdict.
  function stats(data) {
    if (!data || !data.topology) return null;
    const items = [[data.topology.nodes.filter(n => n.kind === 'agent').length, 'agents', 'Logical agents in the selected release drawing']];
    const checks = data.agents.map(a => Console.checkSummary(data.onboarding[a.name]));
    if (checks.every(Boolean)) {
      const sum = key => checks.reduce((n, c) => n + c[key], 0);
      items.push([sum('observed') + ' / ' + sum('total'), 'checks observed', sum('inferred') + ' inferred; ' + sum('declared') + ' declared. No overall protection verdict.']);
      if (sum('failing')) items.push([sum('failing'), 'checks failing', 'Observed facts contradict the declaration']);
    }
    return el('dl', {class: 'stats'}, items.map(([n, word, why]) => el('div', {title: why}, el('dt', {}, word), el('dd', {}, String(n)))));
  }
  // Plain words for the redactor's category codes (runtime/phase3/trusted_runtime.py SUPPORTED_ENTITIES). Unknown codes remain unspecified identifiers.
  const CATEGORY = {EMAIL_ADDRESS: 'an email address', PHONE_NUMBER: 'a phone number', CREDIT_CARD: 'a card number', IBAN_CODE: 'a bank account number (IBAN)',
                    SAUDI_BANK_ACCOUNT: 'a bank account number', SAUDI_NATIONAL_ID: 'a national ID number', SAUDI_RESIDENT_ID: 'a residence ID number',
                    SAUDI_VAT_ID: 'a VAT number'};
  const plainCategories = codes => {
    const said = [...new Set((codes || []).map(c => CATEGORY[c] || 'an unspecified identifier'))];
    return said.length ? said.length > 1 ? said.slice(0, -1).join(', ') + ' and ' + said[said.length - 1] : said[0] : 'unspecified identifiers';
  };
  Console.plainCategories = plainCategories;
  function eventText(e) {
    if (e.kind === 'masked') return (e.categories && e.categories.length ? 'Masked ' + plainCategories(e.categories) : 'Identifier check') + (e.caller ? ' · ' + e.caller : '');
    if (e.kind === 'approved') return 'Approved' + (e.action ? ' ' + e.action : '') + (e.target ? ' · ' + e.target : '');
    return (e.code || e.reason || 'refused').toLowerCase().replace(/_/g, ' ') + (e.target ? ' · ' + e.target : e.caller ? ' · ' + e.caller : '');
  }

  function side(data, activity) {
    const rows = data.agents.map(a => {
      const link = el('a', {href: '#/agents/' + encodeURIComponent(a.name), class: 'who'}, el('b', {}, Console.title(a)),
        el('span', {}, Console.countsText(data.onboarding[a.name])));
      return el('div', {class: 'row'}, link, Console.healthChip(a.health));
    });
    const events = activity && activity.events.length ? activity.events.map(e => el('div', {class: 'ev'}, kindChip(e.kind), el('span', {}, eventText(e)), el('time', {}, Console.ago(e.at))))
      : [el('p', {class: 'muted'}, activity && Object.values(activity.sources).includes('unavailable') && !activity.events.length ?
        'No activity yet. Some activity sources are not reachable.' : 'No activity yet.')];
    return el('div', {class: 'side'},
      el('section', {class: 'panel', 'aria-label': 'Agents'}, el('div', {class: 'label'}, 'Agents'), rows.length ? rows : el('p', {class: 'muted'}, 'No agents onboarded.')),
      el('section', {class: 'panel', 'aria-label': 'Live activity'}, el('div', {class: 'label'}, 'Live activity'), events),
      el('div', {class: 'btns'}, el('a', {class: 'btn inverse', href: '#/onboard'}, 'Review onboarding'), el('a', {class: 'btn denied', href: '#/break'}, 'Try to break it')));
  }

  Console.screens.map = (view, arg, alive) => {
    const numbers = el('div', {});
    view.append(el('div', {class: 'head'}, el('div', {class: 'title-row'}, el('h1', {}, 'Every agent gets its own room.'), numbers),
      el('span', {class: 'hint'}, 'Click any part to see how it works.')));
    const body = el('div', {}, el('p', {class: 'muted'}, 'Loading…'));
    view.append(body);
    const compact = window.matchMedia('(max-width: 860px)'), motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let last = '', drawn = '', grid = null, col = null, aside = null, panel = null, selected = null, currentData = null, currentActivity = null;
    const mark = () => grid && grid.querySelectorAll('.part').forEach(node => node.classList.toggle('sel', node.getAttribute('aria-label') === selected));
    const paint = () => {
      if (!grid) return;
      grid.classList.toggle('explaining', !!panel);
      col.replaceChildren(panel || aside);
      mark();
    };
    Console.setDock({
      show(nodes, spec, from) {
        panel = el('section', {class: 'panel xpanel' + (spec.live ? ' proof-live' : ''), role: 'region', 'aria-labelledby': 'ex-title'}, nodes);
        selected = from && from.classList && from.classList.contains('part') ? from.getAttribute('aria-label') : null;
        paint();
      },
      hide() {
        panel = null;
        const back = selected && grid && [...grid.querySelectorAll('.part')].find(node => node.getAttribute('aria-label') === selected);
        selected = null;
        paint();
        return back || null;
      }
    });
    const render = () => {
      if (!alive()) return;
      const data = currentData;
      numbers.replaceChildren(...[stats(data)].filter(Boolean));
      if (!data || !data.topology) {
        panel = null; selected = null; grid = null; drawn = '';
        body.replaceChildren(Console.empty('The console cannot reach its data.', 'Nothing is shown until the API answers.'));
        return;
      }
      aside = side(data, currentActivity);
      const key = JSON.stringify([data, compact.matches, motion.matches]);
      if (grid && key === drawn) { if (!panel) col.replaceChildren(aside); return; }
      const focusedPart = document.activeElement && document.activeElement.closest('.part');
      const focusedName = focusedPart && focusedPart.getAttribute('aria-label');
      const focusPanel = panel && panel.contains(document.activeElement);
      drawn = key;
      col = el('div', {class: 'col'});
      grid = el('div', {class: 'map'}, el('div', {class: 'panel cluster'}, drawing(data,
        (from, nodes) => modelExplain(from, alive, nodes), compact.matches)), col);
      paint();
      body.replaceChildren(grid);
      if (focusPanel) panel.querySelector('.close').focus();
      else if (focusedName) {
        const replacement = [...grid.querySelectorAll('.part')].find(node => node.getAttribute('aria-label') === focusedName);
        if (replacement) replacement.focus();
      }
    };
    const reflow = () => { if (currentData) render(); };
    compact.addEventListener('change', reflow); motion.addEventListener('change', reflow);
    Console.onExit(() => { compact.removeEventListener('change', reflow); motion.removeEventListener('change', reflow); });
    Console.every(async () => {
      const [data, activity] = await Promise.all([Console.loadAgents(), getJSON('/api/console/activity?limit=3')]);
      if (!alive()) return;
      const key = JSON.stringify([data, activity.data]);
      if (key === last) return;
      last = key; currentData = data; currentActivity = activity.ok ? activity.data : null;
      render();
    }, 10000);
  };
})();
