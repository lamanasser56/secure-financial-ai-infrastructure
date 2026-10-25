/* Read-only, release-bound owner evidence. PASS is never inferred to mean an attack was blocked. */
(() => {
  'use strict';
  const {el, getJSON} = Console;
  const utc = value => new Date(value).toISOString().replace('T', ' ').replace(/\.\d+Z$/, ' UTC').replace(/Z$/, ' UTC');
  const binding = {
    current: 'This release', different_release: 'Other release', unbound: 'Release unbound', historical: 'Historical report'
  };
  function outcome(row) {
    if (row.kind === 'historical') return row.result === 'PASS' ? 'Recorded PASS' : 'Recorded FAIL';
    if (row.verdict === 'NOT_EXERCISED') return 'Not exercised';
    if (row.verdict === 'FAIL') return 'Failed';
    return row.kind === 'attack' ? 'Boundary held' : 'Passed';
  }
  function details(d, from) {
    const release = d.release;
    Console.explain({eyebrow: 'EXPLAIN · OWNER REPORT', title: 'What this report proves',
      sub: utc(d.completed_at), copy: d.run_id ? {label: 'Run', value: d.run_id} : null,
      blocks: [
        {label: 'Scope', text: 'An owner-run suite report, not an independent certification or a continuing live scan. A matching release means its selected source, image digests and declarations match this console.'},
        {label: 'Outcomes', text: 'Boundary held means that attack case passed its required controls. Passed means a positive or operational control passed. Not exercised means the case could not establish its result; it is neither success nor proof of a breach.'},
        {label: 'Release', node: release ? el('div', {}, el('p', {class: 'mono'}, 'Source ' + release.source_commit),
          el('p', {class: 'mono'}, 'Release ' + release.id), el('pre', {class: 'code'}, release.images.join('\n')))
          : el('p', {}, 'No qualified source and image binding in this report.')},
        {label: 'Runner', text: d.runner_commit || 'Runner source was not recorded.'},
        {label: 'Source', text: d.file + '. make attack publishes closed outcomes from the owner environment. This screen only reads them.'}
      ], file: 'platform/core/src/agent_platform/attack_results.py'}, from);
  }

  Console.screens.break = async (view, arg, alive) => {
    view.append(Console.head('Try to break it.', 'Recorded boundary checks and positive controls.'));
    const body = el('div', {}, el('p', {class: 'muted'}, 'Loading…'));
    view.append(body);
    const r = await getJSON('/api/console/attacks');
    if (!alive()) return;
    if (!r.ok) {
      body.replaceChildren(Console.empty('Results unavailable.', 'The API did not answer. No result is inferred.'));
      return;
    }
    const d = r.data;
    if (!d.available) {
      const title = d.status === 'invalid' ? 'Mounted results are invalid.' : d.status === 'unavailable' ? 'Mounted results are unreadable.' : 'No mounted results.';
      body.replaceChildren(Console.empty(title, 'Run make attack from the approved release checkout to publish results. This screen is read-only.'));
      return;
    }
    const rows = d.results.map((row, index) => el('div', {class: 'atk'},
      el('span', {class: 'ring plain', 'aria-hidden': 'true'}, String(index + 1)),
      el('div', {}, el('b', {}, row.label), el('span', {class: 'by'}, row.purpose + ' · ',
        el('time', {datetime: row.at}, utc(row.at)))),
      el('span', {class: 'chip ' + (row.kind === 'historical' ? 'muted' : row.verdict === 'FAIL' ? 'bad' : row.verdict === 'NOT_EXERCISED' ? 'declared' : row.kind === 'control' ? 'allowed' : 'denied')}, outcome(row))));
    const FIRST = 6;
    const list = el('section', {class: 'panel', 'aria-label': 'Checks'}, rows.slice(0, FIRST));
    if (rows.length > FIRST) {
      const more = el('div', {class: 'more'}, el('button', {type: 'button', class: 'btn link', 'aria-expanded': 'false', onclick: event => {
        const open = event.currentTarget.getAttribute('aria-expanded') !== 'true';
        list.replaceChildren(...(open ? rows : rows.slice(0, FIRST)), more);
        event.currentTarget.setAttribute('aria-expanded', String(open));
        event.currentTarget.textContent = open ? 'Show the first ' + FIRST : 'Show all ' + rows.length;
      }}, 'Show all ' + rows.length));
      list.append(more);
    }
    const attacks = d.summary.attack, controls = d.summary.control;
    const missing = attacks.not_exercised + controls.not_exercised;
    const failed = attacks.failed + controls.failed;
    const historical = d.binding === 'historical';
    body.replaceChildren(el('div', {class: 'two wide'}, list,
      el('section', {class: 'panel result', 'aria-label': 'Result'},
        el('div', {class: 'eyebrow'}, binding[d.binding]),
        el('div', {class: 'big' + (failed || missing || d.binding !== 'current' ? ' bad' : '')}, historical ? '—' : attacks.passed + '/' + attacks.total),
        el('h2', {}, historical ? 'Unqualified outcomes' : 'boundary checks passed'),
        historical ? el('p', {class: 'muted'}, 'Original control semantics and release binding were not recorded. These outcomes do not qualify this release.')
          : el('p', {}, controls.passed + '/' + controls.total + ' controls passed · ' + failed + ' failed · ' + missing + ' not exercised'),
        d.binding !== 'current' && !historical ? el('p', {class: 'note'}, 'This report does not qualify this release.') : null,
        !d.complete && !historical ? el('p', {class: 'note'}, 'Incomplete report. Required execution or runner identity is missing.') : null,
        el('p', {class: 'muted'}, el('time', {datetime: d.completed_at}, utc(d.completed_at))),
        el('button', {type: 'button', class: 'btn link', onclick: event => details(d, event.currentTarget)}, 'Report details →'))));
  };
})();
