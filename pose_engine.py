"""
TFLite pose classifier + landmark normalization + per-joint evaluation.
Mirrors the exact normalization logic from yoga_pose_detector.py.

Interpreter priority (all run the same .tflite model):
  1. ai_edge_litert  (Google LiteRT, lightweight, used in Docker/Render)
  2. tflite_runtime  (legacy standalone runtime)
  3. tensorflow.lite (full TensorFlow, local dev fallback)
"""
import os
import math
import logging
import threading
import numpy as np
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("pose_engine")

# ── Constants ─────────────────────────────────────────────────────────────────
IDX_LEFT_HIP = 23
IDX_RIGHT_HIP = 24
IDX_LEFT_SHOULDER = 11
IDX_RIGHT_SHOULDER = 12
N_LANDMARKS = 33

CLASS_NAMES = [
    "chair", "cobra", "dog", "no_pose",
    "shoulder_stand", "triangle", "tree", "warrior"
]

# Confidence threshold to declare pose is detected
CONF_THRESHOLD = 0.6

# Joint deviation threshold (in normalized units) to flag as misaligned
JOINT_DEVIATION_THRESHOLD = 0.12

# Floor for per-joint std when scoring (avoids division by ~0)
MIN_STD = 0.02

# Deviation assigned when math goes non-finite (treated as critical, JSON-safe)
MAX_DEVIATION = 99.0

# Human-readable names for the 33 MediaPipe landmarks
LANDMARK_NAMES = [
    "nose", "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear", "mouth_left", "mouth_right",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky",
    "left_index", "right_index", "left_thumb", "right_thumb",
    "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle", "left_heel", "right_heel",
    "left_foot_index", "right_foot_index",
]

# Key joints to evaluate for pose correctness (skip face landmarks)
KEY_JOINT_INDICES = [
    11, 12,  # shoulders
    13, 14,  # elbows
    15, 16,  # wrists
    23, 24,  # hips
    25, 26,  # knees
    27, 28,  # ankles
    29, 30,  # heels
    31, 32,  # foot indices
]


def _create_interpreter(model_path: str):
    """
    Build a TFLite interpreter using the lightest available backend.
    Returns: (interpreter, backend_name)
    """
    # 1. Google LiteRT (pip install ai-edge-litert)
    try:
        from ai_edge_litert.interpreter import Interpreter
        return Interpreter(model_path=model_path), "ai_edge_litert"
    except ImportError:
        pass

    # 2. Legacy standalone tflite_runtime
    try:
        from tflite_runtime.interpreter import Interpreter
        return Interpreter(model_path=model_path), "tflite_runtime"
    except ImportError:
        pass

    # 3. Full TensorFlow (local development only)
    try:
        import tensorflow as tf
        return tf.lite.Interpreter(model_path=model_path), "tensorflow.lite"
    except ImportError:
        pass

    raise RuntimeError(
        "No TFLite interpreter available. Install one of: "
        "ai-edge-litert (recommended), tflite-runtime, or tensorflow."
    )


class PoseEngine:
    """
    Loads the TFLite yoga pose classifier and provides:
    - Landmark normalization (matching training pipeline)
    - Pose classification
    - Per-joint correctness evaluation against reference poses
    """
    def __init__(self, model_path: Optional[str] = None):
        env_path = os.getenv("TFLITE_MODEL_PATH")
        if model_path and os.path.exists(model_path):
            self._model_path = model_path
        elif env_path and os.path.exists(env_path):
            self._model_path = env_path
        elif os.path.exists("../ml/models/yoga_pose_classifier.tflite"):
            self._model_path = "../ml/models/yoga_pose_classifier.tflite"
        elif os.path.exists("ml/models/yoga_pose_classifier.tflite"):
            self._model_path = "ml/models/yoga_pose_classifier.tflite"
        elif os.path.exists("../yoga_pose_classifier.tflite"):
            self._model_path = "../yoga_pose_classifier.tflite"
        else:
            self._model_path = env_path or "../yoga_pose_classifier.tflite"
        self._interpreter = None
        self._backend_name: Optional[str] = None
        # TFLite interpreters are NOT thread-safe: serialize set_tensor/invoke/get_tensor.
        self._lock = threading.Lock()
        self._input_details = None
        self._output_details = None
        self._warned_missing: set = set()
        self._reference_poses: dict = {}  # {class_name: {mean: np.array, std: np.array}}

    @property
    def is_ready(self) -> bool:
        return self._interpreter is not None

    @property
    def backend_name(self) -> Optional[str]:
        """Which interpreter backend is in use (None until load_model succeeds)."""
        return self._backend_name

    def has_reference(self, pose: str) -> bool:
        return pose in self._reference_poses

    def load_model(self):
        """Load the TFLite model (LiteRT -> tflite_runtime -> TensorFlow)."""
        self._interpreter, self._backend_name = _create_interpreter(self._model_path)

        self._interpreter.allocate_tensors()
        self._input_details = self._interpreter.get_input_details()[0]
        self._output_details = self._interpreter.get_output_details()[0]
        print(
            f"[PoseEngine] Model loaded via {self._backend_name} — "
            f"input shape: {self._input_details['shape']}, "
            f"output classes: {len(CLASS_NAMES)}"
        )

    def set_reference_poses(self, references: dict):
        """
        Set reference pose landmark distributions.
        references: { class_name: { "mean": [66 floats], "std": [66 floats] } }
        """
        self._reference_poses = {}
        for class_name, data in references.items():
            mean = np.array(data["mean"], dtype=np.float32)
            std = np.array(data["std"], dtype=np.float32)
            if not (np.isfinite(mean).all() and np.isfinite(std).all()):
                logger.warning("Reference for %s had NaN/inf values; sanitized.", class_name)
            mean = np.nan_to_num(mean, nan=0.0, posinf=0.0, neginf=0.0)
            std = np.nan_to_num(std, nan=0.05, posinf=0.05, neginf=0.05)
            std = np.clip(std, MIN_STD, None)
            self._reference_poses[class_name] = {"mean": mean, "std": std}
        print(f"[PoseEngine] Reference poses loaded for: {list(self._reference_poses.keys())}")

    @staticmethod
    def normalize_landmarks(lm_xy: np.ndarray) -> np.ndarray:
        """
        Normalize 33x2 landmarks exactly as in training pipeline.
        lm_xy: (33, 2) array of (x, y) coordinates
        Returns: (66,) normalized flat embedding
        """
        left_hip = lm_xy[IDX_LEFT_HIP]
        right_hip = lm_xy[IDX_RIGHT_HIP]
        hip_center = (left_hip + right_hip) * 0.5

        # Center on hip midpoint
        centered = lm_xy - hip_center

        # Compute torso size
        left_shoulder = lm_xy[IDX_LEFT_SHOULDER]
        right_shoulder = lm_xy[IDX_RIGHT_SHOULDER]
        shoulder_center = (left_shoulder + right_shoulder) * 0.5
        torso_size = np.linalg.norm(shoulder_center - hip_center)

        # Max distance from center
        dists = np.linalg.norm(centered, axis=1)
        max_dist = np.max(dists)

        scale = max(torso_size * 2.5, max_dist, 1e-6)
        normalized = centered / scale

        return normalized.flatten().astype(np.float32)  # (66,)

    def classify(self, landmarks_xy: list[list[float]]) -> tuple[str, float, np.ndarray]:
        """
        Classify a pose from 33 (x, y) landmarks.
        Returns: (predicted_class_name, confidence, all_probabilities)
        """
        if self._interpreter is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        lm_xy = np.array(landmarks_xy, dtype=np.float32)
        if lm_xy.shape != (33, 2):
            raise ValueError(f"Expected (33, 2) landmarks, got {lm_xy.shape}")

        embedding = self.normalize_landmarks(lm_xy)
        inp = np.expand_dims(embedding, axis=0).astype(np.float32)

        with self._lock:
            self._interpreter.set_tensor(self._input_details["index"], inp)
            self._interpreter.invoke()
            # copy: the interpreter reuses its output buffer on the next call
            probs = self._interpreter.get_tensor(self._output_details["index"])[0].copy()

        top_idx = int(np.argmax(probs))
        top_conf = float(probs[top_idx])
        top_name = CLASS_NAMES[top_idx]

        return top_name, top_conf, probs

    def evaluate_joints(
        self,
        landmarks_xy: list[list[float]],
        target_pose: str,
    ) -> tuple[bool, bool, bool, list[dict], str]:
        """
        Evaluate per-joint correctness by comparing user landmarks
        against reference pose landmark distributions.

        Returns:
            all_correct: True if all key joints are within correct threshold (< 2.0 std)
            has_yellow: True if any joint has warning deviation (2.0 <= dev < 3.5)
            has_red: True if any joint has critical deviation (>= 3.5)
            joints: list of { index, name, status, deviation }
            correction_message: human-readable correction cue
        """
        lm_xy = np.array(landmarks_xy, dtype=np.float32)
        if not np.isfinite(lm_xy).all():
            raise ValueError("Landmarks contain NaN/inf")
        normalized = self.normalize_landmarks(lm_xy)

        # If no reference for this pose, use classification confidence only
        ref = self._reference_poses.get(target_pose)
        if ref is None:
            if target_pose not in self._warned_missing:
                self._warned_missing.add(target_pose)
                logger.warning(
                    "No reference distribution for '%s' - joints cannot be scored.", target_pose
                )
            return True, False, False, self._all_correct_joints(), ""

        mean = ref["mean"]
        std = ref["std"]

        # Compute per-joint deviation (in units of standard deviation)
        joints = []
        warning_names = []
        critical_names = []
        all_correct = True

        for idx in KEY_JOINT_INDICES:
            x_idx = idx * 2
            y_idx = idx * 2 + 1

            if x_idx >= len(normalized) or x_idx >= len(mean):
                continue

            # Compute deviation in normalized space
            dx = abs(normalized[x_idx] - mean[x_idx])
            dy = abs(normalized[y_idx] - mean[y_idx])

            # Use std to scale: deviation = distance / max(std, epsilon)
            sx = max(float(std[x_idx]), MIN_STD)
            sy = max(float(std[y_idx]), MIN_STD)
            dev = float(np.sqrt((dx / sx) ** 2 + (dy / sy) ** 2))
            if not math.isfinite(dev):
                dev = MAX_DEVIATION
            dev = min(dev, MAX_DEVIATION)

            # Thresholds:
            # dev < 2.0: correct (green)
            # 2.0 <= dev < 3.5: warning / minor misalignment (yellow) - timer does NOT stop!
            # dev >= 3.5: critical / severe mistake (red) - timer stops!
            if dev < 2.0:
                status = "correct"
            elif dev < 3.5:
                status = "warning"
                all_correct = False
                warning_names.append(LANDMARK_NAMES[idx])
            else:
                status = "critical"
                all_correct = False
                critical_names.append(LANDMARK_NAMES[idx])

            joints.append({
                "index": idx,
                "name": LANDMARK_NAMES[idx],
                "status": status,
                "deviation": round(dev, 3),
            })

        has_yellow = len(warning_names) > 0
        has_red = len(critical_names) > 0

        # Build concise correction message for speech and display
        correction = ""
        if critical_names:
            formatted = [n.replace("_", " ") for n in critical_names[:2]]
            if len(formatted) == 1:
                correction = f"Adjust your {formatted[0]}."
            else:
                correction = f"Adjust your {formatted[0]} and {formatted[1]}."
        elif warning_names:
            formatted = [n.replace("_", " ") for n in warning_names[:2]]
            if len(formatted) == 1:
                correction = f"Gently adjust your {formatted[0]}."
            else:
                correction = f"Gently adjust your {formatted[0]} and {formatted[1]}."

        return all_correct, has_yellow, has_red, joints, correction

    def _all_correct_joints(self) -> list[dict]:
        """Return all key joints as 'correct' (used when no reference available)."""
        return [
            {
                "index": idx,
                "name": LANDMARK_NAMES[idx],
                "status": "correct",
                "deviation": 0.0,
            }
            for idx in KEY_JOINT_INDICES
        ]


# Global singleton
pose_engine = PoseEngine()
