"""
Pydantic models for request/response schemas and MongoDB documents.
"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime


# ── Auth Models ───────────────────────────────────────────────────────────────

class SignUpRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=5, max_length=200)
    password: str = Field(..., min_length=6, max_length=128)


class SignInRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    success: bool
    token: str
    user: dict


# ── User Models ───────────────────────────────────────────────────────────────

class UserStats(BaseModel):
    total_sessions: int = 0
    total_minutes_practiced: int = 0
    average_score: float = 0
    favorite_pose: str = ""


class BmiData(BaseModel):
    weight_kg: float = 0
    height_cm: float = 0
    age: int = 0
    gender: str = ""
    bmi_value: float = 0
    bmi_category: str = ""
    dietary_preference: str = ""
    calculated_at: str = ""


class UserDocument(BaseModel):
    """MongoDB User document schema."""
    name: str
    email: str
    password_hash: str
    is_account_active: bool = True
    avatar_seed: str = ""
    member_since: str = ""
    has_completed_onboarding: bool = False
    age_category: str = ""
    experience_level: str = ""
    stats: UserStats = UserStats()
    bmi_data: Optional[BmiData] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UserProfileResponse(BaseModel):
    """User profile returned to frontend (no password hash)."""
    id: str
    name: str
    email: str
    is_account_active: bool = True
    avatar_seed: str = ""
    member_since: str = ""
    has_completed_onboarding: bool = False
    age_category: str = ""
    experience_level: str = ""
    stats: UserStats = UserStats()
    bmi_data: Optional[BmiData] = None


class UpdateProfileRequest(BaseModel):
    has_completed_onboarding: Optional[bool] = None
    age_category: Optional[str] = None
    experience_level: Optional[str] = None
    bmi_data: Optional[BmiData] = None


# ── Yoga Pose Models ──────────────────────────────────────────────────────────

class WrongPostureImpact(BaseModel):
    mistake: str
    impact: str
    correction: str


class YogaPoseDocument(BaseModel):
    """MongoDB Yoga Pose document schema."""
    pose_id: str  # e.g. 'tree', 'warrior', 'chair'
    name: str
    sanskrit_name: str
    difficulty: str  # 'Beginner' | 'Intermediate' | 'Advanced'
    category: str
    description: str
    target_muscles: list[str] = []
    benefits: list[str] = []
    wrong_posture_impacts: list[WrongPostureImpact] = []
    ideal_hold_duration_seconds: int = 45
    voice_keywords: list[str] = []
    image_url: str = ""  # Cloudinary URL
    key_alignment_checkpoints: list[str] = []
    model_class_name: str = ""  # class name in the TFLite model
    model_class_index: int = -1  # class index in the TFLite model


class YogaPoseResponse(BaseModel):
    """Pose data returned to frontend."""
    id: str
    name: str
    sanskrit_name: str
    difficulty: str
    category: str
    description: str
    target_muscles: list[str] = []
    benefits: list[str] = []
    wrong_posture_impacts: list[WrongPostureImpact] = []
    ideal_hold_duration_seconds: int = 45
    voice_keywords: list[str] = []
    image_url: str = ""
    key_alignment_checkpoints: list[str] = []
    model_class_name: str = ""
    model_class_index: int = -1


# ── Joint Status Models ──────────────────────────────────────────────────────

class JointStatus(BaseModel):
    index: int
    name: str
    status: str  # "correct" | "warning" | "misaligned" | "critical"
    deviation: float = 0.0


class PoseDetectionResult(BaseModel):
    """WebSocket response for each frame."""
    predicted_pose: str
    confidence: float
    target_pose: str
    is_correct: bool
    has_red: bool = False
    has_yellow: bool = False
    joints: list[JointStatus] = []
    timer_action: str  # "start" | "stop" | "continue" | "idle"
    correction_message: str = ""


# ── Session Models ────────────────────────────────────────────────────────────

class SessionPoseRecord(BaseModel):
    pose_id: str
    pose_name: str
    sanskrit_name: str
    duration_seconds: float = 0
    best_hold_seconds: float = 0
    attempts_count: int = 0
    accuracy_score: float = 0
    cues_received: list[str] = []
    status: str = "completed"  # "completed" | "skipped" | "practicing"


class SessionDocument(BaseModel):
    """MongoDB Session document schema."""
    user_id: str
    start_time: float
    end_time: float = 0
    total_duration_seconds: float = 0
    poses_recorded: list[SessionPoseRecord] = []
    overall_accuracy: float = 0
    calories_burned_est: float = 0
    ai_report: Optional[dict] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SaveSessionRequest(BaseModel):
    start_time: float
    end_time: float = 0
    total_duration_seconds: float = 0
    poses_recorded: list[SessionPoseRecord] = []
    overall_accuracy: float = 0
    calories_burned_est: float = 0
    ai_report: Optional[dict] = None


class SessionResponse(BaseModel):
    id: str
    user_id: str
    start_time: float
    end_time: float = 0
    total_duration_seconds: float = 0
    poses_recorded: list[SessionPoseRecord] = []
    overall_accuracy: float = 0
    calories_burned_est: float = 0
    ai_report: Optional[dict] = None
    created_at: str = ""


# ── WebSocket Messages ────────────────────────────────────────────────────────

class LandmarkFrame(BaseModel):
    """Incoming WebSocket message with landmarks."""
    type: str = "landmarks"
    target_pose: str  # model class name e.g. 'tree', 'warrior'
    landmarks: list[list[float]]  # [[x0, y0], [x1, y1], ..., [x32, y32]]
