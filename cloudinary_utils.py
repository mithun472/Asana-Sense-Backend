"""
Cloudinary SDK configuration and URL helpers with exact uploaded Cloudinary assets.
"""
import os
import cloudinary
import cloudinary.utils
from dotenv import load_dotenv

load_dotenv()

# Exact Cloudinary URLs uploaded by user
CLOUDINARY_POSE_URLS = {
    "chair": "https://res.cloudinary.com/yhj7u0bn/image/upload/v1789033782/Chair_pose.png",
    "warrior": "https://res.cloudinary.com/yhj7u0bn/image/upload/v1789033718/Warrior-3-Arms-Forward-1200x800.jpg",
    "tree": "https://res.cloudinary.com/yhj7u0bn/image/upload/v1789019346/tree.avif",
    "dog": "https://res.cloudinary.com/yhj7u0bn/image/upload/v1789019346/downdog.jpg",
    "cobra": "https://res.cloudinary.com/yhj7u0bn/image/upload/v1789019345/cobro.avif",
    "shoulder_stand": "https://res.cloudinary.com/yhj7u0bn/image/upload/v1789019345/sholders_stand.jpg",
    "triangle": "https://res.cloudinary.com/yhj7u0bn/image/upload/v1789034482/1lFCiwdr0bqa_JDFaYD84M_TfvJ3RYy5mWpV0UfRTU7xWcEtRjbrG8vNowmL9pK1tWUVWng9jDML5TQJzC3i10hKS3JXMACiD_tV8sScPBGBF-Bhybv1Vw55Hvul60Z9pL09cCrP.jpg"
}

def configure_cloudinary():
    """Initialize Cloudinary SDK from environment variables."""
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    api_key = os.getenv("CLOUDINARY_API_KEY", "")
    api_secret = os.getenv("CLOUDINARY_API_SECRET", "")

    if cloud_name and api_key and api_secret:
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True,
        )
        print(f"[Cloudinary] Configured for cloud: {cloud_name}")
        return True
    else:
        print("[Cloudinary] WARNING: credentials not set; SDK not configured (static URLs still work).")
        return False


def get_pose_image_url(pose_id: str, cloud_name: str = "") -> str:
    """
    Generate or retrieve the exact Cloudinary URL for a pose image.
    Uses the user's specific uploaded Cloudinary URLs first.
    """
    if pose_id in CLOUDINARY_POSE_URLS:
        return CLOUDINARY_POSE_URLS[pose_id]

    cn = cloud_name or os.getenv("CLOUDINARY_CLOUD_NAME", "yhj7u0bn")
    return (
        f"https://res.cloudinary.com/{cn}/image/upload"
        f"/c_fill,w_800,h_600,q_auto,f_auto"
        f"/{pose_id}.jpg"
    )
