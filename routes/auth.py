"""
Authentication routes for ASANA-SENSE API.
Handles sign up, sign in, me, and profile update.
"""
from datetime import datetime
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
 
from database import users_collection
from models import (
    SignUpRequest, SignInRequest, AuthResponse,
    UpdateProfileRequest,
)
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user,
)
from crypto_utils import encrypt_str, decrypt_str, encrypt_bmi, decrypt_bmi
 
router = APIRouter(prefix="/api/auth", tags=["Authentication"])
 
 
def _user_to_response(user: dict) -> dict:
    """Convert MongoDB user document to API response dict."""
    return {
        "id": str(user["_id"]),
        "name": decrypt_str(user.get("name", "")),
        "email": user.get("email", ""),
        "is_account_active": user.get("is_account_active", True),
        "avatar_seed": user.get("avatar_seed", ""),
        "member_since": user.get("member_since", ""),
        "has_completed_onboarding": user.get("has_completed_onboarding", False),
        "age_category": user.get("age_category", ""),
        "experience_level": user.get("experience_level", ""),
        "stats": user.get("stats", {}),
        "bmi_data": decrypt_bmi(user.get("bmi_data")),
    }
 
 
@router.post("/signup", response_model=AuthResponse)
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
    name_plain = req.name.strip()
    user_doc = {
        "name": encrypt_str(name_plain),
        "email": req.email.lower().strip(),
        "password_hash": await asyncio.to_thread(hash_password, req.password),
        "is_account_active": True,
        "avatar_seed": name_plain[:2].upper(),
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
            "name": name_plain,
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
 
 
@router.post("/signin", response_model=AuthResponse)
async def signin(req: SignInRequest):
    """Sign in with email and password."""
    coll = users_collection()
 
    user = await coll.find_one({"email": req.email.lower().strip()})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No account found with this email.",
        )
 
    if not await asyncio.to_thread(verify_password, req.password, user["password_hash"]):
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


@router.post("/send-welcome-email")
async def send_welcome_email_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """Send a welcome email to the authenticated user's registered email."""
    to_email = current_user.get("email", "")
    user_name = current_user.get("name", "Yogi")

    if not to_email or "@" not in to_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid email address found on account. Please update your profile.",
        )

    loop = asyncio.get_event_loop()
    success, message = await loop.run_in_executor(
        None,
        send_welcome_email,
        to_email,
        user_name,
    )

    if success:
        return {
            "success": True,
            "message": f"Welcome email sent to {to_email}",
            "to_email": to_email,
        }

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Failed to send welcome email: {message}",
    )


router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current authenticated user profile."""
    return {"success": True, "user": current_user}
 
 
@router.patch("/profile")
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
        update_fields["bmi_data"] = encrypt_bmi(req.bmi_data.model_dump())
 
    if update_fields:
        update_fields["updated_at"] = datetime.utcnow()
        await coll.update_one(
            {"_id": ObjectId(current_user["id"])},
            {"$set": update_fields},
        )
 
    updated = await coll.find_one({"_id": ObjectId(current_user["id"])})
    return {"success": True, "user": _user_to_response(updated)}