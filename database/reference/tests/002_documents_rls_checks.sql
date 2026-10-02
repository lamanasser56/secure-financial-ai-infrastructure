BEGIN TRANSACTION READ ONLY;

WITH checks (check_name, passed) AS (
  VALUES
    (
      'documents RLS is enabled',
      COALESCE(
        (
          SELECT relrowsecurity
          FROM pg_class
          WHERE oid = to_regclass('portfolio_ref.documents')
        ),
        false
      )
    ),
    (
      'documents FORCE RLS is enabled',
      COALESCE(
        (
          SELECT relforcerowsecurity
          FROM pg_class
          WHERE oid = to_regclass('portfolio_ref.documents')
        ),
        false
      )
    ),
    (
      'documents has exactly four policies',
      (
        SELECT count(*) = 4
        FROM pg_policy
        WHERE polrelid = to_regclass('portfolio_ref.documents')
      )
    ),
    (
      'documents policies cover SELECT INSERT UPDATE DELETE',
      (
        SELECT array_agg(polcmd ORDER BY polcmd) = ARRAY['a', 'd', 'r', 'w']::"char"[]
        FROM pg_policy
        WHERE polrelid = to_regclass('portfolio_ref.documents')
      )
    ),
    (
      'documents policies are permissive',
      NOT EXISTS (
        SELECT 1
        FROM pg_policy
        WHERE polrelid = to_regclass('portfolio_ref.documents')
          AND NOT polpermissive
      )
    ),
    (
      'documents policies apply only to PUBLIC scope',
      NOT EXISTS (
        SELECT 1
        FROM pg_policy
        WHERE polrelid = to_regclass('portfolio_ref.documents')
          AND polroles <> ARRAY[0::oid]
      )
    )
)
SELECT check_name, passed
FROM checks
ORDER BY check_name;

ROLLBACK;
