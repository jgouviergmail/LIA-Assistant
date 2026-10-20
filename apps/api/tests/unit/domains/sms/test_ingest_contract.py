"""SMS validation/filter/index contracts exercised before any persistence exists."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.sms.schemas import SmsIngestItem
from src.domains.sms.search import blind_terms, tokenize
from src.domains.sms.sender_policy import normalize_sender
from src.domains.sms.sensitive_filter import contains_access_secret

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "body",
    [
        "Votre code de connexion est 123456. Ne le communiquez jamais.",
        "Your verification code: 123-456",
        "OTP: 839201",
        "Code de récupération : abcd-efgh-ijkl",
        "Your password is: NotForStorage!",
        "Votre mot de passe temporaire : Abcd1234!",
        "Einmalpasswort: 987654",
        "Tu código de verificación es 123456",
        "Il tuo codice di accesso è 123456",
        "验证码：123456，请勿泄露",
        "Sign in with this link https://example.test/login?token=private-value",
        "Réinitialisez votre mot de passe https://example.test/reset/very-secret",
    ],
)
def test_access_secrets_are_excluded(body: str) -> None:
    assert contains_access_secret(body)


@pytest.mark.parametrize(
    "body",
    [
        "RDV médical demain à 14h",
        "Virement de 123456 euros reçu.",
        "Le code postal est 75001",
        "Le mot de passe est à changer régulièrement.",
        "Your bank balance is 123456",
        "Your package 839201 is ready.",
        "Bonjour 👋\nVoici les nouvelles de la famille.",
        "明天下午见面。",
    ],
)
def test_personal_content_without_access_secrets_is_retained(body: str) -> None:
    assert not contains_access_secret(body)


def test_message_date_is_aware_normalized_and_literal_body_is_preserved() -> None:
    body = "  Bonjour 👋\nhttps://example.test  "
    item = SmsIngestItem(sender="Alice", date="2026-01-02T13:00:00+01:00", body=body, o="iphone")
    assert item.date == datetime(2026, 1, 2, 12, tzinfo=UTC)
    assert item.body == body
    assert item.date_kind == "unknown"


@pytest.mark.parametrize(
    "field,value",
    [
        ("sender", ""),
        ("sender", "a" * 257),
        ("body", ""),
        ("body", "a" * 16001),
        ("body", 42),
        ("date", "2026-01-02T12:00:00"),
        ("date", 123456),
        pytest.param(
            "date", (datetime.now(UTC) + timedelta(days=1)).isoformat(), id="date-too-far-future"
        ),
        ("o", "a" * 33),
        ("schema_version", 2),
        ("schema_version", True),
    ],
)
def test_invalid_messages_are_rejected(field: str, value: object) -> None:
    payload = {"sender": "Alice", "date": "2026-01-02T12:00:00Z", "body": "Salut", "o": "iphone"}
    with pytest.raises(ValidationError):
        SmsIngestItem.model_validate({**payload, field: value})


def test_sender_equivalence_does_not_guess_a_country_or_fuzzy_match_names() -> None:
    assert normalize_sender("+33 (0)6 12 34 56 78") != normalize_sender("0612345678")
    assert normalize_sender("+33 6 12 34 56 78") == normalize_sender("+33612345678")
    assert normalize_sender("Alice Martin") != normalize_sender("Alice")
    assert normalize_sender("ALICE") == normalize_sender("Alice")


def test_lexical_index_is_tenant_scoped_and_queries_share_normalization() -> None:
    a, b = uuid4(), uuid4()
    assert tokenize("CAFÉ, café! 東京 🐈") == tokenize("café 東京")
    assert blind_terms(a, "Café demain", key=b"t" * 32) == blind_terms(
        a, "demain CAFÉ", key=b"t" * 32
    )
    assert not set(blind_terms(a, "Café", key=b"t" * 32)) & set(
        blind_terms(b, "Café", key=b"t" * 32)
    )
    assert "café" not in str(blind_terms(a, "Café", key=b"t" * 32))


@pytest.mark.parametrize(
    "body",
    [
        "Your temporary password is Abcd1234!",
        "Votre mot de passe est XyZ123456!",
        "https://example.test/login?token=private-value Cliquez pour continuer",
        "Code de récupération : ABCD-EFGH-IJKL",
    ],
)
def test_identifiable_access_secrets_do_not_depend_on_colon_or_link_position(body: str) -> None:
    assert contains_access_secret(body)


@pytest.mark.parametrize(
    "body",
    [
        "OTP: 123\u200b456",
        "Your verification code is AB7C4Q",
        "Votre code est 123456",
        "验证码：123\n456",
    ],
)
def test_common_otp_formatting_cannot_escape_the_filter(body: str) -> None:
    assert contains_access_secret(body)


@pytest.mark.parametrize(
    "body",
    [
        "Never share your verification code with anyone.",
        "Your password is important.",
        "Le code postal de votre agence est 75001.",
    ],
)
def test_security_advice_and_postal_information_are_not_access_secrets(body: str) -> None:
    assert not contains_access_secret(body)


def test_missing_origin_is_not_silently_invented_as_iphone() -> None:
    with pytest.raises(ValidationError):
        SmsIngestItem.model_validate(
            {"sender": "Alice", "date": "2026-01-02T12:00:00Z", "body": "Salut"}
        )
