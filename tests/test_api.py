import pytest
from fastapi.testclient import TestClient

from backend.main import app, state


@pytest.fixture
def client():
    previous_started = state.started
    state.started = True  # Keep tests from starting the file-monitor background task.
    state.rate_history.clear()
    state.rate_history.extend([
        {"timestamp": "2026-09-28T12:00:00+00:00", "error_rate": 0.05},
        {"timestamp": "2026-09-28T12:00:01+00:00", "error_rate": 0.70},
    ])
    state.system_status = "anomaly"

    with TestClient(app) as test_client:
        yield test_client

    state.started = previous_started
    state.rate_history.clear()
    state.system_status = "learning"


def test_health_endpoint_returns_required_payload(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_endpoint_includes_live_state(client):
    response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json()["system_status"] == "anomaly"
    assert response.json()["active_alerts"] == 1


def test_metrics_endpoint_returns_recent_time_series(client):
    response = client.get("/api/metrics")

    assert response.status_code == 200
    assert [point["error_rate"] for point in response.json()] == [0.05, 0.70]
