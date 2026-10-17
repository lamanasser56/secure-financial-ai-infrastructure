/* Onboard: the agent.yaml facts on the left, the eight guarantees on the right (verified / declared / failing), refreshed while the screen is open. */
(() => {
  'use strict';
  const {el, getJSON} = Console;
  const CHIP = {verified: ['allowed', 'Verified', '✓'], declared: ['declared', 'Declared', '✓'], failing: ['denied', 'Failing', '!']};

  // The condensed manifest, from the manifest facts the API returns for this agent (no file text is invented).
  function yaml(a) {
    const row = (k, v) => [el('span', {class: 'k'}, k + ':'), ' ' + v, '\n'];
    return el('pre', {class: 'yaml', 'aria-label': 'agent.yaml'}, row('agent', a.name), row('team', a.team), row('runtime', (a.runtime || '').split(' ')[0] || 'unknown'),
      row('budget', '$' + a.budget_usd_month.toFixed(2) + ' / month'), row('redaction', a.redaction),
      row('tools', '[' + a.tools.map(t => t.id + ' · ' + t.access).join(', ') + ']'), row('data', a.data === 'none' ? 'none' : a.data.database + ' · own rows'));
  }

  async function showExample(from) {
    const r = await getJSON('/api/console/example');
    if (!r.ok || !r.data.available) {
      Console.explain({eyebrow: 'EXPLAIN · NOT SEEN LIVE', title: 'A file the platform refuses', blocks: [{label: 'Example', text: 'The example file is not available here.'}],
        file: 'docs/examples/rejected-agent/'}, from);
      return;
    }
    Console.explain({eyebrow: 'EXPLAIN · EXAMPLE FILE', title: 'A file the platform refuses', sub: r.data.file,
      blocks: [{label: 'In plain words', text: 'This manifest asks for more than the platform allows. Nothing is created from it.'},
               {label: 'How it works', text: 'Run ' + r.data.command + '. The platform prints one line per broken rule and generates nothing.'},
               {label: 'The file', node: el('pre', {class: 'code'}, r.data.text)}], file: r.data.file}, from);
  }

  Console.screens.onboard = (view, arg, alive) => {
    let selected = arg, first = true, last = '';
    const check = el('button', {type: 'button', class: 'btn inverse', onclick: () => { first = true; last = ''; tick(); }}, '▶ Check again');
    view.append(Console.head('Add a new agent.', 'One file in. Eight guarantees out.', check));
    const body = el('div', {}, el('p', {class: 'muted'}, 'Loading…'));
    const example = el('button', {type: 'button', class: 'btn link', onclick: e => showExample(e.currentTarget)}, 'See example →');
    view.append(body, el('div', {class: 'rejected'}, el('b', {}, 'REJECTED'),
      el('span', {}, 'A file asking for the internet, a write tool, or a $500 budget is refused. Nothing gets created.'), example));
    async function tick() {
      const loaded = await Console.loadAgents();
      if (!alive()) return;
      // Onboard is about agent.yaml: platform tenants (the ops agent) are not onboarded from a manifest.
      const data = loaded && {...loaded, agents: loaded.agents.filter(a => a.kind !== 'platform')};
      const key = JSON.stringify(data) + selected;
      if (key === last) return;
      last = key;
      if (!data) { body.replaceChildren(Console.empty('The console cannot reach its data.', 'No guarantees are shown until the API answers.')); return; }
      if (!data.agents.length) { body.replaceChildren(Console.empty('No agents onboarded yet.', 'Add platform/agents/<name>/agent.yaml and run make onboard.')); return; }
      if (!data.agents.some(a => a.name === selected)) selected = data.agents[0].name;
      const agent = data.agents.find(a => a.name === selected), onb = data.onboarding[selected];
      const picker = el('div', {class: 'tabsel', role: 'group', 'aria-label': 'Agent'}, data.agents.map(a => el('button', {type: 'button', 'aria-pressed': String(a.name === selected),
        onclick: () => { selected = a.name; first = true; last = ''; history.replaceState(null, '', '#/onboard/' + encodeURIComponent(a.name)); tick(); }}, a.name)));
      const rows = onb ? onb.guarantees.map((g, i) => {
        const [kind, word, mark] = CHIP[g.state];
        const row = el('div', {class: 'g' + (first && !Console.reduced() ? ' fill' : '')}, el('span', {class: 'ring ' + kind, 'aria-hidden': 'true'}, mark),
          el('button', {type: 'button', class: 'name', onclick: e => Console.explainGuarantee(g, e.currentTarget)}, g.title),
          g.basis === 'inference' ? el('span', {class: 'hint'}, 'inferred') : null, el('span', {class: 'chip ' + kind}, word));
        row.style.animationDelay = (i * 90) + 'ms';  // CSSOM, not a style attribute: allowed by the page's CSP
        return row;
      }) : el('div', {class: 'empty'}, 'Guarantees are not available right now.');
      first = false;
      body.replaceChildren(el('div', {class: 'two'},
        el('section', {class: 'panel', 'aria-label': 'agent.yaml'}, el('div', {class: 'card-head'}, el('span', {class: 'mono muted'}, 'agent.yaml')), picker, yaml(agent)),
        el('section', {class: 'panel', 'aria-label': 'The platform builds'}, el('div', {class: 'card-head'}, el('h2', {}, 'The platform builds'),
          onb ? el('span', {class: 'count'}, onb.counts.verified + ' / ' + onb.total, onb.counts.failing ? el('span', {class: 'bad'}, onb.counts.failing + ' failing') : null) : null), rows)));
    }
    Console.every(tick, 5000);
  };
})();
