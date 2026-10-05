"""Unwired transaction contract using the existing reference documents schema."""

from uuid import UUID

from runtime.phase3.trusted_runtime import ControlFailure, IdentityClaims


def read_document_integrity(connection, claims, *, identity, document_id, tenant_directory):
    """Trusted server maps authenticated identity to DB UUID; no request tenant.

    The supplied connection must be an exclusively leased, nonowner, read-only
    role with NOBYPASSRLS and verified FORCE RLS. This candidate does not acquire
    connections or prove those deployment facts. Always rollback before release.
    Existing demo expense tools remain unchanged; no invented financial DB table.
    """
    try:
        if not isinstance(claims, IdentityClaims):
            raise ValueError
        tenant_context = identity.resolve(claims)
        if not identity.authorize(claims, tenant_context, "documents.read"):
            raise ValueError
        tenant = str(UUID(tenant_directory[tenant_context.tenant_id]))
        identifier = str(UUID(document_id))
    except Exception:
        raise ControlFailure("authorization", "denied") from None
    try:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN READ ONLY")
            cursor.execute("SELECT pg_catalog.set_config('portfolio_ref.tenant_id', %s, true)",
                           (tenant,))
            cursor.execute(
                "SELECT sha256_digest FROM portfolio_ref.documents "
                "WHERE tenant_id = %s::uuid AND id = %s::uuid LIMIT 2", (tenant, identifier))
            rows = cursor.fetchall()
            if len(rows) != 1 or len(rows[0]) != 1:
                raise ValueError
            digest = rows[0][0]
            if (type(digest) is not str or len(digest) != 64
                    or any(c not in "0123456789abcdef" for c in digest)):
                raise ValueError
        return digest
    except Exception:
        raise ControlFailure("authorization", "denied") from None
    finally:
        try:
            connection.rollback()
        except Exception:
            # Caller must discard this lease; no result is returned on failure.
            raise ControlFailure("authorization", "denied") from None
