"""
Yoga poses routes for ASANA-SENSE API.
Handles retrieval of all yoga poses and individual pose details.
"""
from fastapi import APIRouter, HTTPException
from database import poses_collection

router = APIRouter(prefix="/api/poses", tags=["Yoga Poses"])


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


@router.get("", include_in_schema=True)
@router.get("/", include_in_schema=False)
async def get_all_poses():
    """Get all yoga poses from MongoDB (excludes no_pose)."""
    coll = poses_collection()
    cursor = coll.find({"pose_id": {"$ne": "no_pose"}}).sort("model_class_index", 1)
    poses = []
    async for doc in cursor:
        poses.append(_pose_to_response(doc))
    return {"success": True, "poses": poses}


@router.get("/{pose_id}")
async def get_pose(pose_id: str):
    """Get a single yoga pose by ID."""
    coll = poses_collection()
    doc = await coll.find_one({"pose_id": pose_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Pose not found")
    return {"success": True, "pose": _pose_to_response(doc)}
