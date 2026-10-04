"""Real Presidio services for the eight-category bounded synthetic contract.

No NER coverage claim, model download, outbound request or request logging.
Startup role selects analyzer or anonymizer; callers cannot select a role.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from presidio_analyzer import (
    AnalyzerEngine,
    Pattern,
    PatternRecognizer,
    RecognizerRegistry,
)
from presidio_analyzer.nlp_engine import NoOpNlpEngine
from presidio_analyzer.predefined_recognizers import (
    CreditCardRecognizer,
    EmailRecognizer,
    IbanRecognizer,
    PhoneRecognizer,
)
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import RecognizerResult
import tldextract

ENTITIES = {
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "IBAN_CODE",
    "SAUDI_NATIONAL_ID",
    "SAUDI_RESIDENT_ID",
    "SAUDI_VAT_ID",
    "SAUDI_BANK_ACCOUNT",
}


class OfflineEmail(EmailRecognizer):
    # Same upstream recognition, supported no-fetch suffix validation.
    _extract = tldextract.TLDExtract(suffix_list_urls=())

    def validate_result(self, pattern_text):
        return bool(self._extract(pattern_text).fqdn)


def make_analyzer():
    registry = RecognizerRegistry(supported_languages=["en", "ar"])
    for language in ("en", "ar"):
        for recognizer in (
            OfflineEmail(supported_language=language),
            CreditCardRecognizer(supported_language=language),
            IbanRecognizer(supported_language=language),
            PhoneRecognizer(supported_language=language, supported_regions=["SA"]),
        ):
            registry.add_recognizer(recognizer)
        for entity, pattern in (
            ("SAUDI_NATIONAL_ID", r"\b[1١۱][0-9٠-٩۰-۹]{9}\b"),
            ("SAUDI_RESIDENT_ID", r"\b[2٢۲][0-9٠-٩۰-۹]{9}\b"),
            ("SAUDI_VAT_ID", r"\b[3٣۳][0-9٠-٩۰-۹]{13}[3٣۳]\b"),
            (
                "SAUDI_BANK_ACCOUNT",
                r"(?i)(?:(?<=bank account reference )|(?<=bank account: )|(?<=حساب مصرفي: ))[0-9٠-٩۰-۹]{10,18}\b",
            ),
        ):
            registry.add_recognizer(
                PatternRecognizer(
                    supported_entity=entity,
                    supported_language=language,
                    patterns=[Pattern(entity, pattern, 0.65)],
                )
            )
    nlp = NoOpNlpEngine(
        models=[{"lang_code": lang, "model_name": ""} for lang in ("en", "ar")]
    )
    nlp.load()
    return AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp,
        supported_languages=["en", "ar"],
        default_score_threshold=0.35,
    )


def serve(role, port=3000):
    if (
        role not in {"analyzer", "anonymizer"}
        or type(port) is not int
        or port not in {3000, 3001}
    ):
        raise ValueError("presidio:invalid_role")
    engine = make_analyzer() if role == "analyzer" else AnonymizerEngine()

    class Handler(BaseHTTPRequestHandler):
        server_version = "BoundedPresidio"
        sys_version = ""
        timeout = 4

        def log_message(self, *args):
            pass

        def respond(self, status, value):
            body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
            if len(body) > 65536:
                status, body = 500, b'{"error":"bounded_failure"}'
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.respond(200 if self.path == "/health" else 404, {"status": "ready"})

        def do_POST(self):
            try:
                size = self.headers.get_all("Content-Length", [])
                if (
                    len(size) != 1
                    or not size[0].isdigit()
                    or not 0 < int(size[0]) <= 32768
                    or self.headers.get("Transfer-Encoding")
                ):
                    raise ValueError
                value = json.loads(self.rfile.read(int(size[0])))
                if (
                    not isinstance(value, dict)
                    or type(value.get("text")) is not str
                    or not 0 < len(value["text"].encode()) <= 4096
                ):
                    raise ValueError
                if role == "analyzer":
                    if (
                        self.path != "/analyze"
                        or set(value) != {"text", "language"}
                        or value["language"] not in {"en", "ar"}
                    ):
                        raise ValueError
                    found = engine.analyze(
                        text=value["text"],
                        language=value["language"],
                        entities=sorted(ENTITIES),
                    )
                    output = [
                        {
                            k: getattr(item, k)
                            for k in ("entity_type", "start", "end", "score")
                        }
                        for item in found
                    ]
                else:
                    if (
                        self.path != "/anonymize"
                        or set(value) != {"text", "analyzer_results"}
                        or not isinstance(value["analyzer_results"], list)
                        or len(value["analyzer_results"]) > 64
                    ):
                        raise ValueError
                    findings = []
                    for item in value["analyzer_results"]:
                        if (
                            not isinstance(item, dict)
                            or set(item) != {"entity_type", "start", "end", "score"}
                            or item["entity_type"] not in ENTITIES
                            or type(item["start"]) is not int
                            or type(item["end"]) is not int
                            or not 0
                            <= item["start"]
                            < item["end"]
                            <= len(value["text"])
                            or type(item["score"]) not in {int, float}
                            or not 0 <= item["score"] <= 1
                        ):
                            raise ValueError
                        findings.append(RecognizerResult(**item))
                    output = {
                        "text": engine.anonymize(
                            text=value["text"], analyzer_results=findings
                        ).text
                    }
                self.respond(200, output)
            except Exception:
                self.respond(400, {"error": "bounded_failure"})

    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    if len(sys.argv) not in {2, 3}:
        raise SystemExit("presidio:role_required")
    serve(sys.argv[1], int(sys.argv[2]) if len(sys.argv) == 3 else 3000)
