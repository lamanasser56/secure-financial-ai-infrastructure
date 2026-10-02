"""Static gate for the reference-only SQL and optional disposable DB check."""

from pathlib import Path
import os
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "database/reference/migrations"


class ReferenceRLSTests(unittest.TestCase):
    def test_reference_schema_has_forced_command_specific_rls(self):
        schema = (MIGRATIONS / "001_tenant_schema.sql").read_text()
        policies = (MIGRATIONS / "002_documents_rls.sql").read_text()
        self.assertIn("CREATE SCHEMA portfolio_ref", schema)
        self.assertIn("tenant_id uuid NOT NULL", schema)
        self.assertIn("ENABLE ROW LEVEL SECURITY", policies)
        self.assertIn("FORCE ROW LEVEL SECURITY", policies)
        for operation in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            self.assertIn(f"FOR {operation}", policies)
        self.assertIn("current_setting('portfolio_ref.tenant_id', true)", policies)

    def test_disposable_database_behavior(self):
        url = os.environ.get("PORTFOLIO_TEST_DATABASE_URL")
        if not url or not shutil.which("psql"):
            self.skipTest("disposable PostgreSQL URL and psql not available")
        result = subprocess.run(
            ["bash", "scripts/test-reference-rls.sh"], cwd=ROOT,
            text=True, capture_output=True, check=False,
            env={**os.environ, "PORTFOLIO_TEST_DATABASE_URL": url},
        )
        self.assertEqual(result.returncode, 0, result.stderr[-1000:])


if __name__ == "__main__":
    unittest.main()
