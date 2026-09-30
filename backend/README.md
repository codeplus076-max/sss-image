# SonarOps Marine Intelligence — Backend Service

A modular, production-ready FastAPI backend for the AI-powered Side-Scan Sonar (SSS) anomaly detection and marine intelligence workstation.

---

## Architecture Overview

```
backend/
├── app/
│   ├── __init__.py           # Package marker
│   ├── main.py               # FastAPI application factory and server entry point
│   ├── api/                  # API routers
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       └── routes/
│   │           ├── __init__.py
│   │           └── health.py # GET /api/v1/health endpoint
│   ├── core/                 # Core settings, constants, and CORS handling
│   │   ├── __init__.py
│   │   └── config.py
│   ├── schemas/              # Pydantic data schemas
│   │   ├── __init__.py
│   │   └── common.py         # Shared schemas (HealthResponse, etc.)
│   ├── services/             # Future business logic, preprocessing, & AI pipelines
│   │   └── __init__.py
│   └── utils/                # Utility helpers (sonar image processing, coordinates)
│       └── __init__.py
├── tests/                    # Automated unit & integration tests
│   ├── __init__.py
│   └── test_health.py        # Pytest test cases for health endpoints
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variables template
├── .gitignore                # Ignored caches, venv, and environment files
└── README.md                 # Setup and run instructions
```

---

## Prerequisites

- **Python**: 3.10+ (tested on Python 3.12 / 3.13)
- **Package Manager**: `pip`

---

## Getting Started

### 1. Create a Python Virtual Environment

From the `backend/` directory:

**On Windows (PowerShell):**
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

*(If script execution is disabled on PowerShell, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process` first)*

**On Linux / macOS / Git Bash:**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

---

### 2. Install Dependencies

With the virtual environment activated:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

### 3. Configure Environment Variables

Copy `.env.example` to `.env`:

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

**Linux / macOS:**
```bash
cp .env.example .env
```

Default configuration in `.env`:
```ini
APP_NAME=sonar-backend
APP_ENV=development
API_V1_PREFIX=/api/v1
HOST=0.0.0.0
PORT=8000
DEBUG=True
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000
```

---

### 4. Run the FastAPI Development Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The server will be available at:
- **API Base**: `http://localhost:8000`
- **Interactive OpenAPI Docs**: `http://localhost:8000/docs`
- **Alternative ReDoc**: `http://localhost:8000/redoc`
- **Health Check**: `http://localhost:8000/api/v1/health`

---

### 5. Verify the Health Endpoint

**Request:**
```bash
curl http://localhost:8000/api/v1/health
```

**Response:**
```json
{
  "status": "ok",
  "service": "sonar-backend",
  "version": "v1"
}
```

---

### 6. Run Automated Tests

Run the test suite with `pytest`:

```bash
pytest
```

To run with verbose output:
```bash
pytest -v
```

---

## CORS Configuration

By default, the backend allows origins matching the React/Vite frontend development server (`http://localhost:5173` and `http://127.0.0.1:5173`). To add custom origins or production URLs, update `CORS_ORIGINS` in your `.env` file.

---

## Operational Models & Geolocation Status

### 1. Verified Operational Models (5 Models)
- **Cylinder**: Industrial cylinders / container detection (`YOLO12s`, native 1536px)
- **GhostVision**: Ghost fishing gear / abandoned crab pots (`YOLO12s`, native 640px)
- **Mines**: Naval mine warfare objects (`MILCO`, `NOMBO`) (`YOLO12s`, native 640px)
- **Shipwreck**: Maritime vessels & wrecks (`YOLO26n`, native 640px)
- **SubPipes**: Subsea pipelines & conduits (`YOLO12s`, native 640px)
- **Natural Seabed**: Currently pending training by team; returns descriptive HTTP 400 when explicitly requested.

### 2. Geolocation Integrity & Survey Metadata
- Accepts optional survey metadata: `latitude` ([-90, 90]), `longitude` ([-180, 180]), `depth` (>= 0), `heading` ([0, 360)), and `timestamp` (ISO-8601).
- **Strict Geolocation Integrity**: Zero coordinate fabrication. Image-only uploads strictly retain `latitude: null`, `longitude: null`, and `geolocation_available: false`.
- **Architectural Separation**: Detections retain pure 2D bounding boxes in image pixel and normalized space, while survey navigation data is encapsulated separately in `metadata` and backward-compatible `geolocation`.

---

## Cloud Deployment (e.g. Render)

The backend is fully self-contained and pre-configured for containerized and cloud PaaS deployment (such as Render, Railway, or Fly.io).

### Render Web Service Configuration:
- **Environment**: `Python 3`
- **Root Directory**: `backend`
- **Build Command**:
  ```bash
  pip install -r requirements.txt
  ```
- **Start Command**:
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port $PORT
  ```

### Required Environment Variables:
| Variable | Description | Example Value |
|---|---|---|
| `PORT` | Dynamically injected by Render | *(Injected automatically)* |
| `CORS_ORIGINS` | Comma-separated allowed frontend domains | `https://your-frontend.onrender.com` |
| `APP_ENV` | Application environment mode | `production` |
| `PYTHON_VERSION` | Python runtime version | `3.11` or `3.12` |

> **Note on Model Resolution**: All 5 trained models are packaged in `backend/models/`. The application automatically resolves model paths relative to the project directory or through `MODELS_DIR` regardless of working directory or operating system. Local development origins (`localhost:5173`, etc.) are automatically preserved alongside production origins.


