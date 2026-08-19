from typing import List, Optional
from pydantic import BaseModel, Field


class PoseBase(BaseModel):
    pose_name: str = Field(..., description="e.g. 'Tadasana', 'Vrikshasana'")
    display_name: Optional[str] = Field(None, description="Human friendly name, e.g. 'Mountain Pose'")
    image_url: Optional[str] = Field(None, description="URL to the reference pose image (e.g. hosted on S3/Cloudinary)")
    image_base64: Optional[str] = Field(None, description="Alternative: base64-encoded image, if not hosting externally")
    description: Optional[str] = Field(None, description="How to correctly perform the pose")
    merits: List[str] = Field(default_factory=list, description="Benefits of the pose")
    demerits: List[str] = Field(default_factory=list, description="Cautions / who should avoid it")


class PoseCreate(PoseBase):
    pass


class PoseOut(PoseBase):
    id: str = Field(..., alias="_id")

    class Config:
        populate_by_name = True


class PredictRequest(BaseModel):
    landmarks: List[float] = Field(
        ..., description="Flattened MediaPipe pose landmarks, e.g. [x1,y1,z1,vis1, x2,y2,z2,vis2, ...]"
    )
    expected_pose: str = Field(..., description="The pose_name the user is currently attempting")


class PredictResponse(BaseModel):
    predicted_pose: str
    confidence: float
    is_correct: bool
    message: str
    correction: Optional[PoseOut] = None
