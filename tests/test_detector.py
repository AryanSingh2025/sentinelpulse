from backend.main import build_alert, classify_severity


def test_severity_thresholds():
    assert classify_severity(2.4, 0.1, 0.05) == "LOW"
    assert classify_severity(2.5, 0.1, 0.05) == "MEDIUM"
    assert classify_severity(3.0, 0.1, 0.05) == "HIGH"
    assert classify_severity(4.0, 0.1, 0.05) == "CRITICAL"


def test_zero_standard_deviation_produces_finite_critical_alert():
    alert = build_alert(
        rate=0.70,
        mean=0.05,
        std=0.0,
        event={"service": "payment-service", "message": "Database timeout"},
    )

    assert alert["severity"] == "CRITICAL"
    assert alert["z_score"] == 10.0
    assert alert["service"] == "payment-service"
