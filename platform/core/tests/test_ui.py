"""Static invariants of the console UI (platform/core/ui) and the Financial Agent UI that shares its design.

No JS engine runs offline: behaviour is covered by the screenshots of a local stub run (console_stub.py, ui_stub.py) and by
the HTTP tests in test_console.py. These checks pin what the design spec and the page's CSP require.
"""
from pathlib import Path
import re
import unittest

REPO = Path(__file__).resolve().parents[3]
FRONT = REPO / 'platform/core/ui'
FIN = REPO / 'platform/agents/financial/finance_agent/ui'
FRONT_FILES = ('index.html', 'style.css', 'core.js', 'app.js', 'map.js', 'agents.js', 'onboard.js', 'attacks.js', 'ops.js')
SHARED = ('style.css', 'core.js')
FONTS = ('barlow-semi-condensed-latin-700-normal', 'barlow-semi-condensed-latin-800-normal', 'ibm-plex-sans-latin-400-normal',
         'ibm-plex-sans-latin-500-normal', 'ibm-plex-sans-latin-600-normal', 'ibm-plex-mono-latin-400-normal', 'ibm-plex-mono-latin-500-normal')
SCRIPTS = [FRONT / n for n in FRONT_FILES if n.endswith('.js')] + [FIN / 'app.js', FIN / 'core.js']
PAGES = (FRONT / 'index.html', FIN / 'index.html')


class Assets(unittest.TestCase):
    def test_exact_file_set(self):
        self.assertEqual(sorted(p.name for p in FRONT.iterdir()), sorted(FRONT_FILES + ('typeface',)))
        self.assertEqual(sorted(p.name for p in FIN.iterdir()), ['app.js', 'core.js', 'index.html', 'style.css', 'typeface'])

    def test_shared_design_is_byte_identical_in_both_uis(self):
        for name in SHARED:
            self.assertEqual((FRONT / name).read_bytes(), (FIN / name).read_bytes(), name)
        self.assertEqual(sorted(p.name for p in (FRONT / 'typeface').iterdir()), sorted(p.name for p in (FIN / 'typeface').iterdir()))
        for p in (FRONT / 'typeface').iterdir():
            self.assertEqual(p.read_bytes(), (FIN / 'typeface' / p.name).read_bytes(), p.name)

    def test_fonts_are_self_hosted_ofl_woff2(self):
        css = (FRONT / 'style.css').read_text()
        urls = re.findall(r"url\('([^']+)'\)", css)
        self.assertEqual(sorted(urls), sorted('/typeface/' + f + '.woff2' for f in FONTS))
        for f in FONTS:
            self.assertEqual((FRONT / 'typeface' / (f + '.woff2')).read_bytes()[:4], b'wOF2')
        for licence in ('LICENSE-barlow.txt', 'LICENSE-ibm-plex.txt'):
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
                    self.assertRegex(url, r'^http://(127\.0\.0\.1[:/]|www\.w3\.org/2000/svg)', f'{path.name}: {url}')
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
        self.assertIn('EXPLAIN · VERIFIED LIVE', core)
        self.assertIn("explainTopic('network'", (FRONT / 'map.js').read_text())

    def test_badge_distinguishes_live_not_live_and_offline(self):
        core = (FRONT / 'core.js').read_text()
        for text in ("'Live'", "'Not live'", "'Offline'", 'setDegraded'):
            self.assertIn(text, core)
        self.assertIn('Console.setDegraded(!agents.data.live_available)', (FRONT / 'app.js').read_text())

    def test_health_chip_has_no_chip_when_health_is_null(self):
        app = (FRONT / 'app.js').read_text()
        self.assertIn('if (!health) return null;', app)
        for label in ("'Running'", "'Not ready'", "'Absent'"):
            self.assertIn(label, app)

    def test_stamp_rules(self):
        agents = (FRONT / 'agents.js').read_text()
        for text in ("c.failing ? 'FAILING'", "c.verified ? 'VERIFIED' : 'DECLARED'", "' live · '", "' declared'"):
            self.assertIn(text, agents)
        self.assertIn('explainStamp(agent, onb, e.currentTarget)', agents)  # the stamp opens Explain
        self.assertIn("'Failing: '", agents)  # the failing item is named

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

    def test_mrz_is_built_from_real_values_only(self):
        agents = (FRONT / 'agents.js').read_text()
        body = agents[agents.index('function mrz('):agents.index('const emblem')]
        for real in ('agent.name', 'agent.namespace', 'image_digests', 'budget_usd_month', 'counts', 'health'):
            self.assertIn(real, body)

    def test_onboard_has_eight_rows_states_and_the_rejected_example(self):
        onboard = (FRONT / 'onboard.js').read_text()
        for text in ('Verified', 'Declared', 'Failing', 'inferred', 'REJECTED', 'docs/examples/rejected-agent/', '/api/console/example', '$500 budget'):
            self.assertIn(text, onboard)

    def test_break_it_has_no_run_button_and_an_empty_state(self):
        attacks = (FRONT / 'attacks.js').read_text()
        self.assertNotIn('Run the attacks', attacks.replace("The run button comes in a later phase", ''))
        self.assertIn('No attack results yet.', attacks)
        self.assertIn('/api/console/attacks', attacks)

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

    def test_financial_ui_renders_only_the_steps_the_trace_says_happened(self):
        app = (FIN / 'app.js').read_text()
        for text in ('Checked who you are', 'Hid personal data from the model', 'Read only your own rows', 'Ignored orders hidden in the data',
                     'Matched the number to the data', 'trace.redaction.calls > 0', 'if (trace.data_access)', 'if (trace.injection_result)',
                     "trace.grounding_result === 'grounded'", 'Audit record →', 'Real login'.lower() and '/api/login'):
            self.assertIn(text, app)
        self.assertNotIn('language: UI', app)


if __name__ == '__main__':
    unittest.main()
