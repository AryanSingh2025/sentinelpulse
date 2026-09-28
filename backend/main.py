import asyncio
import json
import math
import os
import re
import statistics
from collections import deque
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent.parent
load_dotenv(BASE / "backend" / ".env")

LOG_FILE = Path(os.getenv("LOG_FILE", str(BASE / "data" / "app.log"))).resolve()
WINDOW_SIZE = int(os.getenv("WINDOW_SIZE", "20"))
BASELINE_WINDOWS = int(os.getenv("BASELINE_WINDOWS", "5"))
Z_THRESHOLD = float(os.getenv("Z_THRESHOLD", "2.5"))
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
SNS_TOPIC_ARN = os.getenv("AWS_SNS_TOPIC_ARN", "")

LOG_RE = re.compile(
    r"^(?P<ts>\S+\s+\S+)\s+(?P<level>[A-Z]+)\s+(?P<service>\S+)\s+(?P<message>.*)$"
)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    monitor_task = None
    if not state.started:
        state.started = True
        monitor_task = asyncio.create_task(monitor_file())

    try:
        yield
    finally:
        if monitor_task is not None:
            monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await monitor_task
            state.started = False


app = FastAPI(title="SentinelPulse Log Anomaly Detector", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LogFileCursor:
    """Track complete appended lines and reset when the file is replaced or truncated."""

    def __init__(self):
        self.position = 0
        self.identity = None
        self.pending_line = ""

    def read_new_lines(self, path: Path) -> list[str]:
        path = Path(path)
        file_stat = path.stat()
        identity = (file_stat.st_dev, file_stat.st_ino)

        was_replaced = self.identity is not None and identity != self.identity
        was_truncated = file_stat.st_size < self.position
        if was_replaced or was_truncated:
            self.position = 0
            self.pending_line = ""

        self.identity = identity
        if file_stat.st_size <= self.position:
            return []

        with path.open("r", encoding="utf-8", errors="replace", newline="") as log_file:
            log_file.seek(self.position)
            appended_text = log_file.read()
            self.position = log_file.tell()

        pieces = (self.pending_line + appended_text).splitlines(keepends=True)
        self.pending_line = ""
        if pieces and not pieces[-1].endswith(("\n", "\r")):
            self.pending_line = pieces.pop()

        return [line.rstrip("\r\n") for line in pieces]


class MonitorState:
    def __init__(self):
        self.events = deque(maxlen=WINDOW_SIZE)
        self.rate_history = deque(maxlen=100)
        self.baseline_rates = []
        self.alerts = deque(maxlen=100)
        self.clients = set()
        self.file_cursor = LogFileCursor()
        self.started = False
        self.last_event = None
        self.total_events = 0
        self.total_errors = 0
        self.anomaly_active = False
        self.system_status = "learning"

    @property
    def baseline_mean(self):
        return statistics.mean(self.baseline_rates) if self.baseline_rates else 0.0

    @property
    def baseline_std(self):
        if len(self.baseline_rates) < 2:
            return 0.0
        return statistics.stdev(self.baseline_rates)

    @property
    def current_rate(self):
        return sum(1 for x in self.events if x["is_error"]) / len(self.events) if self.events else 0.0


state = MonitorState()


def parse_line(line: str) -> Optional[dict]:
    line = line.strip()
    if not line:
        return None

    m = LOG_RE.match(line)
    if not m:
        # Graceful fallback for arbitrary log lines.
        parts = line.split(maxsplit=2)
        if len(parts) >= 2:
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": parts[1].upper(),
                "service": parts[0],
                "message": parts[-1],
            }
        return None

    ts, level, service, message = m.group("ts"), m.group("level"), m.group("service"), m.group("message")
    return {
        "timestamp": ts,
        "level": level,
        "service": service,
        "message": message,
    }


def classify_severity(z: float, rate: float, baseline: float) -> str:
    # Severity is based on deviation from the established baseline.
    if z >= 4.0 or rate >= max(0.80, baseline + 0.50):
        return "CRITICAL"
    if z >= 3.0 or rate >= max(0.60, baseline + 0.35):
        return "HIGH"
    if z >= 2.5 or rate >= max(0.40, baseline + 0.20):
        return "MEDIUM"
    return "LOW"


def recommend_action(message: str) -> str:
    text = message.casefold()
    if "memory" in text or "out of memory" in text:
        return "Inspect memory usage and recent workload changes."
    if any(term in text for term in ("authentication", "unauthorized", "token", "credential")):
        return "Inspect authentication failures and recent credential or configuration changes."
    if any(term in text for term in ("database", "connection", "timeout")):
        return "Inspect database connectivity and recent deployments."
    return "Inspect the affected service logs and recent deployments."


def build_alert(rate: float, mean: float, std: float, event: dict) -> dict:
    z = (rate - mean) / std if std > 1e-9 else (10.0 if rate > mean else 0.0)
    severity = classify_severity(z, rate, mean)
    message = event.get("message", "")

    return {
        "id": f"{state.total_events}-{int(datetime.now().timestamp() * 1000)}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "error_rate": round(rate, 3),
        "baseline_rate": round(mean, 3),
        "z_score": round(z, 2),
        "service": event.get("service", "unknown"),
        "message": message,
        "recommendation": recommend_action(message),
    }


def publish_sns(alert: dict):
    if alert.get("severity") not in {"HIGH", "CRITICAL"}:
        return {"sent": False, "reason": "SNS notifications are limited to HIGH and CRITICAL alerts"}

    if not SNS_TOPIC_ARN:
        return {"sent": False, "reason": "AWS_SNS_TOPIC_ARN not configured"}

    try:
        sns = boto3.client("sns", region_name=AWS_REGION)
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f"[{alert['severity']}] SentinelPulse anomaly",
            Message=json.dumps(alert, indent=2),
        )
        return {"sent": True}
    except (BotoCoreError, ClientError) as exc:
        return {"sent": False, "reason": str(exc)}


async def broadcast(payload: dict):
    dead = []
    for ws in list(state.clients):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        state.clients.discard(ws)


async def process_event(event: dict):
    state.total_events += 1
    is_error = event["level"] in {"ERROR", "CRITICAL", "FATAL"}
    if is_error:
        state.total_errors += 1

    event["is_error"] = is_error
    state.events.append(event)
    state.last_event = event

    if len(state.events) < WINDOW_SIZE:
        return

    rate = state.current_rate

    # Establish baseline from the first completed rolling windows.
    if len(state.baseline_rates) < BASELINE_WINDOWS:
        state.baseline_rates.append(rate)
        record_metric(rate)
        if len(state.baseline_rates) >= BASELINE_WINDOWS:
            state.system_status = "normal"
        await broadcast({
            "type": "metric",
            "data": snapshot(),
        })
        return

    mean = state.baseline_mean
    std = state.baseline_std

    # Add only normal rates to baseline; anomalies should not poison the baseline.
    z = (rate - mean) / std if std > 1e-9 else (10.0 if rate > mean else 0.0)

    state.system_status = "anomaly" if z >= Z_THRESHOLD else "normal"
    record_metric(rate)

    is_anomaly = z >= Z_THRESHOLD
    if is_anomaly and not state.anomaly_active:
        alert = build_alert(rate, mean, std, event)
        state.alerts.appendleft(alert)
        alert["aws"] = publish_sns(alert)
        await broadcast({"type": "alert", "data": alert})

    state.anomaly_active = is_anomaly

    await broadcast({"type": "metric", "data": snapshot()})


def snapshot():
    return {
        "window_size": WINDOW_SIZE,
        "events_in_window": len(state.events),
        "current_error_rate": round(state.current_rate, 3),
        "baseline_error_rate": round(state.baseline_mean, 3),
        "baseline_std": round(state.baseline_std, 3),
        "baseline_ready": len(state.baseline_rates) >= BASELINE_WINDOWS,
        "baseline_windows_collected": len(state.baseline_rates),
        "system_status": state.system_status,
        "active_alerts": int(state.system_status == "anomaly"),
        "total_events": state.total_events,
        "total_errors": state.total_errors,
        "last_event": state.last_event,
    }


def record_metric(rate: float):
    state.rate_history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error_rate": round(rate, 3),
    })


async def monitor_file():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.touch(exist_ok=True)

    while True:
        try:
            for line in state.file_cursor.read_new_lines(LOG_FILE):
                event = parse_line(line)
                if event:
                    await process_event(event)
        except Exception as exc:
            await broadcast({"type": "system", "message": f"Monitor error: {exc}"})

        await asyncio.sleep(0.25)


@app.get("/")
async def root():
    return {"name": "SentinelPulse", "status": "running"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "log_file": str(LOG_FILE), "aws_sns_configured": bool(SNS_TOPIC_ARN)}


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/status")
async def api_status():
    return snapshot()


@app.get("/api/metrics")
async def api_metrics():
    return list(state.rate_history)


@app.get("/api/snapshot")
async def api_snapshot():
    return snapshot()


@app.get("/api/alerts")
async def api_alerts():
    return list(state.alerts)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    state.clients.add(websocket)
    try:
        await websocket.send_json({"type": "metric", "data": snapshot()})
        for alert in list(state.alerts):
            await websocket.send_json({"type": "alert", "data": alert})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.clients.discard(websocket)
    except Exception:
        state.clients.discard(websocket)
