"""Static invariants of the redesigned UI (no JS engine offline; the live screenshots cover behaviour).

Front door: platform/core/ui (About, Security & Operations; served by the hash-bound runtime/agents/web.py, which
allows six fixed paths of at most 32 KB each). Financial Agent: platform/agents/financial/finance_agent/ui.
"""
from pathlib import Path
import re
import unittest

REPO = Path(__file__).resolve().parents[3]
FRONT = REPO / 'platform/core/ui'
FIN = REPO / 'platform/agents/financial/finance_agent/ui'
SERVED = ('index.html', 'app.js', 'style.css', 'operations.html', 'operations.js')
PROPER = {'LiteLLM', 'Google SDP', 'fault-demo'}  # tool names stay as written in both languages


def dictionaries(script):
    """{'en': {key: value}, 'ar': {...}} from the Object.assign(UI.dict.xx, {...}) blocks."""
    out = {'en': {}, 'ar': {}}
    for lang, body in re.findall(r"Object\.assign\(UI\.dict\.(en|ar), \{\n(.*?)\n\}\);", script, re.S):
        for key, value in re.findall(r"(?:'([\w:]+)'|(?<![\w'])(\w+)): (?:'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\")", body) and \
                [(k1 or k2, v1 or v2) for k1, k2, v1, v2 in re.findall(r"(?:'([\w:]+)'|(?<![\w'])(\w+)): (?:'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\")", body)]:
            out[lang][key] = value
    return out


class UiAssets(unittest.TestCase):
    def pages(self):
        return ((FRONT / 'index.html', FRONT / 'app.js'), (FRONT / 'operations.html', FRONT / 'app.js', FRONT / 'operations.js'),
                (FIN / 'index.html', FIN / 'app.js'))

    def test_front_door_paths_fit_the_server_limit(self):
        for name in SERVED:
            with self.subTest(name=name):
                self.assertLessEqual(len((FRONT / name).read_bytes()), 32768)
        self.assertEqual(sorted(p.name for p in FRONT.iterdir()), sorted(SERVED))  # no file the server cannot serve

    def test_no_inner_html_and_balanced_scripts(self):
        for script in (FRONT / 'app.js', FRONT / 'operations.js', FIN / 'app.js'):
            text = script.read_text()
            with self.subTest(script=str(script.relative_to(REPO))):
                self.assertNotIn('innerHTML', text)
                self.assertNotIn('eval(', text)
                for open_, close in ('()', '[]', '{}'):
                    self.assertEqual(text.count(open_), text.count(close), open_ + close)

    def test_no_inline_script_or_style_or_image(self):  # CSP: script-src 'self'; style-src 'self'; img-src 'none'
        for html in (FRONT / 'index.html', FRONT / 'operations.html', FIN / 'index.html'):
            text = html.read_text()
            with self.subTest(html=html.name):
                self.assertNotIn('style=', text)
                self.assertNotIn('<img', text)
                self.assertNotRegex(text, r'<script(?![^>]*\bsrc=)')
                self.assertRegex(text, r'data-lang="ar"')

    def test_every_key_exists_in_both_languages(self):
        for files in self.pages():
            scripts = ''.join(f.read_text() for f in files if f.suffix == '.js')
            html = files[0].read_text()
            d = dictionaries(scripts)
            used = set(re.findall(r'data-t(?:-aria|-ph)?="([\w:]+)"', html)) | set(re.findall(r"\bt\('([\w:]+)'\)", scripts))
            used |= set(re.findall(r"(?:title|body): '(tour_\w+)'", scripts))
            with self.subTest(page=files[0].relative_to(REPO).as_posix()):
                self.assertTrue(d['en'] and d['ar'])
                self.assertEqual(set(d['en']), set(d['ar']), 'EN and AR keys differ')
                self.assertEqual(used - set(d['en']), set(), 'keys used but not translated')

    def test_arabic_labels_are_arabic_with_western_digits(self):
        for files in self.pages():
            d = dictionaries(''.join(f.read_text() for f in files if f.suffix == '.js'))
            for key, value in d['ar'].items():
                with self.subTest(key=key):
                    self.assertNotRegex(value, '[٠-٩۰-۹]')  # Western digits 0-9 only
                    if value not in PROPER and key not in ('t_gateway', 't_redactor', 't_fault'):
                        self.assertRegex(value, '[؀-ۿ]', 'untranslated Arabic label')

    def test_arabic_dates_and_numbers_use_western_digits_and_gregorian_calendar(self):
        core = (FRONT / 'app.js').read_text()
        self.assertIn("'ar-u-nu-latn-ca-gregory'", core)
        self.assertIn('const latin = s =>', core)  # model text with Arabic-Indic digits is shown with 0-9
        self.assertIn("lang === 'ar' ? 'rtl' : 'ltr'", core)
        self.assertIn("el('bdi', {dir: 'ltr'}", core)  # technical IDs isolated left-to-right
        for script in (FRONT / 'app.js', FRONT / 'operations.js', FIN / 'app.js'):  # web.py serves exact paths only
            self.assertNotIn('location.search', script.read_text())
            self.assertNotIn("'?lang=", script.read_text())

    def test_financial_page_shares_the_core_and_the_design(self):
        front, fin = (FRONT / 'app.js').read_text(), (FIN / 'app.js').read_text()
        core = front[front.index('const UI_PARAMS'):front.index('\n})();\n') + 6]
        self.assertIn(core, fin)
        self.assertEqual((FRONT / 'style.css').read_bytes(), (FIN / 'style.css').read_bytes())

    def test_operations_page_content(self):
        script = (FRONT / 'operations.js').read_text() + (FRONT / 'app.js').read_text()
        html = (FRONT / 'operations.html').read_text()
        self.assertNotIn('rollback', script.lower())
        for text in ('No pending approvals.', 'لا توجد موافقات معلّقة.',
                     'No policy denials yet — denials appear here when a request breaks a rule.',
                     'لا توجد حالات رفض بعد — تظهر هنا عندما يخالف طلبٌ إحدى القواعد.',
                     'AI explanation — for information only, it cannot change the action',
                     'شرح الذكاء الاصطناعي — للعلم فقط، ولا يغيّر الإجراء',
                     'Your approval is valid once, for this action on this service, for 5 minutes.',
                     'RAISE_MEMORY_LIMIT_OR_FIX_WORKLOAD', 'DEPLOY_VALID_SIGNED_DIGEST', 'DEPLOY_ATTESTED_IMAGE'):
            self.assertIn(text, script + html)
        for element in ('board', 'incident', 'tracker', 'pending', 'timeline', 'denials', 'checklist', 'owner-action'):
            self.assertIn('id="' + element + '"', html)
        # service names are "role · tool" in both languages
        self.assertIn("t('n_' + k) + ' · ' + t('t_' + k)", script)
        for stale in ('operator-approval.secret', 'live mode is disabled', 'ACTION_FAILED'):
            self.assertNotIn(stale, script + html)

    def test_tour_and_about_view(self):
        about = (FRONT / 'index.html').read_text()
        for section in ('agents', 'answer-path', 'ops-loop', 'controls'):
            self.assertIn('id="' + section + '"', about)
        for files in self.pages():
            scripts = ''.join(f.read_text() for f in files if f.suffix == '.js')
            self.assertIn('UI.start([', scripts)
            self.assertIn('id="tour"', files[0].read_text())
        core = (FRONT / 'app.js').read_text()
        self.assertIn('catch (e) { /* storage blocked: the page still works */ }', core)


if __name__ == '__main__':
    unittest.main()
