from fastapi import APIRouter, HTTPException
from bson import ObjectId
from bson.errors import InvalidId

from app.database import get_poses_collection
from app.schemas import PoseCreate, PoseOut

router = APIRouter(prefix="/poses", tags=["poses"])


def _serialize(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("", response_model=list[PoseOut])
async def list_poses():
    collection = get_poses_collection()
    docs = await collection.find().to_list(length=100)
    return [_serialize(d) for d in docs]


@router.get("/{pose_name}", response_model=PoseOut)
async def get_pose(pose_name: str):
    collection = get_poses_collection()
    doc = await collection.find_one({"pose_name": pose_name})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Pose '{pose_name}' not found")
    return _serialize(doc)


@router.post("", response_model=PoseOut, status_code=201)
async def create_pose(pose: PoseCreate):
    collection = get_poses_collection()
    existing = await collection.find_one({"pose_name": pose.pose_name})
    if existing:
        raise HTTPException(status_code=409, detail=f"Pose '{pose.pose_name}' already exists")
    result = await collection.insert_one(pose.model_dump())
    doc = await collection.find_one({"_id": result.inserted_id})
    return _serialize(doc)


@router.put("/{pose_name}", response_model=PoseOut)
async def update_pose(pose_name: str, pose: PoseCreate):
    collection = get_poses_collection()
    result = await collection.find_one_and_update(
        {"pose_name": pose_name},
        {"$set": pose.model_dump()},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Pose '{pose_name}' not found")
    return _serialize(result)


@router.delete("/{pose_name}", status_code=204)
async def delete_pose(pose_name: str):
    collection = get_poses_collection()
    result = await collection.delete_one({"pose_name": pose_name})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Pose '{pose_name}' not found")
