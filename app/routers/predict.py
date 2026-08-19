from fastapi import APIRouter, HTTPException

from app.database import get_poses_collection
from app.ml_model import predict_pose
from app.config import settings
from app.schemas import PredictRequest, PredictResponse, PoseOut

router = APIRouter(prefix="/predict", tags=["predict"])


@router.post("/check", response_model=PredictResponse)
async def check_pose(payload: PredictRequest):
    try:
        predicted_pose, confidence = predict_pose(payload.landmarks)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Low confidence: model itself is unsure, don't trust the mismatch verdict
    if confidence < settings.confidence_threshold:
        return PredictResponse(
            predicted_pose=predicted_pose,
            confidence=confidence,
            is_correct=False,
            message="Low confidence detection. Try adjusting your position so the camera can see you fully.",
            correction=None,
        )

    is_correct = predicted_pose == payload.expected_pose

    if is_correct:
        return PredictResponse(
            predicted_pose=predicted_pose,
            confidence=confidence,
            is_correct=True,
            message="Great job! Your pose matches the expected asana.",
            correction=None,
        )

    # Mistake detected -> fetch the correct reference pose from MongoDB
    collection = get_poses_collection()
    correct_doc = await collection.find_one({"pose_name": payload.expected_pose})

    if not correct_doc:
        return PredictResponse(
            predicted_pose=predicted_pose,
            confidence=confidence,
            is_correct=False,
            message=(
                f"Mismatch detected (looks like '{predicted_pose}' instead of "
                f"'{payload.expected_pose}'), but no reference data was found in the DB "
                f"for '{payload.expected_pose}'."
            ),
            correction=None,
        )

    correct_doc["_id"] = str(correct_doc["_id"])

    return PredictResponse(
        predicted_pose=predicted_pose,
        confidence=confidence,
        is_correct=False,
        message=(
            f"You're doing '{predicted_pose}' but this pose should be "
            f"'{payload.expected_pose}'. Here's the correct reference."
        ),
        correction=PoseOut(**correct_doc),
    )
