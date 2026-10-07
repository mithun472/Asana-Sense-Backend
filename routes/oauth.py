"""
Google + Microsoft sign-in for ASANA-SENSE.

Flow
    Frontend gets an ID token from Google / Microsoft and POSTs it here.
    We verify signature, audience, issuer and expiry ourselves, then find or
    create the user and return the same AuthResponse that /signin returns.
    Nothing the client says about itself (email, name) is trusted; only the
    claims inside the verified token are used.

Account rules
    * Google: email must have email_verified = true.
    * Microsoft: personal accounts are accepted. Work/school (Entra) accounts
      are accepted only if the token carries xms_edov = true (email domain
      owner verified), because Entra lets a tenant admin put ANY address in the
      email claim. Without this check someone could take over an existing
      account by registering a tenant with the victim's email.
    * An existing account with the same email is linked, not duplicated.
      That is safe because password accounts were verified by OTP.
    * New OAuth accounts get a random unusable password. The user can set a
      real one later through the normal forgot-password flow.

No new dependencies: verification uses python-jose (already in requirements)
and urllib from the standard library for the public key sets.

Env vars
    GOOGLE_CLIENT_ID      Google OAuth "Web application" client ID
    MICROSOFT_CLIENT_ID   Azure app registration (Application/client) ID
"""
import asyncio
import json
import os
import re
import secrets
import time
import urllib.request
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from database import users_collection
from auth import hash_password, create_access_token
from crypto_utils import encrypt_str
from models import AuthResponse
from .auth import _user_to_response, _send_welcome_background

router = APIRouter(prefix="/api/auth", tags=["OAuth"])

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")

MS_JWKS_URL = "https://login.microsoftonline.com/common/discovery/v2.0/keys"
MS_PERSONAL_TENANT = "9188040d-6c67-4c5b-b112-36a304b66dad"
_GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")

_JWKS_TTL = 3600          # seconds a key set stays cached
_JWKS_MIN_REFETCH = 60    # never refetch more often than this (random-kid abuse)
_jwks_cache: dict = {}    # url -> (fetched_at, keys)


class OAuthRequest(BaseModel):
    credential: str = Field(..., min_length=20, max_length=8192)


# ── Token verification ───────────────────────────────────────────────────────

def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "asana-sense-backend"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def _find_key(jwks_url: str, kid: str):
    now = time.time()
    cached = _jwks_cache.get(jwks_url)
    stale = cached is None or now - cached[0] > _JWKS_TTL

    async def refresh():
        try:
            data = await asyncio.to_thread(_fetch_json, jwks_url)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not reach the sign-in provider. Please try again.",
            )
        _jwks_cache[jwks_url] = (time.time(), data.get("keys", []))

    if stale:
        await refresh()

    keys = _jwks_cache[jwks_url][1]
    for k in keys:
        if k.get("kid") == kid:
            return k

    # Unknown kid: the provider may have rotated keys. Refetch once, rate limited.
    if time.time() - _jwks_cache[jwks_url][0] > _JWKS_MIN_REFETCH:
        await refresh()
        for k in _jwks_cache[jwks_url][1]:
            if k.get("kid") == kid:
                return k
    return None


def _bad_token() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sign-in token is invalid or has expired. Please try again.",
    )


async def _verify_id_token(token: str, jwks_url: str, audience: str) -> dict:
    """Verify RS256 signature, audience and expiry. Issuer is checked by callers."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        raise _bad_token()
    if header.get("alg") != "RS256" or not header.get("kid"):
        raise _bad_token()

    key = await _find_key(jwks_url, header["kid"])
    if key is None:
        raise _bad_token()

    try:
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=audience,
            options={"verify_at_hash": False, "leeway": 30},
        )
    except JWTError:
        raise _bad_token()


async def _verify_google(credential: str) -> tuple[str, str]:
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured on the server.",
        )
    claims = await _verify_id_token(credential, GOOGLE_JWKS_URL, client_id)
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise _bad_token()

    email = (claims.get("email") or "").strip().lower()
    if not email or claims.get("email_verified") not in (True, "true"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Google has not verified this email address.",
        )
    return email, (claims.get("name") or "").strip()


async def _verify_microsoft(credential: str) -> tuple[str, str]:
    client_id = os.getenv("MICROSOFT_CLIENT_ID", "").strip()
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Microsoft sign-in is not configured on the server.",
        )
    claims = await _verify_id_token(credential, MS_JWKS_URL, client_id)

    # Multi-tenant app: the issuer must match the tenant the token says it is from.
    tid = str(claims.get("tid") or "")
    if not _GUID_RE.match(tid) or claims.get("iss") != f"https://login.microsoftonline.com/{tid}/v2.0":
        raise _bad_token()

    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your Microsoft account did not share an email address.",
        )

    is_personal = tid.lower() == MS_PERSONAL_TENANT
    edov = claims.get("xms_edov")
    domain_verified = edov is True or str(edov).lower() in ("1", "true")
    if not (is_personal or domain_verified):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This work or school account's email can't be verified. "
                   "Use Google or sign up with email instead.",
        )
    return email, (claims.get("name") or "").strip()


# ── Find or create the user ──────────────────────────────────────────────────

async def _sign_in_verified_email(email: str, name: str, provider: str, _retry: bool = True) -> AuthResponse:
    coll = users_collection()
    user = await coll.find_one({"email": email})
    is_new = False

    if user:
        if not user.get("is_account_active", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )
        await coll.update_one(
            {"_id": user["_id"]},
            {"$addToSet": {"oauth_providers": provider}, "$set": {"updated_at": datetime.utcnow()}},
        )
    else:
        now = datetime.utcnow()
        display = (name or email.split("@")[0]).strip()[:100] or "Practitioner"
        # Random password nobody knows: password sign-in can't work until the
        # user sets one via forgot-password.
        pwd_hash = await asyncio.to_thread(hash_password, secrets.token_urlsafe(32))
        user = {
            "name": encrypt_str(display),
            "email": email,
            "password_hash": pwd_hash,
            "is_account_active": True,
            "is_verified": True,
            "oauth_providers": [provider],
            "avatar_seed": display[:2].upper(),
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
            result = await coll.insert_one(user)
        except DuplicateKeyError:
            # Two sign-ins raced; the other one created it. Take the link path.
            if _retry:
                return await _sign_in_verified_email(email, name, provider, _retry=False)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Please try again.")
        user["_id"] = result.inserted_id
        is_new = True

    if is_new:
        asyncio.create_task(_send_welcome_background(email, display))

    token = create_access_token(str(user["_id"]), email)
    return AuthResponse(success=True, token=token, user=_user_to_response(user))


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/oauth-google", response_model=AuthResponse)
async def oauth_google(req: OAuthRequest):
    email, name = await _verify_google(req.credential)
    return await _sign_in_verified_email(email, name, "google")


@router.post("/oauth-microsoft", response_model=AuthResponse)
async def oauth_microsoft(req: OAuthRequest):
    email, name = await _verify_microsoft(req.credential)
    return await _sign_in_verified_email(email, name, "microsoft")
