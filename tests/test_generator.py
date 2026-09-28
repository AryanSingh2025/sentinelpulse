from scripts.generate_logs import (
    CRITICAL_ERROR_RATE,
    CRITICAL_WARMUP_EVENTS,
    NORMAL_ERROR_RATE,
    error_probability,
)


def test_normal_scenario_stays_at_normal_error_rate():
    assert error_probability("normal", 0) == NORMAL_ERROR_RATE
    assert error_probability("normal", 100) == NORMAL_ERROR_RATE


def test_critical_scenario_warms_up_before_the_burst():
    assert error_probability("critical", 0) == NORMAL_ERROR_RATE
    assert error_probability("critical", CRITICAL_WARMUP_EVENTS - 1) == NORMAL_ERROR_RATE
    assert error_probability("critical", CRITICAL_WARMUP_EVENTS) == CRITICAL_ERROR_RATE


def test_cycle_scenario_preserves_the_repeating_burst():
    assert error_probability("cycle", 0) == NORMAL_ERROR_RATE
    assert error_probability("cycle", 75) == CRITICAL_ERROR_RATE
