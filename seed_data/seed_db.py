"""
Run once to populate MongoDB Atlas with your 5 reference poses.

Usage:
    python seed_data/seed_db.py

Edit the POSES list below: swap in your own image_url (host on Cloudinary/S3/
imgur/GitHub, etc.) or base64 image data, plus real merits/demerits copy.
"""

import os
import sys
from pymongo import MongoClient
from dotenv import load_dotenv

# allow running this script directly from project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "asana_sense")
COLLECTION = os.getenv("POSES_COLLECTION", "poses")

POSES = [
    {
        "pose_name": "Tadasana",
        "display_name": "Mountain Pose",
        "image_url": "https://example.com/images/tadasana.jpg",
        "description": "Stand tall, feet together, weight evenly balanced, spine straight, "
                        "shoulders relaxed, arms at sides, gaze forward.",
        "merits": [
            "Improves posture",
            "Strengthens thighs, knees, and ankles",
            "Increases body awareness",
        ],
        "demerits": [
            "Avoid prolonged standing if you have low blood pressure",
            "Be cautious with insomnia or headache",
        ],
    },
    {
        "pose_name": "Vrikshasana",
        "display_name": "Tree Pose",
        "image_url": "https://example.com/images/vrikshasana.jpg",
        "description": "Balance on one leg, place the sole of the other foot on the inner "
                        "thigh or calf (not the knee), hands in prayer position or overhead.",
        "merits": [
            "Improves balance and focus",
            "Strengthens legs and core",
            "Opens hips",
        ],
        "demerits": [
            "Avoid with low blood pressure or migraine",
            "Go carefully with knee injuries",
        ],
    },
    {
        "pose_name": "Adho Mukha Svanasana",
        "display_name": "Downward Facing Dog",
        "image_url": "https://example.com/images/downward_dog.jpg",
        "description": "Hands and feet on the mat, hips lifted high, body forming an "
                        "inverted V, heels reaching toward the floor.",
        "merits": [
            "Stretches shoulders, hamstrings, calves",
            "Strengthens arms and legs",
            "Relieves back pain",
        ],
        "demerits": [
            "Avoid with carpal tunnel syndrome",
            "Avoid in late pregnancy or high blood pressure",
        ],
    },
    {
        "pose_name": "Bhujangasana",
        "display_name": "Cobra Pose",
        "image_url": "https://example.com/images/bhujangasana.jpg",
        "description": "Lie face down, palms under shoulders, lift chest using back muscles "
                        "while keeping the pelvis on the floor.",
        "merits": [
            "Strengthens the spine",
            "Opens chest and lungs",
            "Relieves stress and fatigue",
        ],
        "demerits": [
            "Avoid with back injury or recent abdominal surgery",
            "Avoid during pregnancy",
        ],
    },
    {
        "pose_name": "Trikonasana",
        "display_name": "Triangle Pose",
        "image_url": "https://example.com/images/trikonasana.jpg",
        "description": "Feet wide apart, one foot turned out, reach down to shin/ankle/floor "
                        "on that side while the opposite arm reaches up, forming a triangle.",
        "merits": [
            "Stretches legs, hips, spine",
            "Improves digestion",
            "Reduces stress",
        ],
        "demerits": [
            "Avoid with neck problems (keep gaze forward instead of up)",
            "Go carefully with low or high blood pressure",
        ],
    },
]


def main():
    if not MONGO_URI:
        raise SystemExit("MONGO_URI not set. Copy .env.example to .env and fill it in.")

    client = MongoClient(MONGO_URI)
    collection = client[DB_NAME][COLLECTION]
    collection.create_index("pose_name", unique=True)

    for pose in POSES:
        collection.update_one(
            {"pose_name": pose["pose_name"]},
            {"$set": pose},
            upsert=True,
        )
        print(f"Upserted: {pose['pose_name']}")

    print(f"Done. {collection.count_documents({})} poses in '{DB_NAME}.{COLLECTION}'.")


if __name__ == "__main__":
    main()
