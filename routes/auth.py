"""
Authentication routes for ASANA-SENSE API.
Handles OTP-verified sign up, sign in, welcome email, me, profile update, and account deletion.

Signup flow (replaces the old single-step /signup):
    1. POST /send-otp    -> validates name/email/password, emails a 6-digit code,
                             holds the pending account (hashed password + encrypted
                             name) in memory for 10 minutes.
    2. POST /verify-otp  -> checks the code, creates the real user in MongoDB,
                             returns a normal JWT session just like signin.
    3. POST /resend-otp  -> issues a fresh code for a still-pending signup.

NOTE: OTP_STORE is in-process memory, matching the original template. It resets
on server restart and is NOT shared across multiple uvicorn workers/processes.
Fine for a single-process dev/demo deployment; swap for Redis before scaling to
multiple workers.
"""
import asyncio
import os
import secrets
import string
import time
from datetime import datetime
from urllib.parse import quote

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from pymongo.errors import DuplicateKeyError

from database import users_collection, sessions_collection
from models import (
    SignUpRequest, SignInRequest, AuthResponse,
    UpdateProfileRequest,
)
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user,
)
from crypto_utils import encrypt_str, decrypt_str, encrypt_bmi, decrypt_bmi
from email_service import send_otp_email, send_welcome_email, send_password_reset_email

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

OTP_TTL_SECONDS = 600  # 10 minutes

# Real bcrypt hash used to keep signin timing equal for unknown emails
_DUMMY_HASH = hash_password("timing-equalizer-not-a-real-password")
# { "email@example.com": { "otp": "123456", "expires_at": <ts>, "name": "...", "pwd_hash": "..." } }
OTP_STORE: dict = {}

OTP_MAX_ATTEMPTS = 5          # wrong guesses allowed per code
OTP_RESEND_COOLDOWN = 30      # seconds between code emails (anti email-bombing)
RESET_TOKEN_TTL_SECONDS = 900  # 15 minutes
# { "reset_token_xyz": { "email": "user@example.com", "expires_at": <ts> } }
RESET_TOKEN_STORE: dict = {}


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str


class ResendOtpRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    email: EmailStr
    new_password: str = Field(..., min_length=6, max_length=128)


def _purge_stale() -> None:
    """Drop expired OTP / reset entries so the in-memory stores can't grow forever."""
    now = time.time()
    for k in [k for k, v in OTP_STORE.items() if now > v["expires_at"] + OTP_RESEND_COOLDOWN]:
        OTP_STORE.pop(k, None)
    for k in [k for k, v in RESET_TOKEN_STORE.items() if now > v["expires_at"]]:
        RESET_TOKEN_STORE.pop(k, None)


def _generate_otp() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))


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
        "is_verified": user.get("is_verified", True),
    }


# ── Step 1: start signup, send the code ─────────────────────────────────────

@router.post("/send-otp")
async def send_otp(req: SignUpRequest):
    """Begin signup: validate, hash the password, email a 6-digit code."""
    coll = users_collection()

    existing = await coll.find_one({"email": req.email.lower().strip()})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Please sign in.",
        )

    email_key = req.email.lower().strip()
    name_plain = req.name.strip()

    _purge_stale()
    pending = OTP_STORE.get(email_key)
    if pending and time.time() - pending["sent_at"] < OTP_RESEND_COOLDOWN:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {OTP_RESEND_COOLDOWN} seconds before requesting another code.",
        )
    otp = _generate_otp()

    # Hash now (bcrypt is CPU-bound — keep it off the event loop) so the
    # plaintext password is never held any longer than this one request.
    pwd_hash = await asyncio.to_thread(hash_password, req.password)

    OTP_STORE[email_key] = {
        "otp": otp,
        "expires_at": time.time() + OTP_TTL_SECONDS,
        "name": name_plain,
        "pwd_hash": pwd_hash,
        "attempts": 0,
        "sent_at": time.time(),
    }

    success, message = await asyncio.to_thread(send_otp_email, req.email, name_plain, otp)
    if not success:
        OTP_STORE.pop(email_key, None)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not send verification email: {message}",
        )

    return {"success": True, "message": f"6-digit code dispatched to {req.email}"}


# ── Step 2: verify the code, actually create the account ────────────────────

@router.post("/verify-otp", response_model=AuthResponse)
async def verify_otp(req: VerifyOtpRequest):
    """Confirm the code and create the real user in MongoDB."""
    email_key = req.email.lower().strip()
    record = OTP_STORE.get(email_key)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending verification found. Please request a new code.",
        )
    if time.time() > record["expires_at"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code expired. Please request a new code.",
        )
    if not secrets.compare_digest(record["otp"], req.otp.strip()):
        record["attempts"] += 1
        if record["attempts"] >= OTP_MAX_ATTEMPTS:
            # Burn the code but keep the record, so the resend cooldown still applies.
            record["expires_at"] = time.time()
            record["sent_at"] = time.time()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many wrong codes. Please request a new code.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid 6-digit verification code.",
        )

    coll = users_collection()
    # Re-check in case the email got taken while the code was pending.
    if await coll.find_one({"email": email_key}):
        OTP_STORE.pop(email_key, None)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Please sign in.",
        )

    now = datetime.utcnow()
    name_plain = record["name"]
    user_doc = {
        "name": encrypt_str(name_plain),
        "email": email_key,
        "password_hash": record["pwd_hash"],
        "is_account_active": True,
        "is_verified": True,
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

    try:
        result = await coll.insert_one(user_doc)
    except DuplicateKeyError:
        OTP_STORE.pop(email_key, None)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Please sign in.",
        )
    user_id = str(result.inserted_id)
    OTP_STORE.pop(email_key, None)

    token = create_access_token(user_id, email_key)

    # Fire-and-forget welcome email — don't make the user wait on a second SMTP round trip.
    asyncio.create_task(_send_welcome_background(req.email, name_plain))

    return AuthResponse(
        success=True,
        token=token,
        user={
            "id": user_id,
            "name": name_plain,
            "email": email_key,
            "is_account_active": True,
            "is_verified": True,
            "avatar_seed": user_doc["avatar_seed"],
            "member_since": user_doc["member_since"],
            "has_completed_onboarding": False,
            "age_category": "",
            "experience_level": "",
            "stats": user_doc["stats"],
            "bmi_data": None,
        },
    )


async def _send_welcome_background(to_email: str, name: str) -> None:
    try:
        await asyncio.to_thread(send_welcome_email, to_email, name)
    except Exception as e:
        print(f"[AuthRoutes] Background welcome email failed for {to_email}: {e}")


# ── Resend ────────────────────────────────────────────────────────────────

@router.post("/resend-otp")
async def resend_otp(req: ResendOtpRequest):
    """Issue a fresh code for a signup that's still pending verification."""
    email_key = req.email.lower().strip()
    record = OTP_STORE.get(email_key)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session expired. Please sign up again.",
        )

    if time.time() - record["sent_at"] < OTP_RESEND_COOLDOWN:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {OTP_RESEND_COOLDOWN} seconds before requesting another code.",
        )

    new_otp = _generate_otp()
    record["otp"] = new_otp
    record["expires_at"] = time.time() + OTP_TTL_SECONDS
    record["attempts"] = 0
    record["sent_at"] = time.time()

    success, message = await asyncio.to_thread(send_otp_email, req.email, record["name"], new_otp)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not send verification email: {message}",
        )

    return {"success": True, "message": "New verification code dispatched"}


# ── Sign in ───────────────────────────────────────────────────────────────

@router.post("/signin", response_model=AuthResponse)
async def signin(req: SignInRequest):
    """Sign in with email and password."""
    coll = users_collection()

    user = await coll.find_one({"email": req.email.lower().strip()})
    # Same error + same work for unknown email and wrong password (no user enumeration).
    # Dummy bcrypt hash of "x" keeps response time similar when the user does not exist.
    stored_hash = user["password_hash"] if user else _DUMMY_HASH
    pw_ok = await asyncio.to_thread(verify_password, req.password, stored_hash)
    if not user or not pw_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    user_id = str(user["_id"])
    token = create_access_token(user_id, user["email"])

    return AuthResponse(
        success=True,
        token=token,
        user=_user_to_response(user),
    )


# ── Forgot / reset password ──────────────────────────────────────────────

@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest):
    """Email a single-use reset link if the account exists."""
    _purge_stale()
    email_key = req.email.lower().strip()
    coll = users_collection()
    user = await coll.find_one({"email": email_key})

    # Same response whether or not the account exists — don't leak which
    # emails are registered.
    generic_response = {
        "success": True,
        "message": f"If an account exists for {req.email}, reset instructions have been dispatched.",
    }
    if not user:
        return generic_response

    reset_token = secrets.token_urlsafe(32)
    RESET_TOKEN_STORE[reset_token] = {
        "email": email_key,
        "expires_at": time.time() + RESET_TOKEN_TTL_SECONDS,
    }

    frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000").split(",")[0].strip()
    reset_url = f"{frontend_origin}/?mode=reset-password&token={reset_token}&email={quote(email_key)}"

    user_name = decrypt_str(user.get("name", "")) or "Yogi"
    success, message = await asyncio.to_thread(send_password_reset_email, req.email, user_name, reset_url)
    if not success:
        RESET_TOKEN_STORE.pop(reset_token, None)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not send reset email: {message}",
        )

    return generic_response


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest):
    """Consume a single-use reset token and update the account's password."""
    token_record = RESET_TOKEN_STORE.get(req.token)

    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset link. Please request a new one.",
        )
    if time.time() > token_record["expires_at"]:
        RESET_TOKEN_STORE.pop(req.token, None)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has expired. Please request a new one.",
        )
    if token_record["email"] != req.email.lower().strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token mismatch with provided email address.",
        )

    coll = users_collection()
    email_key = req.email.lower().strip()
    user = await coll.find_one({"email": email_key})
    if not user:
        RESET_TOKEN_STORE.pop(req.token, None)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account no longer exists.",
        )

    new_hash = await asyncio.to_thread(hash_password, req.new_password)
    await coll.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": new_hash, "updated_at": datetime.utcnow()}},
    )

    # Single-use: burn the token now that it's been redeemed.
    RESET_TOKEN_STORE.pop(req.token, None)

    return {
        "success": True,
        "message": "Your password has been successfully updated. You may now sign in with your new password.",
    }


# ── Welcome email (manual re-trigger, e.g. from a "resend welcome" button) ──

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

    success, message = await asyncio.to_thread(send_welcome_email, to_email, user_name)

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


@router.get("/me")
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


# ── Permanent Account Deletion ─────────────────────────────────────────────

@router.delete("/account")
async def delete_account(
    current_user: dict = Depends(get_current_user),
):
    """
    Permanently deletes the practitioner's account from MongoDB.
    Route: DELETE /api/auth/account
    Headers: Authorization: Bearer <jwt_token>
    """
    coll = users_collection()
    user_id_str = current_user.get("id")

    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user identification.",
        )

    try:
        user_oid = ObjectId(user_id_str)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MongoDB Object ID format.",
        )

    result = await coll.delete_one({"_id": user_oid})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found or already deleted.",
        )
    # Remove the user's practice history too (no orphaned personal data)
    await sessions_collection().delete_many({"user_id": user_id_str})

    return {
        "success": True,
        "message": "Practitioner account and associated credentials have been permanently deleted.",
    }