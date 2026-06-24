# ☁️ Cloud Cost Management Dashboard

> Track AWS cloud resource usage, estimate monthly costs, identify unused resources for cleanup, and predict future spending with machine learning.

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/Python-3.11-green)
![React](https://img.shields.io/badge/React-18-blue)
![License](https://img.shields.io/badge/license-MIT-yellow)

---

## 📋 Table of Contents
1. [Features](#features)
2. [Architecture](#architecture)
3. [Quick Start (3 Steps)](#quick-start)
4. [AWS Setup](#aws-setup)
5. [Configuration Reference](#configuration-reference)
6. [Running Without Docker](#running-without-docker)
7. [API Reference](#api-reference)
8. [Project Structure](#project-structure)
9. [Changelog](#changelog)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔍 **Resource Inventory** | Tracks EC2, S3, RDS, and Lambda across your AWS account |
| 💰 **Cost Estimation** | Estimates monthly spend per resource using AWS on-demand pricing |
| 🧹 **Cleanup Recommendations** | Detects idle, stopped, and unused resources with savings calculations |
| 🤖 **ML Cost Prediction** | Polynomial regression model forecasts next 30 days of cloud spend |
| 📊 **Interactive Dashboard** | Dark-mode React dashboard with Recharts visualizations |
| 🔄 **Auto Collection** | Background scheduler collects AWS data every 6 hours (configurable) |
| 🐳 **Docker Ready** | One-command startup — no manual setup required |
| 🎭 **Demo Mode** | Works without AWS credentials using realistic simulated data |

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────┐
│         Frontend (React + Vite + nginx)      │
│   Dashboard │ Resources │ Costs │ Predictions│
└──────────────────┬──────────────────────────┘
                   │ REST API (HTTP)
┌──────────────────▼──────────────────────────┐
│           Backend (FastAPI + Python)         │
│  AWS Collector │ Cost Estimator │ ML Predict │
└──────┬─────────────────────────┬────────────┘
       │                         │
  PostgreSQL DB             AWS API (boto3)
  (cost history)         EC2 │ S3 │ RDS │ Lambda
```

---

## 🚀 Quick Start

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- AWS IAM credentials (or use Demo Mode — see below)

### Step 1 — Clone and configure

```bash
# Copy the example environment file
cp .env.example .env
```

Open `.env` in any text editor and fill in:

```env
# Your AWS credentials (read-only IAM user)
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=your_secret_here
AWS_DEFAULT_REGION=us-east-1

# Database password (choose any strong password)
POSTGRES_PASSWORD=MyStr0ngPassword!

# Set to "true" if you want to use demo/test data without AWS
DEMO_MODE=false
```

> ⚠️ **Never share or commit your `.env` file.**

### Step 2 — Start the application

```bash
docker compose up --build
```

The first startup takes 2-3 minutes as Docker builds the images and collects initial AWS data.

### Step 3 — Open the dashboard

```
http://localhost:3000
```

The API docs (Swagger UI) are available at `http://localhost:8000/docs`

---

## 🔑 AWS Setup

You need an AWS IAM user with **read-only permissions**. Here's how:

### Option A — Attach ReadOnlyAccess policy (quickest)
1. Go to **AWS Console → IAM → Users → Create user**
2. Set a name (e.g., `cloud-cost-monitor`)
3. Attach policy: **ReadOnlyAccess**
4. Create and download the Access Keys
5. Paste them into your `.env` file

### Option B — Custom minimal policy (recommended for production)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeRegions",
        "s3:ListAllMyBuckets",
        "s3:GetBucketLocation",
        "rds:DescribeDBInstances",
        "lambda:ListFunctions",
        "cloudwatch:GetMetricStatistics"
      ],
      "Resource": "*"
    }
  ]
}
```

### Demo Mode (no AWS needed)

Set `DEMO_MODE=true` in your `.env` to use realistic simulated data — perfect for testing the UI or demo presentations.

---

## ⚙️ Configuration Reference

All configuration is via the `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_ACCESS_KEY_ID` | — | IAM Access Key ID |
| `AWS_SECRET_ACCESS_KEY` | — | IAM Secret Access Key |
| `AWS_DEFAULT_REGION` | `us-east-1` | Primary AWS region |
| `POSTGRES_USER` | `ccm_user` | PostgreSQL username |
| `POSTGRES_PASSWORD` | — | **Required:** PostgreSQL password |
| `POSTGRES_DB` | `cloud_cost_db` | Database name |
| `DEMO_MODE` | `false` | `true` = use simulated data |
| `COLLECTION_INTERVAL_HOURS` | `6` | How often to pull AWS data |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend URL for frontend |

---

## 🖥️ Running Without Docker

> Requires Python 3.11+, Node.js 18+, and a running PostgreSQL instance.

### Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# IMPORTANT: Copy your .env file from the root directory into the backend/ directory.
# Then start the API
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

---

## 📡 API Reference

The full interactive API docs are available at **`http://localhost:8000/docs`** after startup.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check + config info |
| `GET` | `/resources/` | List all resources (filterable) |
| `GET` | `/resources/summary` | Count by service/status |
| `GET` | `/costs/summary` | Total cost + savings summary |
| `GET` | `/costs/trend?days=30` | Daily cost trend data |
| `GET` | `/costs/by-service` | Cost breakdown per AWS service |
| `GET` | `/costs/top-resources` | Most expensive resources |
| `GET` | `/recommendations/` | Cleanup recommendations |
| `POST`| `/recommendations/{id}/resolve` | Mark as resolved |
| `POST`| `/recommendations/refresh` | Re-run advisor |
| `GET` | `/predictions/` | ML 30-day cost forecast |

---

## 📁 Project Structure

```
Cloud Cost Management/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Environment configuration
│   ├── database.py          # SQLAlchemy engine + sessions
│   ├── scheduler.py         # APScheduler background jobs
│   ├── models/              # SQLAlchemy ORM models
│   │   ├── resource.py      # Cloud resource model
│   │   └── cost_record.py   # Cost history + recommendations
│   ├── routes/              # FastAPI route handlers
│   │   ├── resources.py
│   │   ├── costs.py
│   │   ├── recommendations.py
│   │   └── predictions.py
│   ├── services/            # Business logic
│   │   ├── aws_collector.py   # boto3 AWS data collection
│   │   ├── cost_estimator.py  # Cost calculation + DB writes
│   │   ├── cleanup_advisor.py # Idle resource detection
│   │   └── ml_predictor.py   # scikit-learn cost forecast
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/client.js    # Axios API calls
│   │   ├── components/      # Sidebar, TopBar
│   │   ├── pages/           # Dashboard, Resources, Costs, Recommendations, Predictions
│   │   ├── App.jsx          # Router + layout
│   │   ├── main.jsx         # React entry point
│   │   └── index.css        # Design system (dark glassmorphism)
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml       # Orchestrates all services
├── .env.example             # Template — copy to .env and fill in
└── README.md
```

---

## 🔄 Stopping and Restarting

```bash
# Stop all services
docker compose down

# Stop and delete all data (fresh start)
docker compose down -v

# View logs
docker compose logs -f backend
docker compose logs -f frontend
```

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| Dashboard shows no data | Check AWS credentials in `.env`. Try `DEMO_MODE=true` to verify UI works. |
| `docker compose up` fails | Ensure Docker Desktop is running. Try `docker compose down -v` then retry. |
| Backend error on startup | Check `docker compose logs backend` for the full error message. |
| Frontend can't reach API | Ensure backend is healthy at `http://localhost:8000/health`. |
| ML prediction shows flat line | Not enough historical data. It improves after 7+ days of data collection. |

---

## 📝 Changelog

### v1.0.0 — Initial Release
- AWS resource collection: EC2, S3, RDS, Lambda
- Cost estimation with on-demand pricing map
- Cleanup recommendations (idle, stopped, empty resources)
- ML cost prediction (polynomial regression)
- React dashboard with dark glassmorphism design
- Docker Compose for one-command deployment
- Demo mode for testing without AWS credentials

---

## 📄 License

MIT License — free to use, modify, and distribute.

---

*Built with ❤️ using Python (FastAPI), React, PostgreSQL, and AWS SDK.*
