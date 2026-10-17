/* Try to break it: the latest attack-suite results from /api/console/attacks (the committed results file). No run button yet. */
(() => {
  'use strict';
  const {el, getJSON} = Console;
  // Display wording for the suite's case ids (docs/evidence/attack-suite.json). An unknown id is shown as it is, with no control named.
  const CASES = {
    financial_cross_user_database: ['Read another user\'s rows in the database', 'row-level security'],
    financial_cross_user_api_and_forged_session: ['Forge a session or name another user', 'signed sessions'],
    financial_show_saras_expenses: ['Ask for another user\'s expenses', 'own-rows tools'],
    financial_prompt_injection_in_question: ['Hide orders in the question', 'injection guard'],
    financial_filter_bypass_merchant_stays_grounded: ['Hide orders in a merchant name', 'grounding check'],
    financial_ungrounded_record_claim_feature3: ['Claim a record that does not exist', 'grounding check'],
    financial_question_figure_not_evidence: ['Pass off a number in the question as evidence', 'grounding check'],
    financial_merchant_with_digits_answers: ['A merchant name made of digits', 'grounding check'],
    financial_redaction_down_no_model_call: ['Make the redactor fail', 'fails closed'],
    financial_login_lockout_per_username: ['Guess a password', 'login lockout'],
    financial_session_epoch_restart: ['Reuse a session after a restart', 'session epoch'],
    unsigned_image_rejected: ['Run an unsigned image', 'signature check'],
    no_public_exposure: ['Expose a service to the internet', 'no public exposure'],
    egress_containment: ['Call the internet or reach another agent', 'network wall'],
    ops_agent_cannot_change_onboarded_agents: ['Make the ops agent change an agent', 'access rules'],
    ops_stale_approval_refused: ['Replay a stale approval', 'one-use approvals'],
    log_planted_instruction_stays_data: ['Plant an order in a log', 'logs are data'],
    no_secrets_in_env_or_logs: ['Find a secret in env or logs', 'secret handling']
  };

  Console.screens.break = async (view, arg, alive) => {
    view.append(Console.head('Try to break it.', 'Real attacks from the attack suite. Every one should fail.'));
    const body = el('div', {}, el('p', {class: 'muted'}, 'Loading…'));
    view.append(body);
    const r = await getJSON('/api/console/attacks');
    if (!alive()) return;
    if (!r.ok) { body.replaceChildren(Console.empty('The console cannot reach its data.', 'No attack results are shown until the API answers.')); return; }
    const d = r.data;
    if (!d.available) {
      body.replaceChildren(Console.empty('No attack results yet.', 'Run make attack to produce ' + d.file + '. The run button comes in a later phase.'));
      return;
    }
    const rows = d.results.map((x, i) => {
      const [name, by] = CASES[x.case] || [x.case, null], stopped = x.result === 'PASS';
      return el('div', {class: 'atk'}, el('span', {class: 'ring plain', 'aria-hidden': 'true'}, String(i + 1)),
        el('div', {}, el('b', {}, name), el('span', {class: 'by'}, (stopped ? (by ? 'stopped by ' + by : 'stopped') : 'not stopped in this run') + ' · ',
          el('time', {datetime: x.at}, new Date(x.at).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})))),
        el('span', {class: stopped ? 'chip denied' : 'chip bad'}, stopped ? 'Blocked' : 'Not stopped'));
    });
    const all = d.stopped === d.total;
    body.replaceChildren(el('div', {class: 'two wide'}, el('section', {class: 'panel', 'aria-label': 'Attacks'}, rows),
      el('section', {class: 'panel result', 'aria-label': 'Result'}, el('div', {class: 'big' + (all ? '' : ' bad')}, d.stopped + '/' + d.total), el('h2', {}, 'attacks stopped'),
        el('p', {class: 'muted'}, 'Latest run: ' + new Date(d.completed_at).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'}) + '. Results file, not a live run. Closed outcomes only.'),
        el('p', {}, el('button', {type: 'button', class: 'btn link', onclick: e => Console.explain({eyebrow: 'EXPLAIN · RESULTS FILE', title: 'Where these results come from',
          blocks: [{label: 'In plain words', text: 'The attack suite ran against the cluster and wrote this file. The console shows it; it does not run anything.'},
                   {label: 'How it works', text: 'make attack runs the suite from the owner laptop. Each case records PASS when the attack was stopped.'}], file: d.file}, e.currentTarget)}, 'See the results file →')))));
  };
})();
