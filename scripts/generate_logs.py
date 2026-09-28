import argparse
import random
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "app.log"
NORMAL_ERROR_RATE = 0.08
CRITICAL_ERROR_RATE = 0.72
CRITICAL_WARMUP_EVENTS = 30

SERVICES = ["auth-service", "payment-service", "api-gateway", "user-service"]
NORMAL_MESSAGES = [
    "request completed successfully",
    "GET /api/users 200",
    "token validated",
    "database query completed",
]
ERROR_MESSAGES = [
    "database connection timeout",
    "upstream service unavailable",
    "authentication failed",
    "request processing timeout",
]


def error_probability(scenario: str, tick: int) -> float:
    if scenario == "normal":
        return NORMAL_ERROR_RATE
    if scenario == "critical":
        return NORMAL_ERROR_RATE if tick < CRITICAL_WARMUP_EVENTS else CRITICAL_ERROR_RATE

    # Preserve the original repeating demo when the scenario is "cycle".
    in_burst = 75 <= (tick % 110) <= 94
    return CRITICAL_ERROR_RATE if in_burst else NORMAL_ERROR_RATE


def generate_logs(scenario: str, interval: float = 0.5):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.touch(exist_ok=True)

    if scenario == "critical":
        print(f"Writing normal warm-up, then a critical error burst, to {LOG}")
    else:
        print(f"Writing {scenario} demo logs to {LOG}")

    tick = 0
    while True:
        is_error = random.random() < error_probability(scenario, tick)
        level = "ERROR" if is_error else "INFO"
        service = random.choice(SERVICES)
        message = random.choice(ERROR_MESSAGES if is_error else NORMAL_MESSAGES)
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {level} {service} {message}\n"

        with LOG.open("a", encoding="utf-8") as log_file:
            log_file.write(line)
            log_file.flush()

        tick += 1
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="Append demo events to data/app.log")
    parser.add_argument(
        "--scenario",
        choices=("normal", "critical", "cycle"),
        default="cycle",
        help="normal traffic, a warmed-up critical burst, or the repeating original demo",
    )
    args = parser.parse_args()
    generate_logs(args.scenario)


if __name__ == "__main__":
    main()
