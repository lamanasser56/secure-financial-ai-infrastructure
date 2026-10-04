"""Actual local signatures, server grants and existing conversation confinement.

No external issuer login, Google credentials or provider/detector qualification.
"""

import base64
import json
import time
import unittest
from unittest import mock

from runtime.agents.conversations import ConversationStore, ConversationRejected
from runtime.agents.credentials import (
    ScopedCredential,
    application_client_key,
    issuance_request,
)
from runtime.agents.demo import make_demo, prepare_gateway_core
from runtime.agents.core import AgentCore
from runtime.agents.identity import SubjectGrant, TrustedJWTIdentity
from runtime.phase3.adapters import (
    HttpLiteLLMGateway,
    PresidioRedactor,
    BilingualPresidioAnalyzer,
    HttpPresidioAnonymizer,
)
from runtime.phase3.trusted_runtime import ControlFailure, IdentityClaims, TenantContext

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from google.auth import crypt, jwt
except ImportError:
    crypt = None


@unittest.skipIf(crypt is None, "separate locked identity environment required")
class TrustedIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.signer = crypt.RSASigner.from_string(
            private.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        cls.public = (
            private.public_key()
            .public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )

    def setUp(self):
        self.now = int(time.time())
        self.identity = self.adapter()

    def adapter(self, profile="financial", **changes):
        values = dict(
            issuer="https://identity.example.invalid",
            audience="private-agent-fixture",
            certificates={"fixture-key": self.public},
            snapshot_expires_at=self.now + 600,
            subjects={
                "subject-alpha": SubjectGrant(
                    "fixture-a", frozenset({"financial", "infrastructure"})
                ),
                "subject-beta": SubjectGrant("fixture-b", frozenset({"financial"})),
            },
            tenant_reference_key=b"local-fixture-reference-key-only-32",
        )
        values.update(changes)
        return TrustedJWTIdentity(profile, **values)

    def token(self, **changes):
        values = dict(
            iss="https://identity.example.invalid",
            aud="private-agent-fixture",
            sub="subject-alpha",
            iat=self.now - 1,
            exp=self.now + 120,
        )
        values.update(changes)
        return (
            "Bearer " + jwt.encode(self.signer, values, key_id="fixture-key").decode()
        )

    def denied(self, token):
        with self.assertRaises(ControlFailure) as caught:
            self.identity.authenticate(token)
        self.assertEqual(str(caught.exception), "authentication:invalid_token")
        self.assertIsNone(caught.exception.__context__)

    def test_actual_signature_and_server_mapping_ignore_token_grants(self):
        claims = self.identity.authenticate(
            self.token(scopes=["diagnostics.ci"], tenant_id="other")
        )
        self.assertEqual(claims.tenant_claim, "fixture-a")
        self.assertNotIn("diagnostics.ci", claims.scopes)
        tenant = self.identity.resolve(claims)
        self.assertRegex(tenant.tenant_ref, "^[0-9a-f]{16}$")
        self.assertNotEqual(tenant.tenant_ref, tenant.tenant_id)
        self.assertTrue(self.identity.authorize(claims, tenant, "expenses.summary"))
        self.assertFalse(self.identity.authorize(claims, tenant, "diagnostics.ci"))

    def test_invalid_expired_future_wrong_issuer_audience_and_subject(self):
        for change in (
            {"exp": self.now - 2, "iat": self.now - 30},
            {"iat": self.now + 10},
            {"exp": self.now + 4000},
            {"iss": "https://attacker.invalid"},
            {"aud": "other"},
            {"aud": ["private-agent-fixture", "other"]},
            {"sub": "unknown"},
            {"nbf": self.now + 30},
            {"tenant": "fixture-b"},
            {"exp": True},
        ):
            with self.subTest(change=tuple(change)):
                self.denied(self.token(**change))

    def test_bad_signature_header_remote_key_and_oversized_token(self):
        token = self.token()
        self.denied(token[:-5] + "xxxxx")
        for header in (
            {"alg": "none", "kid": "fixture-key", "typ": "JWT"},
            {"alg": "HS256", "kid": "fixture-key", "typ": "JWT"},
            {"alg": "RS256", "kid": "unknown", "typ": "JWT"},
            {
                "alg": "RS256",
                "kid": "fixture-key",
                "typ": "JWT",
                "jku": "https://attacker.invalid",
            },
        ):
            encoded = (
                base64.urlsafe_b64encode(json.dumps(header).encode())
                .decode()
                .rstrip("=")
            )
            self.denied("Bearer " + encoded + "." + token[7:].split(".", 1)[1])
        self.denied("Bearer " + "x" * 8192)
        self.denied("Basic invalid")

    def test_duplicate_claims_rejected_before_verification(self):
        encoded = (
            base64.urlsafe_b64encode(b'{"sub":"subject-alpha","sub":"subject-beta"}')
            .decode()
            .rstrip("=")
        )
        segments = self.token()[7:].split(".")
        self.denied("Bearer " + ".".join([segments[0], encoded, segments[2]]))

    def test_stale_snapshot_and_profile_revocation_fail_closed(self):
        with mock.patch.object(self.identity, "_clock", return_value=self.now + 700):
            self.denied(self.token())
        with self.assertRaises(ControlFailure):
            self.adapter("infrastructure").authenticate(self.token(sub="subject-beta"))

    def test_forged_context_and_cross_tenant_authorization_denied(self):
        claims = self.identity.authenticate(self.token())
        self.assertFalse(
            self.identity.authorize(
                claims,
                TenantContext("fixture-b", "0123456789abcdef"),
                "expenses.summary",
            )
        )
        with self.assertRaises(ControlFailure):
            self.identity.resolve(
                IdentityClaims(claims.subject, "fixture-b", claims.scopes)
            )

    def test_operator_revocation_denies_tokens_and_previously_resolved_context(self):
        claims = self.identity.authenticate(self.token())
        tenant = self.identity.resolve(claims)
        self.identity.revoke_subject("subject-alpha")
        self.identity.revoke_subject("subject-alpha")  # Idempotent denial only.
        self.denied(self.token())
        self.assertFalse(self.identity.authorize(claims, tenant, "expenses.summary"))
        with self.assertRaises(ControlFailure):
            self.identity.resolve(claims)
        with self.assertRaises(ValueError):
            self.identity.revoke_subject("unknown")
        self.assertEqual(
            self.identity.authenticate(self.token(sub="subject-beta")).tenant_claim,
            "fixture-b",
        )

    def test_revocation_denies_existing_conversation_without_more_tools(self):
        core, _ = make_demo("financial")
        core.authenticator = core.resolver = core.authorizer = self.identity
        store = ConversationStore({"financial": (core, self.token())})
        session, _ = store.bootstrap()
        request = {
            "agent": "financial",
            "question": "Show expenses",
            "evidence_source": None,
            "language": "en",
            "conversation_id": None,
        }
        response = store.turn(session, request)
        request["conversation_id"] = response["conversation_id"]
        self.identity.revoke_subject("subject-alpha")
        with self.assertRaises(ControlFailure):
            store.turn(session, request)

    def test_existing_conversation_binding_rechecks_verified_subject(self):
        core, _ = make_demo("financial")
        core.authenticator = core.resolver = core.authorizer = self.identity
        agents = {"financial": (core, self.token())}
        store = ConversationStore(agents)
        token, _ = store.bootstrap()
        request = {
            "agent": "financial",
            "question": "Show expenses",
            "evidence_source": None,
            "language": "en",
            "conversation_id": None,
        }
        response = store.turn(token, request)
        request["conversation_id"] = response["conversation_id"]
        agents["financial"] = (core, self.token(sub="subject-beta"))
        with self.assertRaises(ConversationRejected):
            store.turn(token, request)

    def test_verified_identity_existing_orchestrator_and_actual_http_stub(self):
        from test_live_preparation import boundary_fixture, request

        with boundary_fixture() as (base, records):
            core = AgentCore(
                "financial",
                self.identity,
                self.identity,
                self.identity,
                PresidioRedactor(
                    BilingualPresidioAnalyzer(base + "/analyze", timeout=1),
                    HttpPresidioAnonymizer(base + "/anonymize", timeout=1),
                ),
                HttpLiteLLMGateway(
                    base, timeout=1, client_key="invalid-local-stub-client-key"
                ),
                simulation=False,
            )
            denied = core.run(self.token(aud="wrong"), request())
            self.assertEqual(denied["status"], "blocked")
            self.assertEqual(len(records), 0)
            result = core.run(self.token(), request())
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["tool_executions"], 2)
            self.assertEqual(result["facts"][0]["result"]["total_minor_units"], 24000)
            self.assertEqual(result["gateway_measurement"]["http_attempts"], 3)
            self.assertIsNone(result["gateway_measurement"]["provider_receipts"])
            self.assertIsNone(result["gateway_measurement"]["cost"])


class ClientCredentialTests(unittest.TestCase):
    def test_separate_startup_key_and_forbidden_admin_provider_environment(self):
        for forbidden in (
            "PORTFOLIO_LITELLM_MASTER_KEY",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "GEMINI_API_KEY",
        ):
            with mock.patch.dict(
                "os.environ",
                {
                    forbidden: "invalid",
                    "PORTFOLIO_LITELLM_FINANCIAL_CLIENT_KEY": "invalid-private-fixture-key",
                },
                clear=True,
            ):
                with self.assertRaises(ValueError):
                    application_client_key("financial")
        with mock.patch.dict(
            "os.environ",
            {"PORTFOLIO_LITELLM_CLIENT_KEY": "invalid-private-fixture-key"},
            clear=True,
        ):
            with self.assertRaises(ValueError):
                application_client_key("financial")

    def test_issuance_contract_has_exact_model_route_owner_and_limits(self):
        for profile in ("financial", "infrastructure"):
            value = issuance_request(profile, "nonadmin-fixture-owner")
            self.assertEqual(value["models"], ["secure-financial-chat"])
            self.assertEqual(value["allowed_routes"], ["/chat/completions"])
            self.assertEqual(value["duration"], "1h")
            self.assertEqual(value["metadata"]["agent_profile"], profile)
            self.assertNotIn("key", value)
        with self.assertRaises(ValueError):
            issuance_request("administrator", "owner")

    def test_expiry_revocation_rotation_and_private_representation(self):
        clock = mock.Mock(return_value=100)
        old = ScopedCredential("financial", "invalid-fixture-key-one", 200, clock=clock)
        self.assertNotIn("invalid", repr(old))
        with self.assertRaises(ValueError):
            old.value("infrastructure")
        replacement = ScopedCredential(
            "financial", "invalid-fixture-key-two", 200, clock=clock
        )
        new = old.rotate(replacement)
        with self.assertRaises(ValueError):
            old.value("financial")
        self.assertEqual(new.value("financial"), "invalid-fixture-key-two")
        clock.return_value = 200
        with self.assertRaises(ValueError):
            new.value("financial")
        new.revoke()

    def test_explicit_client_key_has_no_ambient_fallback(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            gateway = HttpLiteLLMGateway(
                "http://127.0.0.1:1", client_key="invalid-private-fixture-key"
            )
        self.assertEqual(gateway.measurement_snapshot()["http_attempts"], 0)
