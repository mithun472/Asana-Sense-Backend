# ASANA-SENSE Backend

AI-powered yoga posture correction backend. FastAPI + MongoDB + TFLite pose model + Groq AI reports.

## Tech Stack
- **FastAPI** — REST + WebSocket API
- **MongoDB** (Motor async driver) — users, sessions
- **TFLite** — on-server pose classification model
- **Groq (Llama 3.3 70B)** — AI-generated session reports (with local fallback if key missing/fails)
- **JWT + bcrypt** — auth
- **AES-256-GCM** — encrypts sensitive profile fields (`name`, `bmi_data`) at rest
- **Cloudinary** — media storage (avatars/assets)

## Folder Structure
```
backend/
├── main.py              # App entrypoint, CORS, lifespan (DB connect, model load)
├── auth.py              # JWT create/decode, get_current_user dependency
├── crypto_utils.py       # AES-256 field encryption/decryption helpers
├── database.py           # MongoDB connection + collection getters
├── models.py              # Pydantic request/response schemas
├── pose_engine.py         # TFLite model wrapper — classify pose, evaluate joints
├── reference_poses.py     # Loads/computes reference pose landmarks
├── cloudinary_utils.py    # Cloudinary config
├── email_service.py       # PDF report generation + SMTP email sending
├── seed_data.py           # Seed script for pose reference data
├── dashboard.html          # Live ops dashboard (optional, see below)
├── live_feed.py            # In-memory feed manager for the dashboard
├── .env.example            # Environment variable template
└── routes/
    ├── auth.py         # /api/auth/*
    ├── poses.py        # /api/poses/*
    ├── sessions.py      # /api/sessions/*
    ├── reports.py       # /api/generate-session-report, /api/send-session-report-email
    ├── websocket.py      # /ws/pose-detect
    └── live_ops.py        # /ops, /ws/live (optional dashboard)
```

## Routes

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/health` | — | Health check |
| POST | `/api/auth/signup` | — | Create account |
| POST | `/api/auth/signin` | — | Login, get JWT |
| GET | `/api/auth/me` | ✅ | Get current user profile |
| PATCH | `/api/auth/profile` | ✅ | Update onboarding/BMI/experience fields |
| GET | `/api/poses` | — | List all yoga poses |
| GET | `/api/poses/{pose_id}` | — | Get one pose's detail |
| POST | `/api/sessions` | ✅ | Save a completed practice session |
| GET | `/api/sessions` | ✅ | List current user's session history |
| GET | `/api/sessions/{id}` | ✅ | Get one session |
| POST | `/api/generate-session-report` | — | Generate AI report (Groq, fallback if unavailable) |
| POST | `/api/send-session-report-email` | ✅ | Email the PDF report to the user |
| WS | `/ws/pose-detect` | — | Real-time pose classification + correction feed |
| GET | `/ops` | — | Live ops dashboard (optional, dev tool) |
| WS | `/ws/live` | — | Feed for the ops dashboard |

## How the Core Flow Works
1. **Frontend camera** → extracts skeletal landmarks locally (never sends raw video/audio here).
2. **`/ws/pose-detect`** → landmarks in, TFLite model classifies pose, checks joint correctness, sends back correctness + timer state every frame.
3. **Session ends** → frontend calls `/api/generate-session-report` → Groq generates a friendly report (or fallback heuristics if no/failed key) → returned to frontend.
4. **Frontend calls `/api/sessions`** → session + report saved to MongoDB under the user.
5. **Optional** → user requests `/api/send-session-report-email` → PDF built and emailed.

## Environment Variables (`.env`)
Copy `.env.example` → `.env` and fill in:
- `MONGODB_URI` — your MongoDB Atlas connection string
- `JWT_SECRET` — random secret for signing tokens
- `CLOUDINARY_*` — Cloudinary credentials
- `TFLITE_MODEL_PATH` — path to the `.tflite` model file
- `FRONTEND_ORIGIN` — your frontend URL (CORS)
- `GROQ_API_KEY` — for AI report generation (get a fresh key if you were seeing 401 errors)
- `PROFILE_ENCRYPTION_KEY` — 32-byte key for AES-256 profile encryption, generate with:
  ```
  python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
  ```

## Security Notes
- Passwords → bcrypt hashed (one-way, never decrypted).
- `name` and `bmi_data` → AES-256-GCM encrypted at rest in MongoDB.
- `email` stays plaintext (needed for login lookup).
- No raw video/audio ever reaches the backend — only numeric skeletal landmarks.

## Running Locally
```bash
pip install -r requirements.txt --break-system-packages
python main.py
```
Server runs on `http://localhost:8000`. Docs at `/docs` (FastAPI auto Swagger UI).

## Optional: Live Ops Dashboard
Drop `dashboard.html`, your logo, and `live_feed.py` in the backend root, register `routes/live_ops.py`, and add the request-logging middleware to `main.py` (see earlier setup notes). Visit `/ops` to watch live API traffic categorized by auth / pose-detect / AI report / session / system.
