"""
ASANA-SENSE FastAPI Backend
- REST endpoints for auth, poses, sessions
- WebSocket for real-time pose detection pipeline
"""
import os
import json
import time
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from bson import ObjectId

from database import connect_db, close_db, users_collection, poses_collection, sessions_collection
from models import (
    SignUpRequest, SignInRequest, AuthResponse,
    UserProfileResponse, UpdateProfileRequest,
    YogaPoseResponse, WrongPostureImpact,
    SaveSessionRequest, SessionResponse,
    PoseDetectionResult, JointStatus, LandmarkFrame,
)
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, get_optional_user,
)
from pose_engine import pose_engine, CLASS_NAMES, CONF_THRESHOLD
from reference_poses import load_or_compute_references
from cloudinary_utils import configure_cloudinary

load_dotenv()


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    print("[App] Starting ASANA-SENSE Backend...")
    await connect_db()
    configure_cloudinary()

    # Load TFLite model
    try:
        pose_engine.load_model()
    except Exception as e:
        print(f"[App] WARNING: Could not load TFLite model: {e}")
        print("[App] Pose detection will not be available.")

    # Load reference poses
    try:
        refs = await load_or_compute_references("../train_landmarks.csv")
        if refs:
            pose_engine.set_reference_poses(refs)
    except Exception as e:
        print(f"[App] WARNING: Could not load reference poses: {e}")

    # Create DB indexes
    await users_collection().create_index("email", unique=True)
    await sessions_collection().create_index("user_id")

    print("[App] ASANA-SENSE Backend ready.")
    yield

    # Shutdown
    await close_db()
    print("[App] Shutdown complete.")


app = FastAPI(
    title="ASANA-SENSE API",
    description="AI Yoga Posture Correction Backend",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "ASANA-SENSE FastAPI Backend", "version": "2.0.0"}


# ══════════════════════════════════════════════════════════════════════════════
# AUTH ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/auth/signup", response_model=AuthResponse)
async def signup(req: SignUpRequest):
    """Create a new user account."""
    coll = users_collection()

    # Check if email already exists
    existing = await coll.find_one({"email": req.email.lower().strip()})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Please sign in.",
        )

    now = datetime.utcnow()
    user_doc = {
        "name": req.name.strip(),
        "email": req.email.lower().strip(),
        "password_hash": hash_password(req.password),
        "is_account_active": True,
        "avatar_seed": req.name.strip()[:2].upper(),
        "member_since": now.strftime("%b %Y"),
        "has_completed_onboarding": False,
        "age_category": "",
        "experience_level": "",
        "stats": {
            "total_sessions": 0,
            "total_minutes_practiced": 0,
            "average_score": 0,
            "favorite_pose": "",
        },
        "bmi_data": None,
        "created_at": now,
        "updated_at": now,
    }

    result = await coll.insert_one(user_doc)
    user_id = str(result.inserted_id)

    token = create_access_token(user_id, req.email.lower().strip())

    return AuthResponse(
        success=True,
        token=token,
        user={
            "id": user_id,
            "name": user_doc["name"],
            "email": user_doc["email"],
            "is_account_active": True,
            "avatar_seed": user_doc["avatar_seed"],
            "member_since": user_doc["member_since"],
            "has_completed_onboarding": False,
            "age_category": "",
            "experience_level": "",
            "stats": user_doc["stats"],
            "bmi_data": None,
        },
    )


@app.post("/api/auth/signin", response_model=AuthResponse)
async def signin(req: SignInRequest):
    """Sign in with email and password."""
    coll = users_collection()

    user = await coll.find_one({"email": req.email.lower().strip()})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No account found with this email.",
        )

    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password.",
        )

    user_id = str(user["_id"])
    token = create_access_token(user_id, user["email"])

    return AuthResponse(
        success=True,
        token=token,
        user=_user_to_response(user),
    )


@app.get("/api/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current authenticated user profile."""
    return {"success": True, "user": current_user}


@app.patch("/api/auth/profile")
async def update_profile(
    req: UpdateProfileRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update user profile fields (onboarding, BMI data, etc.)."""
    coll = users_collection()
    update_fields = {}

    if req.has_completed_onboarding is not None:
        update_fields["has_completed_onboarding"] = req.has_completed_onboarding
    if req.age_category is not None:
        update_fields["age_category"] = req.age_category
    if req.experience_level is not None:
        update_fields["experience_level"] = req.experience_level
    if req.bmi_data is not None:
        update_fields["bmi_data"] = req.bmi_data.model_dump()

    if update_fields:
        update_fields["updated_at"] = datetime.utcnow()
        await coll.update_one(
            {"_id": ObjectId(current_user["id"])},
            {"$set": update_fields},
        )

    updated = await coll.find_one({"_id": ObjectId(current_user["id"])})
    return {"success": True, "user": _user_to_response(updated)}


def _user_to_response(user: dict) -> dict:
    """Convert MongoDB user document to API response dict."""
    return {
        "id": str(user["_id"]),
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "is_account_active": user.get("is_account_active", True),
        "avatar_seed": user.get("avatar_seed", ""),
        "member_since": user.get("member_since", ""),
        "has_completed_onboarding": user.get("has_completed_onboarding", False),
        "age_category": user.get("age_category", ""),
        "experience_level": user.get("experience_level", ""),
        "stats": user.get("stats", {}),
        "bmi_data": user.get("bmi_data"),
    }


# ══════════════════════════════════════════════════════════════════════════════
# YOGA POSES ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/poses")
async def get_all_poses():
    """Get all yoga poses from MongoDB (excludes no_pose)."""
    coll = poses_collection()
    cursor = coll.find({"pose_id": {"$ne": "no_pose"}}).sort("model_class_index", 1)
    poses = []
    async for doc in cursor:
        poses.append(_pose_to_response(doc))
    return {"success": True, "poses": poses}


@app.get("/api/poses/{pose_id}")
async def get_pose(pose_id: str):
    """Get a single yoga pose by ID."""
    coll = poses_collection()
    doc = await coll.find_one({"pose_id": pose_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Pose not found")
    return {"success": True, "pose": _pose_to_response(doc)}


def _pose_to_response(doc: dict) -> dict:
    """Convert MongoDB pose document to API response."""
    return {
        "id": doc.get("pose_id", ""),
        "name": doc.get("name", ""),
        "sanskrit_name": doc.get("sanskrit_name", ""),
        "difficulty": doc.get("difficulty", ""),
        "category": doc.get("category", ""),
        "description": doc.get("description", ""),
        "target_muscles": doc.get("target_muscles", []),
        "benefits": doc.get("benefits", []),
        "wrong_posture_impacts": doc.get("wrong_posture_impacts", []),
        "ideal_hold_duration_seconds": doc.get("ideal_hold_duration_seconds", 45),
        "voice_keywords": doc.get("voice_keywords", []),
        "image_url": doc.get("image_url", ""),
        "key_alignment_checkpoints": doc.get("key_alignment_checkpoints", []),
        "model_class_name": doc.get("model_class_name", ""),
        "model_class_index": doc.get("model_class_index", -1),
    }


# ══════════════════════════════════════════════════════════════════════════════
# SESSION ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/sessions")
async def save_session(
    req: SaveSessionRequest,
    current_user: dict = Depends(get_current_user),
):
    """Save a completed practice session."""
    coll = sessions_collection()
    users = users_collection()

    session_doc = {
        "user_id": current_user["id"],
        "start_time": req.start_time,
        "end_time": req.end_time,
        "total_duration_seconds": req.total_duration_seconds,
        "poses_recorded": [p.model_dump() for p in req.poses_recorded],
        "overall_accuracy": req.overall_accuracy,
        "calories_burned_est": req.calories_burned_est,
        "ai_report": req.ai_report,
        "created_at": datetime.utcnow(),
    }

    result = await coll.insert_one(session_doc)

    # Update user stats
    all_sessions = await coll.find({"user_id": current_user["id"]}).to_list(100)
    total_sess = len(all_sessions)
    total_mins = round(sum(s.get("total_duration_seconds", 0) for s in all_sessions) / 60)
    avg_score = round(sum(s.get("overall_accuracy", 0) for s in all_sessions) / max(total_sess, 1))

    await users.update_one(
        {"_id": ObjectId(current_user["id"])},
        {"$set": {
            "stats.total_sessions": total_sess,
            "stats.total_minutes_practiced": total_mins,
            "stats.average_score": avg_score,
            "updated_at": datetime.utcnow(),
        }},
    )

    return {
        "success": True,
        "session_id": str(result.inserted_id),
        "message": "Session saved successfully.",
    }


@app.get("/api/sessions")
async def get_sessions(current_user: dict = Depends(get_current_user)):
    """Get all sessions for the current user."""
    coll = sessions_collection()
    cursor = coll.find({"user_id": current_user["id"]}).sort("created_at", -1).limit(30)
    sessions = []
    async for doc in cursor:
        sessions.append({
            "id": str(doc["_id"]),
            "user_id": doc.get("user_id", ""),
            "start_time": doc.get("start_time", 0),
            "end_time": doc.get("end_time", 0),
            "total_duration_seconds": doc.get("total_duration_seconds", 0),
            "poses_recorded": doc.get("poses_recorded", []),
            "overall_accuracy": doc.get("overall_accuracy", 0),
            "calories_burned_est": doc.get("calories_burned_est", 0),
            "ai_report": doc.get("ai_report"),
            "created_at": doc.get("created_at", datetime.utcnow()).isoformat(),
        })
    return {"success": True, "sessions": sessions}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str, current_user: dict = Depends(get_current_user)):
    """Get a specific session by ID."""
    coll = sessions_collection()
    try:
        doc = await coll.find_one({"_id": ObjectId(session_id), "user_id": current_user["id"]})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "success": True,
        "session": {
            "id": str(doc["_id"]),
            "user_id": doc.get("user_id", ""),
            "start_time": doc.get("start_time", 0),
            "end_time": doc.get("end_time", 0),
            "total_duration_seconds": doc.get("total_duration_seconds", 0),
            "poses_recorded": doc.get("poses_recorded", []),
            "overall_accuracy": doc.get("overall_accuracy", 0),
            "calories_burned_est": doc.get("calories_burned_est", 0),
            "ai_report": doc.get("ai_report"),
            "created_at": doc.get("created_at", datetime.utcnow()).isoformat(),
        },
    }


@app.post("/api/generate-session-report")
async def generate_session_report(payload: dict):
    """Generate dynamic AI session report with Groq API and past session progress analysis."""
    import urllib.request
    import urllib.error
    import re

    session_data = payload.get("sessionData", {})
    prev_session_data = payload.get("previousSessionData")
    groq_api_key = payload.get("groqApiKey") or os.getenv("GROQ_API_KEY")

    # 1. Try Groq API if key is available
    if groq_api_key:
        try:
            print("[Backend Groq AI] Calling llama-3.3-70b-versatile for human-understandable report...")
            system_prompt = (
                "You are Veda AI, an elite yoga therapist and warm master biomechanics coach for ASANA-SENSE.\n"
                "Communicate in clear, human-understandable, natural language (avoid dense medical jargon).\n"
                "Analyze the user's completed practice session and actual poses performed.\n"
                "If previous session data is provided and they practiced the same pose(s), specifically explain how they improved compared to last time with clear numbers and praise.\n"
                "Give a high-energy, uplifting 'boostingMessage' to inspire them to keep going!\n\n"
                "You MUST return a JSON object with:\n"
                "- overallScore: number (0 to 100)\n"
                "- flexibilityIndex: string (e.g. 'Exceptional Steadiness', 'Proficient Alignment', 'Developing Form')\n"
                "- coreStabilityScore: number (0 to 100)\n"
                "- boostingMessage: string (warm, encouraging 2-3 sentence motivational message)\n"
                "- comparisonWithPrevious: string (clear comparison showing how they improved if repeated pose or progress vs previous session)\n"
                "- keyStrengths: array of 2-3 positive observations on their actual poses\n"
                "- priorityGrowthAreas: array of 2-3 simple, actionable tips on how to improve in plain human language\n"
                "- masterTeacherNote: string (mindful, grounding wisdom from the master yoga teacher)\n"
                "- recommendedNextPoses: array of 3 pose names tailored to progress\n"
                "- poseImprovements: array of objects for each practiced pose with:\n"
                "    - poseName: string\n"
                "    - currentStatus: string (summary of hold steadiness and alignment today)\n"
                "    - actionableTips: array of 2-3 specific cues on how to improve this exact pose next time\n"
                "    - jointSafetyCue: string (anatomical checkpoint to protect knees/lower back/shoulders)\n"
                "- fitnessNutrition: object with:\n"
                "    - immediatePostWorkout: array of 2-3 recovery foods/drinks (e.g., electrolytes, protein smoothie, sprouted moong bowl)\n"
                "    - dailyStaminaFoods: array of 3-4 nutrient-dense foods for flexibility, joint health, and core strength\n"
                "    - foodsToAvoid: array of 2-3 inflammatory foods that hinder flexibility and joint recovery\n"
                "    - hydrationTip: string (cellular hydration guidance for spinal discs & fascia)\n"
                "    - dietSummary: string (warm 2-sentence nutritional advice for practitioner fitness)\n"
            )
            user_prompt = f"Current Session:\n{json.dumps(session_data, indent=2)}\n\n"
            if prev_session_data:
                user_prompt += f"Previous Session for Comparison:\n{json.dumps(prev_session_data, indent=2)}"
            else:
                user_prompt += "First session (baseline certification)."

            req_body = json.dumps({
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.5,
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=req_body,
                headers={
                    "Authorization": f"Bearer {groq_api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "ASANA-SENSE/2.0",
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=12) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                raw_content = res_data["choices"][0]["message"]["content"]
                # Strip markdown code blocks if present
                clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_content.strip(), flags=re.MULTILINE)
                parsed = json.loads(clean_json)
                parsed["aiProvider"] = "Groq (Llama 3.3 70B)"
                return {"success": True, "data": parsed}
        except Exception as e:
            print(f"[Backend Groq AI Error]: {e}")

    # Fallback: Dynamic Biomechanical Heuristics on REAL Poses
    current_poses = session_data.get("posesRecorded") or session_data.get("poses_recorded") or []
    prev_poses = (prev_session_data.get("posesRecorded") or prev_session_data.get("poses_recorded") or []) if prev_session_data else []

    current_score = session_data.get("overallAccuracy") or session_data.get("overall_accuracy") or 92
    prev_score = (prev_session_data.get("overallAccuracy") or prev_session_data.get("overall_accuracy")) if prev_session_data else None

    comparison_text = ""
    has_matched = False

    if current_poses and prev_poses:
        for cp in current_poses:
            cid = cp.get("poseId") or cp.get("pose_id")
            matched = next((p for p in prev_poses if (p.get("poseId") or p.get("pose_id")) == cid), None)
            if matched:
                has_matched = True
                curr_hold = cp.get("durationSeconds") or cp.get("duration_seconds") or 0
                prev_hold = matched.get("durationSeconds") or matched.get("duration_seconds") or 0
                curr_acc = cp.get("accuracyScore") or cp.get("accuracy_score") or 0
                prev_acc = matched.get("accuracyScore") or matched.get("accuracy_score") or 0
                pname = cp.get("poseName") or cp.get("pose_name") or "your pose"
                hdiff = curr_hold - prev_hold
                sdiff = curr_acc - prev_acc
                comparison_text = (
                    f"In your previous practice of {pname}, you held for {prev_hold}s at {prev_acc}% accuracy. "
                    f"In this session, you achieved {curr_hold}s ({'+' if hdiff >= 0 else ''}{hdiff}s) with {curr_acc}% accuracy ({'+' if sdiff >= 0 else ''}{sdiff}%)!"
                )
                break

    if not comparison_text:
        if prev_score is not None:
            diff = current_score - prev_score
            comparison_text = f"Overall session posture efficiency moved from {prev_score}% to {current_score}% ({'+' if diff >= 0 else ''}{diff}% difference) with improved core steadiness!"
        else:
            comparison_text = f"Baseline practice session certified! You established a strong foundational score of {current_score}% accuracy. Repeating these poses in your next session will unlock direct progress tracking."

    boosting_message = (
        f"Phenomenal dedication on the mat! Repeating {current_poses[0].get('poseName', 'your pose') if current_poses else 'your pose'} reinforced your neuromuscular alignment, noticeably reducing micro-wobbles and boosting your continuous hold endurance."
        if has_matched else
        "Outstanding effort today! By stepping onto the mat and completing these structured holds, you activated deep stabilizing muscle chains and built mental calm. Every session compounds your physical resilience!"
    )

    dynamic_strengths = []
    dynamic_pose_improvements = []
    
    # Specific pose improvement knowledge base for the actual yoga poses
    pose_advice_map = {
        "chair": {
            "tips": [
                "Shift your body weight 10-15% further back into your heels so your toes can remain lightly grounded without gripping.",
                "Draw your navel gently toward your lumbar spine to avoid excessive hyperextension in the lower back.",
                "Broaden across your collarbones and glide your shoulder blades down while extending arms overhead."
            ],
            "safety": "Ensure your knees stay behind your toes and remain parallel, avoiding inward valgus collapse."
        },
        "cobra": {
            "tips": [
                "Initiate the spinal extension from the thoracic spine (chest) rather than pushing aggressively through wrists.",
                "Hug your elbows tightly into your ribcage to keep your rotator cuff safely engaged.",
                "Keep the back of your neck long by directing your gaze 3-4 feet forward rather than cranking your chin up."
            ],
            "safety": "Keep your pubic bone firmly anchored to the floor to prevent pinching in the lumbar L4-L5 vertebrae."
        },
        "dog": {
            "tips": [
                "Firmly press through the knuckle pads of your index fingers and thumbs to decompress the median wrist nerve.",
                "Maintain a generous microbend in your knees if hamstrings feel tight, allowing your sit bones to lift higher.",
                "Rotate your outer armpits inward toward your ears to broaden the upper back and stabilize the scapulae."
            ],
            "safety": "Prioritize a straight, lengthened spine over forcing heels flat to the mat."
        },
        "shoulder_stand": {
            "tips": [
                "Walk your hands further down your back towards your shoulder blades to lift your chest into your chin.",
                "Keep your elbows tucked strictly shoulder-width apart without splaying outward on the mat.",
                "Reach upward through the balls of your feet, engaging your inner thighs and glutes."
            ],
            "safety": "CRITICAL: Never turn your head or neck sideways while in shoulder stand; keep your gaze centered on your chest."
        },
        "triangle": {
            "tips": [
                "Hinge strictly from the hip crease rather than rounding sideways through your waist.",
                "Stack your top shoulder and hip directly over the bottom ones as if flattened between two panes of glass.",
                "Engage your core obliques so very little weight rests on your lower hand or shin."
            ],
            "safety": "Maintain a subtle 5-degree micro-bend in the front knee to shield posterior cruciate ligaments."
        },
        "tree": {
            "tips": [
                "Firmly root through all four corners of your standing foot, lifting the inner arch for reflexive stability.",
                "Fix your drishti (unwavering gaze) on a stationary eye-level point 6-8 feet ahead of you.",
                "Hug the outer hip of the standing leg inward toward the midline rather than jutting it out."
            ],
            "safety": "Place the lifted foot on either the inner thigh or calf—never directly against the side of the knee joint."
        },
        "warrior": {
            "tips": [
                "Internally rotate the lifted thigh so both hip points face squarely toward the floor in a level horizontal plane.",
                "Actively drive through the heel of the lifted back leg to activate your gluteus medius and hamstrings.",
                "Create a continuous energetic line of power from your outstretched fingertips back through your flexed heel."
            ],
            "safety": "Keep a soft microbend in the supporting knee to protect the knee capsule from hyperextension."
        }
    }

    for p in current_poses:
        pname = p.get("poseName") or p.get("pose_name") or "Asana"
        pid = (p.get("poseId") or p.get("pose_id") or "").lower()
        bh = p.get("bestHoldSeconds") or p.get("best_hold_seconds") or p.get("durationSeconds") or p.get("duration_seconds") or 15
        acc = p.get("accuracyScore") or p.get("accuracy_score") or 92
        dynamic_strengths.append(f"Solid execution in {pname} with continuous hold of {bh}s and {acc}% joint angle accuracy.")

        # Find matching knowledge
        advice_key = next((k for k in pose_advice_map if k in pid or k in pname.lower()), "tree")
        advice = pose_advice_map[advice_key]

        dynamic_pose_improvements.append({
            "poseName": pname,
            "currentStatus": f"Held for {bh}s with {acc}% biomechanical alignment.",
            "actionableTips": advice["tips"],
            "jointSafetyCue": advice["safety"]
        })

    if not dynamic_strengths:
        dynamic_strengths = [
            "Consistent breath synchronization maintained through transitions.",
            "Pelvis leveling maintained with stable joint alignment.",
        ]
        dynamic_pose_improvements.append({
            "poseName": "Tree Pose Balance (Vrikshasana)",
            "currentStatus": "Strong foundational balance hold certified.",
            "actionableTips": pose_advice_map["tree"]["tips"],
            "jointSafetyCue": pose_advice_map["tree"]["safety"]
        })

    fitness_nutrition = {
        "immediatePostWorkout": [
            "Tender Coconut Water or Himalayan Pink Salt Lemon Water: Immediately replenishes vital electrolytes (potassium, sodium, magnesium) lost through sweat.",
            "Sprouted Moong Dal Salad or Plant Protein Smoothie: High bio-availability plant protein with chia seeds to rebuild muscle fibers and restore glycogen within 45 minutes.",
            "Warm Golden Turmeric Almond Milk: Curcumin reduces joint inflammation and accelerates fascial recovery after deep holds."
        ],
        "dailyStaminaFoods": [
            "Soaked Walnuts & Flaxseeds: Rich in plant-based Omega-3 fatty acids to lubricate synovial joint capsules and maintain ligament elasticity.",
            "Ancient Whole Millets (Ragi / Jowar) & Quinoa: Complex carbohydrates providing slow-burning energy for long yoga sessions without blood sugar spikes.",
            "Fresh Leafy Greens (Palak, Moringa, Methi): Dense in iron, magnesium, and calcium to prevent post-practice muscle cramping.",
            "Sesame Seeds & Soaked Almonds: Essential natural calcium and healthy fats to strengthen bone density for standing balances."
        ],
        "foodsToAvoid": [
            "Refined White Sugar & High-Fructose Syrups: Induces systemic fascial stiffness and delays muscle recovery.",
            "Ultra-Processed Deep-Fried Foods: High in trans fats that impair cellular oxygenation and cause post-practice lethargy.",
            "Excessive Caffeine Immediately Before Practice: Dehydrates spinal intervertebral discs and increases tremors during balance holds."
        ],
        "hydrationTip": "Drink 400-500ml of room-temperature or lukewarm water 30 minutes after your practice. Lukewarm water enhances digestive Agni and cellular hydration for spinal discs.",
        "dietSummary": "Nourish your body with clean, sattvic, whole foods rich in antioxidants and plant proteins. Prioritize deep hydration and anti-inflammatory foods to support joint longevity and muscular vitality."
    }

    return {
        "success": True,
        "data": {
            "overallScore": current_score,
            "flexibilityIndex": "Exceptional Steadiness" if current_score >= 90 else "Proficient Alignment" if current_score >= 80 else "Developing Form",
            "coreStabilityScore": min(100, max(75, current_score - 3)),
            "boostingMessage": boosting_message,
            "comparisonWithPrevious": comparison_text,
            "keyStrengths": dynamic_strengths[:3],
            "priorityGrowthAreas": [
                "Maintain a soft 5° micro-bend in your supporting knees to shield the joint capsule from excessive shear.",
                "Slide your scapulae down the back of your ribcage to neutralize trapezius tension.",
                "Ground evenly through all four corners of your feet for optimal drishti balance.",
            ],
            "poseImprovements": dynamic_pose_improvements,
            "fitnessNutrition": fitness_nutrition,
            "masterTeacherNote": "Consistency creates mastery. The steadiness and mindful presence you cultivated in today's holds will carry directly into your posture and daily energy throughout the week.",
            "recommendedNextPoses": ["Warrior III Pose", "Tree Pose Balance", "Downward-Facing Dog"],
            "aiProvider": "Veda AI Biomechanics Engine",
        }
    }



# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET: REAL-TIME POSE DETECTION
# ══════════════════════════════════════════════════════════════════════════════

@app.websocket("/ws/pose-detect")
async def websocket_pose_detect(websocket: WebSocket):
    """
    Real-time pose detection pipeline via WebSocket.

    Client sends: { "type": "landmarks", "target_pose": "tree", "landmarks": [[x,y], ...] }
    Server responds: { "type": "pose_result", "predicted_pose": ..., "is_correct": ..., "joints": [...], ... }

    Timer logic:
    - "start": all joints correct, pose matches target → timer should start
    - "continue": still correct → timer keeps running
    - "stop": mismatch detected → timer stops, save as attempt
    - "idle": no valid pose or no_pose detected → timer stays idle
    """
    await websocket.accept()
    print("[WS] Client connected for pose detection")

    # Per-connection state for timer action tracking and prediction debouncing
    was_running = False
    mismatch_counter = 0

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = data.get("type", "")
            if msg_type != "landmarks":
                continue

            target_pose = data.get("target_pose", "")
            landmarks = data.get("landmarks", [])

            if not target_pose or len(landmarks) != 33:
                await websocket.send_json({
                    "type": "pose_result",
                    "predicted_pose": "unknown",
                    "confidence": 0,
                    "target_pose": target_pose,
                    "is_correct": False,
                    "has_red": True,
                    "has_yellow": False,
                    "joints": [],
                    "timer_action": "idle",
                    "correction_message": "",
                })
                continue

            try:
                # 1. Classify the pose
                predicted, confidence, probs = pose_engine.classify(landmarks)

                # 2. If predicted is no_pose or confidence too low → idle
                if predicted == "no_pose" or confidence < CONF_THRESHOLD:
                    timer_action = "stop" if was_running else "idle"
                    was_running = False
                    mismatch_counter = 0
                    await websocket.send_json({
                        "type": "pose_result",
                        "predicted_pose": predicted,
                        "confidence": round(confidence, 4),
                        "target_pose": target_pose,
                        "is_correct": False,
                        "has_red": True,
                        "has_yellow": False,
                        "joints": [],
                        "timer_action": timer_action,
                        "correction_message": "",
                    })
                    continue

                # 3. Check if predicted pose matches target
                # Handle model class name mapping (typos in model)
                model_name_map = {
                    "shoulder_stand": "shoudler_stand",
                    "triangle": "traingle",
                }
                target_model_check = model_name_map.get(target_pose, target_pose)

                raw_match = (predicted == target_model_check) and confidence >= CONF_THRESHOLD
                if raw_match:
                    mismatch_counter = 0
                    pose_matches = True
                else:
                    mismatch_counter += 1
                    # Debounce: require 3 consecutive mismatch frames before flagging different pose
                    pose_matches = mismatch_counter < 3

                # 4. Evaluate per-joint correctness
                is_correct, has_yellow, has_red, joints, correction = pose_engine.evaluate_joints(
                    landmarks, target_pose
                )

                # Override: if confirmed wrong pose after debouncing, flag as red
                if not pose_matches:
                    is_correct = False
                    has_red = True
                    correction = f"You're doing {predicted.replace('_', ' ').title()}. Switch to {target_pose.replace('_', ' ').title()}."

                # 5. Determine timer action:
                # Yellow does NOT stop the timer! Timer runs until RED is detected!
                if not has_red:
                    timer_action = "start" if not was_running else "continue"
                    was_running = True
                else:
                    timer_action = "stop" if was_running else "idle"
                    was_running = False

                # 6. Send result
                await websocket.send_json({
                    "type": "pose_result",
                    "predicted_pose": predicted,
                    "confidence": round(confidence, 4),
                    "target_pose": target_pose,
                    "is_correct": is_correct,
                    "has_red": has_red,
                    "has_yellow": has_yellow,
                    "joints": joints,
                    "timer_action": timer_action,
                    "correction_message": correction,
                })

            except Exception as e:
                print(f"[WS] Processing error: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"Processing error: {str(e)}",
                })

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Unexpected error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
