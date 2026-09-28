<div align="center">

<img src="asana_sense_logo.png" alt="ASANA-SENSE" width="260" />

# 🧘 ASANA-SENSE Backend

### *AI-Powered Computer Vision Yoga Guide — See • Guide • Improve*

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-2.0-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![TensorFlow Lite](https://img.shields.io/badge/TFLite-Pose_Classifier-FF6F00?style=for-the-badge&logo=tensorflow&logoColor=white)
![MongoDB](https://img.shields.io/badge/Database-MongoDB_Atlas-47A248?style=for-the-badge&logo=mongodb&logoColor=white)
![Groq](https://img.shields.io/badge/AI_Reports-Groq_Llama_3.3_70B-F55036?style=for-the-badge&logoColor=white)
![WebSocket](https://img.shields.io/badge/Realtime-WebSockets-010101?style=for-the-badge&logo=socket.io&logoColor=white)
![JWT](https://img.shields.io/badge/Auth-JWT_+_bcrypt-000000?style=for-the-badge&logo=jsonwebtokens&logoColor=white)
![AES-256](https://img.shields.io/badge/Encryption-AES--256--GCM-1FAE7A?style=for-the-badge&logo=letsencrypt&logoColor=white)
![Cloudinary](https://img.shields.io/badge/Storage-Cloudinary-3448C5?style=for-the-badge&logo=cloudinary&logoColor=white)

**Real-time yoga posture correction that never records your camera — only skeletal landmarks travel to the server.**

[✨ Features](#-key-features) • [🧠 How It Works](#-how-the-pipeline-works) • [🛣️ API Routes](#️-api-routes) • [🔐 Security](#-security--privacy-commitments) • [📊 Live Ops](#-live-ops-dashboard) • [🚀 Quick Start](#-getting-started)

</div>

---

## 📌 Executive Summary

**ASANA-SENSE** turns any webcam into a personal yoga teacher. This repository is the **FastAPI backend** powering it:

1. **Real-Time Pose Detection**: The browser extracts 33 body landmarks and streams them over WebSocket. The server classifies the pose with a **TFLite model** and answers frame-by-frame with correctness, joint feedback and a hold-timer signal.
2. **Joint-Level Correction**: Every joint is judged **green / yellow / red** against reference poses, with plain-language correction messages (e.g. *"You're doing Warrior. Switch to Tree."*).
3. **AI Session Reports**: When a session ends, **Groq (Llama 3.3 70B)** writes a friendly, human-readable report — with an automatic **biomechanical fallback** if the AI is unavailable.
4. **Progress Tracking**: Sessions and reports are stored per user in MongoDB, powering history and improvement stats.
5. **Certified PDF Emails**: One request builds a PDF report with ReportLab and mails it to the user over SMTP.
6. **Privacy by Design**: No video, no audio, no images reach the backend. Profile fields are **AES-256-GCM encrypted at rest**.

---

## ✨ Key Features

### 🎯 1. Live Pose Engine
- **WebSocket pipeline** at `/ws/pose-detect` — landmarks in, verdict out, every frame.
- **TFLite classifier** identifies which of the supported poses the user is holding, with a confidence score.
- **Target-pose aware**: compares what you're doing against what you *should* be doing.
- **Smart hold timer**: timer starts/continues only while form is correct, pauses the moment a joint goes red.

### 🧘 2. Supported Poses
| Pose | Pose | Pose |
|---|---|---|
| 🪑 Chair Pose | 🐍 Cobra Pose | 🐕 Downward-Facing Dog |
| 🕯️ Shoulder Stand | 🔺 Triangle Pose | 🌳 Tree Pose |
| 🦅 Warrior III | | |
---

## 🛠️ Project Structure

```
backend/
├── main.py                  # App entry, CORS, lifespan (DB, model, references)
├── auth.py                  # JWT + get_current_user dependency
├── crypto_utils.py          # 🔐 AES-256-GCM field encryption
├── database.py              # MongoDB (Motor) connection & collections
├── models.py                # Pydantic request/response schemas
├── pose_engine.py           # 🧠 TFLite classifier + joint evaluation
├── reference_poses.py       # Reference pose landmark loader
├── email_service.py         # 📄 ReportLab PDF + SMTP sender
├── cloudinary_utils.py      # Cloudinary config
├── seed_data.py             # Seeds the yoga pose catalogue
├── live_feed.py             # 📊 In-memory feed for ops dashboard
├── dashboard.html           # 📊 Live ops dashboard page
├── asana_sense_logo.png
├── requirements.txt
├── .env.example
└── routes/
    ├── __init__.py          # register_routes(app)
    ├── auth.py              # /api/auth/*
    ├── poses.py             # /api/poses/*
    ├── sessions.py          # /api/sessions/*
    ├── reports.py           # AI report + email
    ├── websocket.py         # /ws/pose-detect
    └── live_ops.py          # /ops + /ws/live
```

---

## 🔐 Security & Privacy Commitments

> [!IMPORTANT]
> - **No raw media, ever**: The only camera-derived data reaching the server is an array of 33 numeric `(x, y)` landmarks. No frames, no images, no audio.
> - **Nothing persisted from live detection**: WebSocket frames are processed and discarded. Only final session summaries are saved.
> - **AES-256-GCM at rest**: `name` and `bmi_data` are encrypted before hitting MongoDB, with a fresh random nonce per write and tamper detection built in.
> - **bcrypt passwords**: One-way hashed, never reversible.
> - **JWT auth**: Protected routes require a valid signed token.

> [!NOTE]
> `email` stays plaintext so login lookup and the unique index keep working. The AES key lives only in the server `.env` — **back it up and never commit it**; losing it makes encrypted fields unreadable.

---

## 📊 Live Ops Dashboard

A light-mode, ticket-style feed for demos and debugging.

1. Keep `live_feed.py`, `dashboard.html` and `asana_sense_logo.png` in the backend root.
2. Register `routes/live_ops.py` in `routes/__init__.py`.
3. Keep the `record_activity` middleware in `main.py`.
4. Open **`http://localhost:8000/ops`** 🚀

Filters: **ALL • AUTH • POSE-DETECT • AI REPORT • SESSION • SYSTEM**

---

## 🚀 Getting Started

### Prerequisites
- 🐍 **Python** 3.11+
- 🍃 **MongoDB Atlas** cluster
- ☁️ **Cloudinary** account
- 🤖 **Groq** API key *(optional — fallback works without it)*
- 📧 **Gmail App Password** *(for emailing reports)*

### 1️⃣ Install

```bash
cd backend
python -m venv venv

# Windows
.\venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2️⃣ Configure `.env`

Copy `.env.example` → `.env` and fill in:

```env
# Database
MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/asana_sense

# Auth
JWT_SECRET=your-super-secret-jwt-key
JWT_EXPIRY_MINUTES=1440

# Cloudinary
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret

# ML model
TFLITE_MODEL_PATH=../ml/models/yoga_pose_classifier.tflite

# CORS
FRONTEND_ORIGIN=http://localhost:3000

# AI reports (Groq)
GROQ_API_KEY=gsk_your_key

# 🔐 AES-256 profile encryption key
PROFILE_ENCRYPTION_KEY=your-32-byte-urlsafe-base64-key

# 📧 SMTP for PDF report emails
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-16-char-app-password
SMTP_FROM_EMAIL=your-email@gmail.com
SMTP_FROM_NAME=ASANA - SENSE AI
```

Generate the encryption key:

```bash
python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

> ⚠️ `SMTP_PASSWORD` must be a **Gmail App Password** (Google Account → Security → 2-Step Verification → App passwords), not your normal password.

### 3️⃣ Run

```bash
python main.py
# or
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

- 🌐 API: **http://localhost:8000**
- 📖 Swagger docs: **http://localhost:8000/docs**
- 📊 Ops dashboard: **http://localhost:8000/ops**

---

## 🩺 Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| 🔴 Server won't start, mentions `PROFILE_ENCRYPTION_KEY` | Key missing in `.env` | Generate and add the key |
| 🔴 Groq returns **401** | Invalid / expired / mistyped API key | Create a fresh key, no spaces or quotes |
| 🟡 Report looks generic | Groq failed → fallback engine used | Check `GROQ_API_KEY` and server logs |
| 🔴 Email report fails | SMTP credentials missing or not an App Password | Set `SMTP_USER` + `SMTP_PASSWORD` |
| 🟡 Pose detection unavailable | TFLite model not found | Check `TFLITE_MODEL_PATH` |
| 🟡 Dashboard connected but empty | Middleware not recording | Confirm `record_activity` in `main.py` |

---

## 👥 Authors & Acknowledgments

Built with 💚 for mindful, safer yoga practice. Thanks to the open-source communities behind **FastAPI**, **TensorFlow Lite**, **MongoDB**, **Groq** and **ReportLab**.

<div align="center">

**ASANA-SENSE • See • Guide • Improve • 2026**

</div>
