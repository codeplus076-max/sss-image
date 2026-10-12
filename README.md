# SIH26057 — Side-Scan Sonar Marine Intelligence Platform

**AI-Assisted Acoustic Anomaly Detection, Geographic Survey Anchoring & Operational Decision-Support Workstation**

---

## 1. Project Overview

The **SIH26057 Side-Scan Sonar Marine Intelligence Platform** is a decision-support system designed to assist sonar analysts, hydrographers, and maritime survey operators in screening acoustic backscatter imagery.

The platform provides end-to-end processing:
1. **Acoustic Quality Validation**: Rejects non-sonar photographs, scanned documents, and corrupt uploads before ML execution.
2. **Multi-Model Anomaly Inference**: Executes specialized YOLO architectures targeting maritime hazards.
3. **Cross-Model Deduplication & Normalization**: Resolves overlapping detections (IoU filtering) and maps raw model classes into standardized semantic categories.
4. **Deterministic Priority & Review Layer**: Assigns transparent operational triage priority (`HIGH`, `MEDIUM`, `LOW`) and rule-based explanations without speculative threat classification.
5. **Geographic Survey Anchoring**: Distinguishes between survey vessel/towfish GPS navigation anchors (`EPSG:4326 - WGS 84`) and image-space pixel localization.
6. **Evidence Persistence & Reporting**: Stores full-resolution survey evidence and generates downloadable JSON and CSV survey dossiers.

---

## 2. Active Model Registry

The platform currently operates **5 verified models**:

| Model Key | Display Name | Architecture | Input Size | Target Classes | Priority Tier | Status |
| :--- | :--- | :---: | :---: | :--- | :---: | :---: |
| `cylinder` | Cylinder Detector | YOLO12s | $1536 \times 1536$ | Cylinder | `LOW` | **Active / Operational** |
| `ghostvision` | GhostVision | YOLO12s | $640 \times 640$ | Crab-Pot (Ghost Gear) | `MEDIUM` | **Active / Operational** |
| `mines` | Mine Detector | YOLO12s | $640 \times 640$ | MILCO, NOMBO | `HIGH` | **Active / Operational** |
| `shipwreck` | Shipwreck Detector | YOLO26n | $640 \times 640$ | Shipwreck, MILCO, NOMBO, Class_0 | `HIGH` | **Active / Operational** |
| `subpipes` | Subsea Pipeline Detector | YOLO12s | $640 \times 640$ | Pipeline | `MEDIUM` | **Active / Operational** |

### Natural Seabed Model Status
- **Status**: **Pending Training / Disabled**
- The Natural Seabed model is actively in training by team members and is **not** integrated into this release. It is intentionally reported as `unavailable` in `/api/v1/health` and `unavailable_models` in `/api/v1/models`.

---

## 3. Architecture & Repository Structure

```
sss/
├── backend/
│   ├── app/
│   │   ├── api/v1/routes/      # FastAPI endpoints (analyze, models, health, etc.)
│   │   ├── core/               # Configuration, model registry, constants
│   │   ├── db/                 # SQLAlchemy database session & initialization
│   │   ├── models/             # Database ORM models
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   └── services/           # Inference, validator, normalizer, persistence
│   ├── models/                 # PyTorch model checkpoint directories
│   ├── tests/                  # Automated pytest test suites (240+ tests)
│   ├── requirements.txt        # Backend Python dependencies
│   ├── .env.example            # Backend environment template
│   └── README.md
├── frontend/
│   ├── src/
│   │   ├── components/         # Views (Ingest, Quality, Detection, Evidence, Report)
│   │   ├── data/               # Report export builders & shared definitions
│   │   ├── services/           # Centralized API client (`api.js`)
│   │   └── utils/              # Audio feedback and formatting utilities
│   ├── public/                 # Static sonar sample assets
│   ├── package.json            # Frontend npm dependencies
│   ├── vite.config.js          # Vite configuration
│   └── .env.example            # Frontend environment template
├── .gitignore                  # Root git exclusion rules
└── README.md                   # System documentation
```

---

## 4. Prerequisites

- **Python**: 3.10, 3.11, 3.12, or 3.13
- **Node.js**: v18.0.0 or higher (with `npm`)
- **Git**

---

## 5. Quickstart & Installation

### Step A: Backend Setup

1. Open a terminal and navigate to `backend/`:
   ```bash
   cd backend
   ```

2. Create and activate a Python virtual environment:
   - **Windows (PowerShell)**:
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
   - **Linux / macOS**:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. Install required Python packages:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Configure environment variables (optional, defaults work out-of-the-box):
   ```bash
   # Windows PowerShell
   Copy-Item .env.example .env
   # Linux / macOS
   cp .env.example .env
   ```

5. Start the FastAPI backend server:
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

The backend server is accessible at `http://127.0.0.1:8000`.
- **Interactive Swagger Documentation**: `http://127.0.0.1:8000/docs`
- **Health Check**: `http://127.0.0.1:8000/api/v1/health`

---

### Step B: Frontend Setup

1. Open a second terminal and navigate to `frontend/`:
   ```bash
   cd frontend
   ```

2. Install npm dependencies:
   ```bash
   npm install
   ```

3. Configure environment variables (optional):
   ```bash
   # Windows PowerShell
   Copy-Item .env.example .env
   # Linux / macOS
   cp .env.example .env
   ```

4. Start the Vite development server:
   ```bash
   npm run dev
   ```

The frontend application will be live at `http://localhost:5173`.

---

## 6. Model Files & Data Assets

The model weights are stored in `backend/models/`:
- `backend/models/Cylinder model/best/`
- `backend/models/GhostVision_YOLO12s_best.pt/best/`
- `backend/models/Mine_YOLO12s_best.pt/best/`
- `backend/models/shipwreak model/best/`
- `backend/models/SubPipeMini2_YOLO12s_best.pt.pt/best/`

Total uncompressed disk size across all 5 models is approximately **77 MB**.

---

## 7. Database & Storage Initialization

- **Database**: SQLite by default (`sonarops.db`).
- **Auto-Initialization**: Database schema and tables auto-initialize on application startup via SQLAlchemy metadata creation. No manual migrations are required.
- **Evidence Storage**: Sonar survey images are stored in `backend/storage/sonar-evidence/` and streamed via `/api/v1/analysis/{id}/evidence`.
- **Clean Environment**: If `sonarops.db` is deleted, the backend creates a fresh database automatically upon restart.

---

## 8. Verification & Testing

### Running Backend Test Suite
From the `backend/` directory with virtual environment activated:
```bash
pytest -v tests/
```
*Expected: 240+ passing tests (0 failures).*

### Running Frontend Production Build
From the `frontend/` directory:
```bash
npm run build
```
*Expected: 0 errors.*

---

## 9. API Workflow & Endpoints

```
[Upload Sonar Swath] 
       │
       ▼
POST /api/v1/analysis/analyze  ──► Sonar Quality Gate (Rejects photos with 422)
       │                       ──► Multi-Model Inference (5 active models)
       │                       ──► Deduplication & Semantic Normalization
       │                       ──► Deterministic Priority Assignment
       │                       ──► SQLite Persistence & Evidence Storage
       ▼
GET  /api/v1/analysis/{id}            (Retrieve complete analysis session)
GET  /api/v1/analysis/{id}/evidence   (Stream original sonar evidence image)
GET  /api/v1/analysis                 (List paginated survey history)
GET  /api/v1/models                   (List available & unavailable models)
GET  /api/v1/health                   (Backend operational health check)
```

---

## 10. Operational Limitations & Scientific Honesty

1. **Decision Support, Not Autonomous Threat Classification**: The platform identifies candidate acoustic anomalies and assigns review priority (`HIGH`, `MEDIUM`, `LOW`) to guide human operators. It does not replace certified mine-countermeasure (MCM) authorities and never claims confirmed explosive threat status from AI detections alone.
2. **Cartographic Distinction**: Target coordinates are localized in sonar image-space (percentage offsets). Survey GPS coordinates anchor the towfish. Conversion to absolute seafloor geographic coordinates requires vehicle altitude, towfish layback, and ray-tracing bathymetry.
3. **Natural Seabed Integration**: The Natural Seabed model remains pending training and is intentionally excluded from active inference.


## Anonymous browser sessions

Visitors do not need an account. The frontend initializes a random anonymous session
using `POST /api/v1/session` before requesting analyses. An HttpOnly, SameSite=Lax
cookie lasts one year (renewed on initialization); HTTPS responses mark it Secure.
Only the SHA-256 hash is stored with each analysis. History, individual results,
evidence, deletion, and asynchronous job polling are restricted to that browser.
Private responses disable caching. Clearing cookies or switching browsers starts a
new history; stored uploads are not deleted by clearing cookies.

On startup the backend adds the nullable `owner_hash` column and index to existing
SQLite/PostgreSQL databases. Existing uploads remain stored with no owner and are
inaccessible through visitor endpoints. No administrator UI is included.

Deploy both frontend and backend together. Browser requests now use `/api` on the
website domain so cookies also work when third-party cookies are blocked:
- Vercel: `frontend/vercel.json` proxies `/api` to the Render backend listed in the
  keep-alive workflow. Update that destination if your backend hostname changes.
- Local development/preview: Vite proxies `/api` to `http://127.0.0.1:8000`.
- `VITE_API_BASE_URL` is no longer used. Other hosting must provide the same proxy.
- Add your exact production/custom/preview frontend origin to backend `CORS_ORIGINS`.
  Arbitrary Vercel preview domains are no longer trusted.
- Keep any Supabase evidence bucket private; public object URLs bypass API access checks.

API clients must initialize a session and retain its cookie for subsequent requests.
Session cookies are private credentials and must not be shared.
