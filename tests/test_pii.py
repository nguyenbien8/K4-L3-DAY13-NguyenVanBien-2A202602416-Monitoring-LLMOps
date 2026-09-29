from app.pii import scrub_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_cccd() -> None:
    out = scrub_text("CCCD cua toi la 001099012345")
    assert "001099012345" not in out
    assert "REDACTED_CCCD" in out


def test_scrub_credit_card_formats() -> None:
    for card in ("4111 1111 1111 1111", "4111-1111-1111-1111", "4111111111111111"):
        out = scrub_text(f"Card {card} please")
        assert card not in out
        assert "REDACTED_CREDIT_CARD" in out
        assert "REDACTED_PHONE_VN" not in out


def test_scrub_passport() -> None:
    out = scrub_text("Passport B1234567")
    assert "B1234567" not in out
    assert "REDACTED_PASSPORT_VN" in out


def test_scrub_keeps_safe_ids() -> None:
    text = "correlation req-1a2b3c4d latency 1692 ms"
    assert scrub_text(text) == text


def test_scrub_event_processor_scrubs_nested_fields() -> None:
    from app.logging_config import scrub_event

    event = {
        "event": "request_failed",
        "payload": {
            "detail": "user student@vinuni.edu.vn",
            "nested": {"phone": "0987654321"},
            "items": ["4111 1111 1111 1111"],
        },
        "exception": "ValueError: CCCD 001099012345",
        "latency_ms": 120,
    }
    out = scrub_event(None, "info", event)
    raw = str(out)
    for secret in ("student@vinuni.edu.vn", "0987654321", "4111 1111 1111 1111", "001099012345"):
        assert secret not in raw
    assert out["latency_ms"] == 120
