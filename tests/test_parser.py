from backend.main import parse_line


def test_parse_standard_log_line():
    event = parse_line(
        "2026-09-28 12:00:02 ERROR payment-service Database connection timeout"
    )

    assert event == {
        "timestamp": "2026-09-28 12:00:02",
        "level": "ERROR",
        "service": "payment-service",
        "message": "Database connection timeout",
    }


def test_parse_fallback_log_line():
    event = parse_line("auth-service error token validation failed")

    assert event["level"] == "ERROR"
    assert event["service"] == "auth-service"
    assert event["message"] == "token validation failed"
    assert event["timestamp"]


def test_blank_or_unusable_lines_are_ignored():
    assert parse_line("") is None
    assert parse_line("malformed") is None
