"""Static invariants of the console UI (platform/core/ui) and the Financial Agent UI that shares its design.

Browser behaviour is tested under tests/browser; API behaviour is covered in test_console.py. These checks pin what the design spec and the page's CSP require.
"""
from pathlib import Path
import re
import unittest

REPO = Path(__file__).resolve().parents[3]
FRONT = REPO / 'platform/core/ui'
FIN = REPO / 'platform/agents/financial/finance_agent/ui'
REPO_ROOT = Path(__file__).resolve().parents[3]
FRONT_FILES = ('index.html', 'style.css', 'core.js', 'app.js', 'map.js', 'agents.js', 'onboard.js', 'attacks.js', 'ops.js', 'shared-assets.json')
FONTS = ('barlow-semi-condensed-latin-700-normal', 'barlow-semi-condensed-latin-800-normal', 'ibm-plex-sans-latin-400-normal',
         'ibm-plex-sans-latin-500-normal', 'ibm-plex-sans-latin-600-normal', 'ibm-plex-mono-latin-400-normal', 'ibm-plex-mono-latin-500-normal') + tuple('ibm-plex-sans-arabic-arabic-%d-normal' % weight for weight in (400, 500, 600, 700))
SCRIPTS = [FRONT / n for n in FRONT_FILES if n.endswith('.js')] + [FIN / 'app.js']
PAGES = (FRONT / 'index.html', FIN / 'index.html')


class Assets(unittest.TestCase):
    def test_exact_file_set(self):
        self.assertEqual(sorted(p.name for p in FRONT.iterdir()), sorted(FRONT_FILES + ('typeface',)))
        self.assertEqual(sorted(p.name for p in FIN.iterdir()), ['app.js', 'index.html'])

    def test_fonts_are_self_hosted_ofl_woff2(self):
        css = (FRONT / 'style.css').read_text()
        urls = re.findall(r"url\('([^']+)'\)", css)
        self.assertEqual(sorted(urls), sorted('/typeface/' + f + '.woff2' for f in FONTS))
        for f in FONTS:
            self.assertEqual((FRONT / 'typeface' / (f + '.woff2')).read_bytes()[:4], b'wOF2')
        for licence in ('LICENSE-barlow.txt', 'LICENSE-ibm-plex.txt', 'LICENSE-ibm-plex-sans-arabic.txt'):
            self.assertIn('SIL Open Font License', (FRONT / 'typeface' / licence).read_text())

    def test_tokens_and_type_from_the_spec(self):
        css = (FRONT / 'style.css').read_text()
        for token in ('--bg: #0C2745', '--ink: #F2F7FF', '--box: #14406E', '--panel: rgba(18, 58, 99, 0.45)', '--muted: #9DB6D6',
                      '--allowed: #7CF0C0', '--denied: #FFB547'):
            self.assertIn(token, css)
        self.assertIn('background-size: 96px 96px, 96px 96px, 24px 24px, 24px 24px', css)
        self.assertIn('prefers-reduced-motion: reduce', css)
        self.assertIn('forced-colors: active', css)
        # IBM Plex Mono only for ids, digests, code (never a heading or the body)
        self.assertEqual(re.findall(r'font[^;{}]*var\(--mono\)', css.split('.mono')[0]), [])

    def test_no_external_origin_anywhere(self):
        for path in [*FRONT.glob('*'), *FIN.glob('*')]:
            if path.is_file():
                text = path.read_text()
                for url in re.findall(r'https?://[^\s\'")<>]+', text):
                    # links only (never fetched; the CSP allows no other origin): this repository's files on GitHub
                    self.assertRegex(url, r'^(http://(127\.0\.0\.1[:/]|www\.w3\.org/2000/svg)|https://github\.com/lamanasser56/secure-financial-ai-infrastructure/blob/$)',
                                     f'{path.name}: {url}')
        for page in PAGES:
            self.assertNotRegex(page.read_text(), r'(src|href)="https?://')


class Scripts(unittest.TestCase):
    def test_no_inner_html_eval_or_storage_of_data(self):
        for script in SCRIPTS:
            text = script.read_text()
            with self.subTest(script=script.parent.name + '/' + script.name):
                for banned in ('innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write', 'eval(', 'new Function', 'localStorage', 'sessionStorage'):
                    self.assertNotIn(banned, text)
                for open_, close in ('()', '[]', '{}'):
                    self.assertEqual(text.count(open_), text.count(close), open_ + close)

    def test_csp_compatible_pages(self):  # script-src 'self'; style-src 'self'; img-src 'none'
        for page in PAGES:
            text = page.read_text()
            self.assertNotIn('style=', text)
            self.assertNotIn('<img', text)
            self.assertNotRegex(text, r'<script(?![^>]*\bsrc=)')
            self.assertNotRegex(text, r'<style')
        for script in SCRIPTS:
            self.assertNotRegex(script.read_text(), r"setAttribute\('style'|style: ['\"]")

    def test_no_sample_data_or_invented_values(self):
        for script in SCRIPTS:
            text = script.read_text()
            self.assertNotRegex(text, r'(?i)sample data|lorem|placeholder data')
        for name in ('map.js', 'agents.js', 'onboard.js', 'attacks.js', 'ops.js', 'app.js'):
            text = (FRONT / name).read_text()
            for agent in ('platform-guide', 'agent-financial'):  # agents come only from the API
                self.assertNotIn("'" + agent + "'", text, name)
        self.assertNotIn('Sample data', (FRONT / 'index.html').read_text())

    def test_every_screen_has_an_honest_empty_or_error_state(self):
        for name in ('map.js', 'agents.js', 'onboard.js', 'attacks.js', 'ops.js'):
            self.assertIn('Console.empty(', (FRONT / name).read_text(), name)

    def test_proof_is_never_invented(self):
        core = (FRONT / 'core.js').read_text()
        self.assertIn("'No live proof available'", core)
        self.assertIn('EXPLAIN · NOT SEEN LIVE', core)
        self.assertIn('EXPLAIN · OBSERVED', core)
        self.assertIn("explainTopic('network'", (FRONT / 'map.js').read_text())

    def test_health_chip_has_no_chip_when_health_is_null(self):
        app = (FRONT / 'app.js').read_text()
        self.assertIn('if (!health) return null;', app)
        for label in ("'Running'", "'Not ready'", "'Absent'"):
            self.assertIn(label, app)

    def test_passport_flip_leaves_no_transform_behind(self):
        agents, css = (FRONT / 'agents.js').read_text(), (FRONT / 'style.css').read_text()
        animate = agents[agents.index('page.animate('):]
        animate = animate[:animate.index(');') + 2]
        self.assertNotRegex(animate, r"fill\s*:\s*'(forwards|both)'")  # no fill: the element ends with no transform at all
        self.assertIn('rotateY(0deg)', animate)
        for rule in re.findall(r'\.passport[^{]*\{[^}]*\}', css):
            self.assertNotIn('transform', rule)
            self.assertNotIn('will-change', rule)
        self.assertIn('Console.reduced()', animate + agents)

    def test_passport_values_stay_on_one_line(self):
        css = (FRONT / 'style.css').read_text()
        rule = re.search(r'\.field b \{[^}]*\}', css).group(0)
        for prop in ('white-space: nowrap', 'text-overflow: ellipsis'):
            self.assertIn(prop, rule)
        self.assertIn("el('b', {title: value}, value)", (FRONT / 'agents.js').read_text())  # the full value on hover, if ever cut

    def test_platform_tenant_is_shown_from_the_api_not_hard_coded(self):
        agents, mapjs = (FRONT / 'agents.js').read_text(), (FRONT / 'map.js').read_text()
        self.assertIn("agent.kind === 'platform'", agents)
        self.assertIn("a.kind === 'platform' ? 'acts with approval'", mapjs)
        self.assertNotIn('Security & Ops', agents + mapjs)  # the display name comes from the API
        self.assertIn("filter(a => a.kind !== 'platform')", (FRONT / 'onboard.js').read_text())

    def test_proof_is_focused_wrapped_short_and_expandable(self):
        core, css = (FRONT / 'core.js').read_text(), (FRONT / 'style.css').read_text()
        self.assertIn('const SHORT = 6;', core)
        self.assertIn("'Show full proof ('", core)
        self.assertIn('function narrow(proof, focus)', core)
        self.assertIn('white-space: pre-wrap', re.search(r'\.drawer \.code \{[^}]*\}', css).group(0))
        self.assertIn("explainTopic('network', from, focus)", (FRONT / 'map.js').read_text())

    def test_drawer_shortens_ids_and_links_code(self):
        core = (FRONT / 'core.js').read_text()
        self.assertIn("value.slice(0, 4) + '…' + value.slice(-4)", core)
        self.assertIn('navigator.clipboard.writeText(value)', core)

    def test_ops_explain_says_not_needed_when_an_automated_fix_is_proposed(self):
        ops = (FRONT / 'ops.js').read_text()
        self.assertIn("b.automated_fix ? 'Not needed: an automated fix is proposed.' : 'No explanation yet.'", ops)

    def test_mrz_is_built_from_real_values_only(self):
        agents = (FRONT / 'agents.js').read_text()
        body = agents[agents.index('function mrz('):agents.index('const emblem')]
        for real in ('agent.name', 'agent.namespace', 'image_digests', 'budget_usd_month', 'checkSummary', 'health'):
            self.assertIn(real, body)

    def test_break_it_has_no_run_button_and_an_empty_state(self):
        attacks = (FRONT / 'attacks.js').read_text()
        self.assertNotIn('Run the attacks', attacks)
        self.assertIn('No mounted results.', attacks)
        self.assertIn('/api/console/attacks', attacks)

    def test_break_it_cases_open_and_counts_are_split_by_kind(self):
        attacks = (FRONT / 'attacks.js').read_text()
        self.assertIn("el('button', {type: 'button', class: 'atk'", attacks)  # every case is openable
        self.assertIn('openCase(d, row, index', attacks)
        self.assertIn("'Attack cases: ' + counts(attacks, 'held')", attacks)
        self.assertIn("'Controls: ' + counts(controls, 'passed')", attacks)
        self.assertIn('d.incomplete', attacks)  # the note names each case and its recorded reason
        self.assertNotIn('Required execution or runner identity is missing', attacks)

    def test_map_lines_have_wide_click_targets_and_explains_cite_attack_cases(self):
        map_js, core, css = ((FRONT / n).read_text() for n in ('map.js', 'core.js', 'style.css'))
        self.assertIn("class: 'hit'", map_js)       # Platform network paths: the whole bus area
        self.assertIn("class: 'hit-line'", map_js)  # Internet: the deny line, besides the dashed box
        self.assertIn('pointer-events: all', css)
        self.assertIn('EXPLAIN · PROVEN BY ATTACK RUN', core)
        self.assertIn("'/#/break/' + encodeURIComponent(c.case)", core)
        self.assertIn('Console.attackProof(data.attack_proof)', map_js)

    def test_refresh_buttons_are_never_disabled_by_background_polls(self):
        ops, onboard = (FRONT / 'ops.js').read_text(), (FRONT / 'onboard.js').read_text()
        self.assertIn("if (manual === true) { refreshButton.disabled = true;", ops)  # only a click disables it
        self.assertIn("if (manual === true) { check.disabled = true;", onboard)
        self.assertEqual(ops.count('refreshButton.disabled = true'), 1)
        self.assertEqual(onboard.count('check.disabled = true'), 1)
        self.assertIn("refresh(true)", ops)
        self.assertIn("tick(true)", onboard)

    def test_a_declared_stopped_target_and_the_observer_row_say_what_they_are(self):
        ops = (FRONT / 'ops.js').read_text()
        self.assertIn('Stopped by design · the release declares 0 replicas', ops)
        self.assertNotIn("'Ops API answered; own pod not observed', 'answered'", ops)
        self.assertIn('an observer does not vouch for itself', ops)
    def test_guide_renders_markdown_as_dom_with_distinct_source_titles(self):
        guide = (REPO_ROOT / 'platform/agents/platform-guide/public/app.js').read_text()
        self.assertNotIn('innerHTML', guide)
        self.assertIn("function markdown(text, cls)", guide)
        self.assertIn('sourceTitle(source, result.sources)', guide)  # document · section, numbered when repeated
        answered = guide[guide.index("if (result.status === 'answered')"):guide.index("} else nodes.push(el('p', {class: 'guide-state', role: 'status'}, reasonText(result.reason)));")]
        self.assertIn('guide-note', answered)  # the sources note appears only when there are sources
        self.assertNotIn('Preview only', guide)
    def test_signed_out_is_a_normal_answer_not_an_api_error(self):
        fin, core = (FIN / 'app.js').read_text(), (FRONT / 'core.js').read_text()
        self.assertIn("Console.observeAPI(response.status, true, path === '/api/me' && response.status === 401)", fin)
        self.assertIn("status >= 400 && !expected ? 'error' : 'answered'", core)

    def test_ops_is_minimal_and_has_no_rollback(self):
        ops = (FRONT / 'ops.js').read_text()
        self.assertNotIn('rollback', ops.lower())
        for text in ('Incident timeline', 'Needs approval', 'No pending approvals.', "operation: 'approve'", "operation: 'execute'", 'X-Demo-CSRF', "type: 'password'"):
            self.assertIn(text, ops)

    def test_labelled_inputs_and_real_buttons(self):
        for script in (FIN / 'app.js', FRONT / 'ops.js'):
            text = script.read_text()
            for ident in re.findall(r"el\('input', \{id: '([\w-]+)'", text):
                self.assertRegex(text, r"el\('label', \{for: '" + re.escape(ident) + "'")
        for script in SCRIPTS:
            self.assertNotRegex(script.read_text(), r"el\('(div|span)', \{[^}]*onclick")  # clickable things are buttons or links
        self.assertIn(':focus-visible', (FRONT / 'style.css').read_text())



if __name__ == '__main__':
    unittest.main()
