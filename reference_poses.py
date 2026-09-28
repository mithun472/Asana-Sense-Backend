"""
Compute and store reference pose landmark distributions from training data.
Used for per-joint correctness evaluation.
"""
import os
import numpy as np
import pandas as pd
from typing import Optional

from pose_engine import (
    CLASS_NAMES,
    IDX_LEFT_HIP, IDX_RIGHT_HIP,
    IDX_LEFT_SHOULDER, IDX_RIGHT_SHOULDER,
    N_LANDMARKS,
)


# Column names for x,y of each landmark in the training CSV
LANDMARK_COL_NAMES = [
    "NOSE", "LEFT_EYE_INNER", "LEFT_EYE", "LEFT_EYE_OUTER",
    "RIGHT_EYE_INNER", "RIGHT_EYE", "RIGHT_EYE_OUTER",
    "LEFT_EAR", "RIGHT_EAR", "MOUTH_LEFT", "MOUTH_RIGHT",
    "LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW",
    "LEFT_WRIST", "RIGHT_WRIST", "LEFT_PINKY", "RIGHT_PINKY",
    "LEFT_INDEX", "RIGHT_INDEX", "LEFT_THUMB", "RIGHT_THUMB",
    "LEFT_HIP", "RIGHT_HIP", "LEFT_KNEE", "RIGHT_KNEE",
    "LEFT_ANKLE", "RIGHT_ANKLE", "LEFT_HEEL", "RIGHT_HEEL",
    "LEFT_FOOT_INDEX", "RIGHT_FOOT_INDEX",
]


def normalize_row(row_xy: np.ndarray) -> np.ndarray:
    """
    Apply the same normalization as training: hip-center + torso-scale.
    row_xy: (33, 2) array
    Returns: (66,) normalized flat array
    """
    left_hip = row_xy[IDX_LEFT_HIP]
    right_hip = row_xy[IDX_RIGHT_HIP]
    hip_center = (left_hip + right_hip) * 0.5

    centered = row_xy - hip_center

    left_shoulder = row_xy[IDX_LEFT_SHOULDER]
    right_shoulder = row_xy[IDX_RIGHT_SHOULDER]
    shoulder_center = (left_shoulder + right_shoulder) * 0.5
    torso_size = np.linalg.norm(shoulder_center - hip_center)

    dists = np.linalg.norm(centered, axis=1)
    max_dist = np.max(dists)

    scale = max(torso_size * 2.5, max_dist, 1e-6)
    normalized = centered / scale

    return normalized.flatten().astype(np.float32)


def compute_reference_poses(
    csv_path: str = "../train_landmarks.csv",
) -> dict:
    """
    Read training CSV, normalize each row, compute mean + std per class.
    Returns: { class_name: { "mean": list[float], "std": list[float] } }
    """
    if not os.path.exists(csv_path):
        print(f"[ReferencePoses] Training CSV not found at {csv_path}")
        return {}

    print(f"[ReferencePoses] Loading training data from {csv_path}...")
    df = pd.read_csv(csv_path)

    # Extract x, y columns for each landmark
    x_cols = [f"{name}_x" for name in LANDMARK_COL_NAMES]
    y_cols = [f"{name}_y" for name in LANDMARK_COL_NAMES]

    # Verify columns exist
    missing = [c for c in x_cols + y_cols if c not in df.columns]
    if missing:
        print(f"[ReferencePoses] Missing columns: {missing[:5]}...")
        return {}

    references = {}

    for class_name in CLASS_NAMES:
        if class_name == "no_pose":
            continue

        # Filter rows for this class
        class_df = df[df["class_name"] == class_name]
        if class_df.empty:
            # Try alternate class names from the CSV (handle typos)
            alt_names = {
                "shoulder_stand": "shoudler_stand",
                "triangle": "traingle",
            }
            alt = alt_names.get(class_name, class_name)
            class_df = df[df["class_name"] == alt]

        if class_df.empty:
            print(f"[ReferencePoses] No training data found for class: {class_name}")
            continue

        # Build (N, 33, 2) array and normalize each row
        all_normalized = []
        for _, row in class_df.iterrows():
            xy = np.array(
                [[row[x_col], row[y_col]] for x_col, y_col in zip(x_cols, y_cols)],
                dtype=np.float32,
            )
            norm = normalize_row(xy)
            all_normalized.append(norm)

        all_normalized = np.array(all_normalized)

        mean = np.mean(all_normalized, axis=0)
        std = np.std(all_normalized, axis=0)
        # Clamp std to prevent division by near-zero
        std = np.clip(std, 0.01, None)

        references[class_name] = {
            "mean": mean.tolist(),
            "std": std.tolist(),
        }
        print(
            f"[ReferencePoses] {class_name}: {len(all_normalized)} samples, "
            f"mean_range=[{mean.min():.3f}, {mean.max():.3f}]"
        )

    return references


async def load_or_compute_references(
    csv_path: str = "../train_landmarks.csv",
) -> dict:
    """
    Load references from MongoDB if available, otherwise compute from CSV
    and store in MongoDB.
    """
    from database import reference_poses_collection

    coll = reference_poses_collection()

    # Try loading from DB
    existing = await coll.find_one({"_id": "reference_poses_v1"})
    if existing and "data" in existing:
        print("[ReferencePoses] Loaded from MongoDB cache.")
        return existing["data"]

    # Compute from CSV
    references = compute_reference_poses(csv_path)
    if references:
        await coll.replace_one(
            {"_id": "reference_poses_v1"},
            {"_id": "reference_poses_v1", "data": references},
            upsert=True,
        )
        print("[ReferencePoses] Computed and cached in MongoDB.")

    return references


if __name__ == "__main__":
    # CLI usage: python reference_poses.py
    refs = compute_reference_poses()
    print(f"\nComputed references for {len(refs)} classes:")
    for name, data in refs.items():
        print(f"  {name}: mean_len={len(data['mean'])}, std_len={len(data['std'])}")
