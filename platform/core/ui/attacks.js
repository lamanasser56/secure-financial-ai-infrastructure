/* Read-only, release-bound owner evidence. PASS is never inferred to mean an attack was blocked. */
(() => {
  'use strict';
  const {el, getJSON} = Console;
  const utc = value => new Date(value).toISOString().replace('T', ' ').replace(/\.\d+Z$/, ' UTC').replace(/Z$/, ' UTC');
  const binding = {
    current: 'This release', different_release: 'Other release', unbound: 'Release unbound', historical: 'Historical report'
  };
  // Closed reasons recorded by the suite (attack_suite.py / attack_runtime.py). Unknown codes are shown as recorded.
  const REASONS = {
    active_turn_not_established: 'The two simultaneous user turns could not be held open together.',
    active_turn_did_not_finish: 'A user turn did not finish after the probe.',
    frontdoor_turn_unavailable: 'The front door did not answer a probe turn.',
    boundary_positive_control_unavailable: 'The same valid model request did not succeed before the outage, so a refusal could not be told apart from a provider failure.',
    redactor_outage_not_established: 'The redactor could not be stopped for the test.',
    previous_fault_pods_still_present: 'Pods from an earlier fault were still terminating.',
    planted_log_not_observed: 'The observer did not report the planted crash loop in time.',
    observer_unavailable: 'The Ops observer did not answer.',
    probe_rollout_failed: 'The temporary probe worker did not become ready.',
    dns_or_target_failure: 'A destination failed for a reason other than policy.',
    model_control_not_exercised: 'The model did not answer or block for a policy reason (provider unavailable).',
    runner_commit_not_recorded: 'The runner source commit was not recorded.',
    control_unavailable: 'A required control was unavailable.',
    cleanup_failed_earlier: 'An earlier cleanup failed, so later cases were not run.',
    not_recorded: 'The report did not record a reason.'
  };
  const reasonText = code => !code ? null : REASONS[code] || (code.startsWith('requires_') ? 'Its prerequisite did not pass: ' + code.slice(9) + '.' : code);
  function outcome(row) {
    if (row.kind === 'historical') return row.result === 'PASS' ? 'Recorded PASS' : 'Recorded FAIL';
    if (row.verdict === 'NOT_EXERCISED') return 'Not exercised';
    if (row.verdict === 'FAIL') return 'Failed';
    return row.kind === 'attack' ? 'Boundary held' : 'Passed';
  }
  const chip = row => el('span', {class: 'chip ' + (row.kind === 'historical' ? 'muted' : row.verdict === 'FAIL' ? 'bad'
    : row.verdict === 'NOT_EXERCISED' ? 'declared' : row.kind === 'control' ? 'allowed' : 'denied')}, outcome(row));
  const MEANING = {
    'attack:PASS': 'The attack was attempted against this release and every required check held.',
    'attack:FAIL': 'The attack was attempted and a required check did not hold.',
    'attack:NOT_EXERCISED': 'The attack could not be carried out completely, so it proves nothing either way.',
    'control:PASS': 'A positive or operational control worked, so the attack results around it are meaningful.',
    'control:FAIL': 'A positive or operational control failed.',
    'control:NOT_EXERCISED': 'The control could not run.'
  };
  function openCase(d, row, index, from) {
    const facts = row.facts || [];
    Console.explain({eyebrow: 'EXPLAIN · CASE ' + (index + 1) + ' OF ' + d.results.length + ' · ' + (row.kind === 'attack' ? 'ATTACK' : row.kind === 'control' ? 'CONTROL' : 'ARCHIVED'),
      title: row.label, sub: row.purpose,
      blocks: [
        {label: 'Outcome', node: el('p', {}, chip(row), ' ', MEANING[row.kind + ':' + row.verdict] || 'Archived outcome; its control semantics were not recorded.')},
        row.reason ? {label: 'Why', node: el('div', {}, el('p', {}, reasonText(row.reason)), el('p', {class: 'mono muted'}, row.reason))} : null,
        {label: 'When', node: el('p', {class: 'mono'}, utc(row.at))},
        facts.length ? {label: 'Recorded facts', node: el('pre', {class: 'code'}, facts.map(([k, v]) => k + ': ' + v).join('\n'))}
          : {label: 'Recorded facts', text: d.schema_version >= 3 ? 'This case recorded no facts.' : 'Reports before version 3 did not keep per-case facts.'},
        {label: 'Report', text: 'Run ' + (d.run_id || 'unrecorded') + ' · ' + binding[d.binding] + '.'}
      ].filter(Boolean), file: 'platform/clouds/gke/attack_suite.py'}, from);
  }
  function details(d, from) {
    const release = d.release;
    Console.explain({eyebrow: 'EXPLAIN · OWNER REPORT', title: 'What this report proves',
      sub: utc(d.completed_at), copy: d.run_id ? {label: 'Run', value: d.run_id} : null,
      blocks: [
        {label: 'Scope', text: 'An owner-run suite report, not an independent certification or a continuing live scan. A matching release means its selected source, image digests and declarations match this console.'},
        {label: 'Outcomes', text: 'Attack cases try to break a boundary: boundary held means every required check held. Controls are setup, positive and cleanup checks that make the attack results meaningful. Not exercised means the case could not establish its result; it is neither success nor proof of a breach.'},
        {label: 'Release', node: release ? el('div', {}, el('p', {class: 'mono'}, 'Source ' + release.source_commit),
          el('p', {class: 'mono'}, 'Release ' + release.id), el('pre', {class: 'code'}, release.images.join('\n')))
          : el('p', {}, 'No qualified source and image binding in this report.')},
        {label: 'Runner', text: d.runner_commit || 'Runner source was not recorded.'},
        {label: 'Source', text: d.file + '. make attack publishes closed outcomes from the owner environment. This screen only reads them.'}
      ], file: 'platform/core/src/agent_platform/attack_results.py'}, from);
  }
  const counts = (s, noun) => s.passed + ' ' + noun + ' · ' + s.failed + ' failed · ' + s.not_exercised + ' not exercised (of ' + s.total + ')';

  Console.screens.break = async (view, arg, alive) => {
    view.append(Console.head('Try to break it.', 'Attack cases against this release, and the controls that make them meaningful.'));
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
    const rows = d.results.map((row, index) => el('button', {type: 'button', class: 'atk', 'data-case': row.case,
        'aria-label': row.label + ' — ' + outcome(row) + ', open the case', onclick: event => openCase(d, row, index, event.currentTarget)},
      el('span', {class: 'ring plain', 'aria-hidden': 'true'}, String(index + 1)),
      el('span', {class: 'what'}, el('b', {}, row.label), el('span', {class: 'by'}, (row.kind === 'control' ? 'Control · ' : row.kind === 'attack' ? 'Attack · ' : '') + row.purpose + ' · ',
        el('time', {datetime: row.at}, utc(row.at)))),
      chip(row)));
    const FIRST = 6;
    const wanted = arg ? d.results.findIndex(row => row.case === arg) : -1;
    const list = el('section', {class: 'panel', 'aria-label': 'Cases'});
    let open = wanted >= FIRST;
    const more = el('div', {class: 'more'}, el('button', {type: 'button', class: 'btn link', 'aria-expanded': String(open), onclick: event => {
      open = !open; paint();
      event.currentTarget.setAttribute('aria-expanded', String(open));
      event.currentTarget.textContent = open ? 'Show the first ' + FIRST : 'Show all ' + rows.length;
    }}, open ? 'Show the first ' + FIRST : 'Show all ' + rows.length));
    const paint = () => list.replaceChildren(...(open ? rows : rows.slice(0, FIRST)), ...(rows.length > FIRST ? [more] : []));
    paint();
    const attacks = d.summary.attack, controls = d.summary.control;
    const missing = attacks.not_exercised + controls.not_exercised;
    const failed = attacks.failed + controls.failed;
    const historical = d.binding === 'historical';
    const why = (d.incomplete || []).map(item => el('li', {}, el('b', {}, item.label),
      ' — ' + (item.verdict === 'FAIL' ? 'failed' : item.verdict === 'NOT_EXERCISED' ? 'not exercised' : 'missing') + (item.reason ? ': ' + reasonText(item.reason) : '')));
    body.replaceChildren(el('div', {class: 'two wide'}, list,
      el('section', {class: 'panel result', 'aria-label': 'Result'},
        el('div', {class: 'eyebrow'}, binding[d.binding]),
        el('div', {class: 'big' + (failed || missing || d.binding !== 'current' ? ' bad' : '')}, historical ? '—' : attacks.passed + '/' + attacks.total),
        el('h2', {}, historical ? 'Unqualified outcomes' : 'attack cases held'),
        historical ? el('p', {class: 'muted'}, 'Original control semantics and release binding were not recorded. These outcomes do not qualify this release.')
          : el('div', {}, el('p', {}, 'Attack cases: ' + counts(attacks, 'held')), el('p', {}, 'Controls: ' + counts(controls, 'passed')),
            el('p', {class: 'muted'}, attacks.total + ' attack cases + ' + controls.total + ' controls = ' + d.results.length + ' recorded cases.')),
        d.binding !== 'current' && !historical ? el('p', {class: 'note'}, 'This report does not qualify this release.') : null,
        !d.complete && !historical ? el('div', {class: 'note'}, el('p', {}, 'Incomplete report. It cannot qualify this release because:'),
          why.length ? el('ul', {class: 'why'}, why) : el('p', {}, 'The report did not record why.')) : null,
        el('p', {class: 'muted'}, el('time', {datetime: d.completed_at}, utc(d.completed_at))),
        el('button', {type: 'button', class: 'btn link', onclick: event => details(d, event.currentTarget)}, 'Report details →'))));
    if (wanted >= 0) {
      rows[wanted].scrollIntoView({block: 'center'});
      openCase(d, d.results[wanted], wanted, rows[wanted]);
    }
  };
})();
