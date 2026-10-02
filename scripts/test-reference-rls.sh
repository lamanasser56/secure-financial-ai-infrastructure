#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

: "${PORTFOLIO_TEST_DATABASE_URL:?set a disposable PostgreSQL URL for portfolio_rls_test}"
actual_db="$(psql "$PORTFOLIO_TEST_DATABASE_URL" --no-psqlrc --tuples-only --no-align --command 'SELECT current_database()')"
[[ "$actual_db" == 'portfolio_rls_test' ]] || {
  echo 'refusing to run outside portfolio_rls_test' >&2
  exit 2
}
# This dedicated database is disposable. Reset only the reference fixture so
# repeated qualification runs exercise the forward-only migrations from zero.
psql "$PORTFOLIO_TEST_DATABASE_URL" --no-psqlrc --set=ON_ERROR_STOP=1 \
  --command 'DROP SCHEMA IF EXISTS portfolio_ref CASCADE' >/dev/null
for file in \
  database/reference/migrations/001_tenant_schema.sql \
  database/reference/migrations/002_documents_rls.sql \
  database/reference/tests/001_tenant_schema_checks.sql \
  database/reference/tests/002_documents_rls_checks.sql \
  database/reference/tests/002_documents_rls_behavior.sql; do
  psql "$PORTFOLIO_TEST_DATABASE_URL" --no-psqlrc --set=ON_ERROR_STOP=1 --file="$file" >/dev/null
done
echo 'Reference-only PostgreSQL RLS checks passed'
