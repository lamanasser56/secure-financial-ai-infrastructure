/* Review existing manifest facts and observations. All requests are read-only. */
(() => {
  'use strict';
  const {el, getJSON} = Console;
  const CHIP = {observed: ['allowed', 'Observed', '✓'], inferred: ['declared', 'Inferred', '≈'], declared: ['declared', 'Declared', '—'], failing: ['denied', 'Failing', '!']};

  // A summary is intentionally not presented as a copyable, applicable agent.yaml.
  function summary(a) {
    const field = (name, value) => el('tr', {}, el('th', {scope: 'row'}, name), el('td', {}, value));
    return el('table', {class: 'x', 'aria-label': 'Manifest facts'}, el('tbody', {},
      field('Agent', a.name), field('Team', a.team), field('Runtime', a.runtime || 'unknown'),
      field('Budget', '$' + a.budget_usd_month.toFixed(2) + ' / month'), field('Masking', a.redaction),
      field('Tools', a.tools.map(t => t.id + ' · ' + t.access).join(', ') || 'none'),
      field('Data', a.data === 'none' ? 'none' : a.data.database + ' · through the trusted broker')));

  }

  async function showExample(from) {
    const r = await getJSON('/api/console/example');
    if (!document.contains(from)) return;
    if (!r.ok || !r.data.available) {
      Console.explain({eyebrow: 'EXPLAIN · EXAMPLE UNAVAILABLE', title: 'Expected rejection', blocks: [{label: 'Example', text: 'The example file is not available here.'}],
        file: 'docs/examples/rejected-agent/agent.yaml'}, from);
      return;
    }
    Console.explain({eyebrow: 'EXPLAIN · EXAMPLE FILE', title: 'Expected rejection', sub: r.data.file,
      blocks: [{label: 'What this screen does', text: 'Shows a shipped example. It does not execute the checker or create anything.'},
               {label: 'Run offline', node: el('pre', {class: 'code'}, r.data.command)},
               {label: 'Expected result', text: 'Nonzero exit status. The checker lists every broken rule and generates nothing. The budget breaks both per-agent and shared limits; the tool breaks both access and naming rules.'},
               {label: 'Example file', node: el('pre', {class: 'code'}, r.data.text)}], file: r.data.file}, from);
  }

  Console.screens.onboard = (view, arg, alive) => {
    let selected = arg, first = true, last = '', request = 0;
    const notice = el('p', {class: 'muted', role: 'status'}, 'Read-only review. No deployment or keys are created here.');
    const check = el('button', {type: 'button', class: 'btn inverse', onclick: () => { first = true; last = ''; tick(); }}, 'Refresh observations');
    view.append(Console.head('Review onboarding.', 'Manifest facts and checks, side by side.', check));
    const body = el('div', {}, el('p', {class: 'muted'}, 'Loading…'));
    const help = el('button', {type: 'button', class: 'btn link', onclick: e => Console.explain({eyebrow: 'EXPLAIN · OWNER WORKFLOW', title: 'Onboarding workflow',
      blocks: [{label: 'Review a manifest', node: el('pre', {class: 'code'}, 'make onboard-check F=platform/agents/<name>/agent.yaml')},
               {label: 'Generate reviewed configuration', node: el('pre', {class: 'code'}, 'make onboard A=<name>')},
               {label: 'Before deployment', text: 'A supported manifest must pass the current schema, image, budget and read-only tool rules. Review and commit the generated configuration; make up deploys the selected release. This screen performs none of these actions.'}],
      file: 'docs/console/onboarding-review.md'}, e.currentTarget)}, 'Owner workflow →');
    const example = el('button', {type: 'button', class: 'btn link', onclick: e => showExample(e.currentTarget)}, 'See example →');
    view.append(notice, body, help, el('div', {class: 'rejected'}, el('b', {}, 'EXPECTED REJECTION'),
      el('span', {}, 'Extra egress, a $500 budget and a write tool fail the current rules. The checker returns nonzero.'), example));
    async function tick() {
      const mine = ++request;
      check.disabled = true;
      const loaded = await Console.loadAgents();
      if (!alive() || mine !== request) return;
      check.disabled = false;
      const data = loaded && {...loaded, agents: loaded.agents.filter(a => a.kind !== 'platform')};
      const key = JSON.stringify(data) + selected;
      if (key === last) return;
      last = key;
      if (!data) { body.replaceChildren(Console.empty('The console cannot reach its data.', 'No checks are shown until the API answers.')); return; }
      if (!data.agents.length) { body.replaceChildren(Console.empty('No agents onboarded yet.', 'Review an agent manifest with the documented owner workflow.')); return; }
      if (!data.agents.some(a => a.name === selected)) selected = data.agents[0].name;
      const agent = data.agents.find(a => a.name === selected), onb = data.onboarding[selected];
      const picker = el('div', {class: 'tabsel', role: 'group', 'aria-label': 'Agent'}, data.agents.map(a => el('button', {type: 'button', 'aria-pressed': String(a.name === selected),
        onclick: () => { selected = a.name; first = true; last = ''; history.replaceState(null, '', '#/onboard/' + encodeURIComponent(a.name)); tick(); }}, Console.title(a))));
      const rows = onb ? onb.guarantees.map((g, i) => {
        const [kind, word, mark] = CHIP[Console.checkKind(g)];
        const row = el('div', {class: 'g' + (first && !Console.reduced() ? ' fill' : '')}, el('span', {class: 'ring ' + kind, 'aria-hidden': 'true'}, mark),
          el('button', {type: 'button', class: 'name', onclick: e => Console.explainGuarantee(g, e.currentTarget, agent)}, g.title), el('span', {class: 'chip ' + kind}, word));
        row.style.animationDelay = (i * 90) + 'ms';
        return row;
      }) : el('div', {class: 'empty'}, 'Checks are unavailable. No verdict is inferred.');
      first = false;
      body.replaceChildren(el('div', {class: 'two onb'},
        el('section', {class: 'panel', 'aria-label': 'Manifest summary'}, el('div', {class: 'card-head'}, el('h2', {}, 'Manifest summary')), picker, summary(agent),
          el('p', {class: 'g muted'}, 'Selected release facts. This summary is not an applicable YAML file.')),
        el('section', {class: 'panel', 'aria-label': 'Check observations'}, el('div', {class: 'card-head'}, el('h2', {}, 'Check observations')),
          el('div', {class: 'card-head muted'}, Console.countsText(onb)), rows)));
    }
    Console.every(tick, 5000);
  };
})();
