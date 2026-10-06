"""
Session routes for ASANA-SENSE API.
Handles saving completed practice sessions and retrieving user session history.
"""
from datetime import datetime
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from database import users_collection, sessions_collection
from models import SaveSessionRequest
from auth import get_current_user

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])


@router.post("", include_in_schema=True)
@router.post("/", include_in_schema=False)
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
    agg = await coll.aggregate([
        {"$match": {"user_id": current_user["id"]}},
        {"$group": {
            "_id": None,
            "count": {"$sum": 1},
            "duration": {"$sum": {"$ifNull": ["$total_duration_seconds", 0]}},
            "accuracy": {"$sum": {"$ifNull": ["$overall_accuracy", 0]}},
        }},
    ]).to_list(1)
    totals = agg[0] if agg else {"count": 0, "duration": 0, "accuracy": 0}
    total_sess = totals["count"]
    total_mins = round(totals["duration"] / 60)
    avg_score = round(totals["accuracy"] / max(total_sess, 1))

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


@router.get("", include_in_schema=True)
@router.get("/", include_in_schema=False)
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


@router.get("/{session_id}")
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
