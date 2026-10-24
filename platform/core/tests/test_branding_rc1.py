"""Public display contracts; resource/package/repository identities are deliberately stable."""
from html.parser import HTMLParser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__();self.in_title=False;self.title='';self.text=[];self.feed(text)
    def handle_starttag(self, tag, attrs):
        if tag == 'title':self.in_title=True
    def handle_endtag(self, tag):
        if tag == 'title':self.in_title=False
    def handle_data(self, data):
        self.text.append(data)
        if self.in_title:self.title+=data


class BrandingRC1(unittest.TestCase):
    def test_every_current_browser_shell_has_parent_brand_and_subtitle(self):
        for path in ('platform/core/ui/index.html','platform/agents/financial/finance_agent/ui/index.html',
                     'platform/agents/platform-guide/public/index.html'):
            with self.subTest(path=path):
                page=Page((ROOT/path).read_text())
                self.assertIn('Agent Runtime Platform',page.title)
                self.assertIn('Agent Runtime Platform',' '.join(page.text))
                self.assertIn('Infrastructure · Security · Operations',' '.join(page.text))
                self.assertNotIn('Agent-Platform',' '.join(page.text))

    def test_dynamic_titles_and_agent_passports_use_current_brand(self):
        self.assertIn(' · Agent Runtime Platform',(ROOT/'platform/core/ui/app.js').read_text())
        self.assertIn('AGENT RUNTIME PLATFORM',(ROOT/'platform/core/ui/agents.js').read_text())

    def test_example_names_and_repository_links_are_preserved(self):
        self.assertIn('Financial Agent',(ROOT/'platform/agents/financial/finance_agent/ui/index.html').read_text())
        self.assertIn('Platform Guide',(ROOT/'platform/agents/platform-guide/public/index.html').read_text())
        self.assertIn('secure-financial-ai-infrastructure/blob/main/',(ROOT/'platform/core/ui/core.js').read_text())


class WorkflowBrandingDependencies(unittest.TestCase):
    def test_release_trigger_tracks_renamed_ci_without_changing_signer_path(self):
        import yaml
        ci=yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text())
        raw=(ROOT/'.github/workflows/agent-platform-images.yml').read_text()
        workflow=yaml.safe_load(raw)
        trigger=workflow.get('on',workflow.get(True))
        self.assertEqual(trigger['workflow_run']['workflows'],[ci['name']])
        self.assertIn('/.github/workflows/agent-platform-images.yml@refs/heads/main',raw)
        self.assertEqual(set(ci['jobs']),{'checks','agents','google-sdp-offline-evaluation','gitleaks'})
