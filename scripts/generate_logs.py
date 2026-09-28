import random
import time
from datetime import datetime

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "app.log"
LOG.parent.mkdir(exist_ok=True)
LOG.touch(exist_ok=True)

services = ["auth-service", "payment-service", "api-gateway", "user-service"]
normal_messages = [
    "request completed successfully",
    "GET /api/users 200",
    "token validated",
    "database query completed",
]
error_messages = [
    "database connection timeout",
    "upstream service unavailable",
    "authentication failed",
    "request processing timeout",
]

# First phase is normal so the detector can learn a baseline. Then a burst is injected.
tick = 0
print(f"Writing demo logs to {LOG}")

while True:
    burst = 75 <= (tick % 110) <= 94
    is_error = random.random() < (0.72 if burst else 0.08)
    level = "ERROR" if is_error else "INFO"
    service = random.choice(services)
    message = random.choice(error_messages if is_error else normal_messages)

    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {level} {service} {message}\n"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)
        f.flush()

    tick += 1
    time.sleep(0.5)
