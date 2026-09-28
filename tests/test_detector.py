import asyncio

from backend import main
from backend.main import build_alert, classify_severity, recommend_action


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


def test_sliding_window_error_rate_updates_as_old_events_drop():
    state = main.MonitorState()
    state.events.extend({"is_error": False} for _ in range(main.WINDOW_SIZE - 1))
    state.events.append({"is_error": True})
    assert state.current_rate == 1 / main.WINDOW_SIZE

    state.events.append({"is_error": True})
    assert state.current_rate == 2 / main.WINDOW_SIZE


def test_recommendations_follow_the_error_message():
    assert "database connectivity" in recommend_action("Database connection timeout").lower()
    assert "authentication failures" in recommend_action("Unauthorized token").lower()
    assert "memory usage" in recommend_action("Out of memory").lower()
    assert "service logs" in recommend_action("Unexpected failure").lower()


def test_sns_skips_medium_alerts_even_when_configured(monkeypatch):
    monkeypatch.setattr(main, "SNS_TOPIC_ARN", "arn:aws:sns:region:account:topic")

    result = main.publish_sns({"severity": "MEDIUM"})

    assert result["sent"] is False
    assert "HIGH and CRITICAL" in result["reason"]


def test_sns_without_topic_configuration_does_not_raise(monkeypatch):
    monkeypatch.setattr(main, "SNS_TOPIC_ARN", "")

    result = main.publish_sns({"severity": "CRITICAL"})

    assert result == {"sent": False, "reason": "AWS_SNS_TOPIC_ARN not configured"}


def test_continuous_anomaly_creates_only_one_alert():
    state = main.state
    state.events.clear()
    state.events.extend({"is_error": False} for _ in range(main.WINDOW_SIZE - 1))
    state.baseline_rates[:] = [0.0] * main.BASELINE_WINDOWS
    baseline_before_anomaly = state.baseline_rates.copy()
    state.alerts.clear()
    state.rate_history.clear()
    state.clients.clear()
    state.total_events = 0
    state.total_errors = 0
    state.anomaly_active = False
    state.system_status = "normal"

    async def add_consecutive_errors():
        for _ in range(3):
            await main.process_event({
                "timestamp": "2026-09-28T12:00:00+00:00",
                "level": "ERROR",
                "service": "payment-service",
                "message": "Database connection timeout",
            })

    asyncio.run(add_consecutive_errors())

    assert len(state.alerts) == 1
    assert state.anomaly_active is True
    assert state.baseline_rates == baseline_before_anomaly
