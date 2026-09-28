# SentinelPulse — Real-Time Log Anomaly Detector

SentinelPulse monitors a continuously growing application log, calculates a rolling error rate, learns a normal baseline, detects statistically significant deviations, assigns severity, streams alerts to a React dashboard, and optionally publishes alerts to AWS SNS.

## Architecture

```text
Growing app.log
      |
      v
Python file monitor (FastAPI)
      |
      +--> Sliding window ---> Error rate
      |                           |
      |                           v
      |                    Baseline mean/std
      |                           |
      |                           v
      |                    Z-score detection
      |                           |
      |                  +--------+--------+
      |                  |                 |
      v                  v                 v
React WebSocket     Alert feed        AWS SNS
dashboard
```

## Quick start

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload --port 8000
```

### 2. Frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

### 3. Generate a live log stream

Open a third terminal:

```bash
python scripts/generate_logs.py
```

The generator deliberately creates normal traffic followed by an error burst, making the anomaly detector easy to demonstrate.

## AWS SNS

Create an SNS topic in AWS and put its ARN into `backend/.env`:

```env
AWS_REGION=ap-south-1
AWS_SNS_TOPIC_ARN=arn:aws:sns:ap-south-1:YOUR_ACCOUNT_ID:sentinelpulse-alerts
```

Configure AWS credentials locally using the AWS CLI (`aws configure`) or your normal AWS credential mechanism.

If no SNS topic is configured, the application still works locally and marks AWS delivery as not configured.

## Demo flow

1. Start backend.
2. Start frontend.
3. Start log generator.
4. Wait for baseline learning.
5. The generator enters an error burst.
6. Error rate rises above baseline.
7. SentinelPulse creates a severity alert.
8. Alert appears in the browser immediately through WebSocket.
9. If SNS is configured, the same alert is published to AWS.

## Why the approach is useful

The baseline is protected from anomaly contamination: detected anomalous windows are not used to learn the normal baseline. This prevents a prolonged incident from slowly becoming the new "normal."

## Team split

- Member 1: Backend/log monitoring
- Member 2: Frontend dashboard
- Member 3: AWS SNS
- Member 4: Testing/demo data
- Member 5: Documentation/architecture
- Member 6: Demo/presentation/QA
