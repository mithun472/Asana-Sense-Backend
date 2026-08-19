"""
Wraps your existing trained Extra Trees classifier.

Assumes:
- You already trained an ExtraTreesClassifier on flattened MediaPipe landmarks
  (33 landmarks x 4 values [x, y, z, visibility] = 132 features, or however
  your training pipeline flattens them — just make sure predict-time input
  matches train-time feature order/length).
- The model was saved with joblib.dump(model, "extra_trees_pose_model.pkl").
- model.classes_ / model.predict give you the pose label directly, OR you
  used a LabelEncoder to convert pose names -> integers before training,
  in which case set LABEL_ENCODER_PATH so we can decode back to names.
"""

import joblib
import numpy as np
from app.config import settings

_model = None
_label_encoder = None


def load_model():
    """Call once at app startup."""
    global _model, _label_encoder
    _model = joblib.load(settings.model_path)

    if settings.label_encoder_path:
        try:
            _label_encoder = joblib.load(settings.label_encoder_path)
        except FileNotFoundError:
            _label_encoder = None


def predict_pose(landmarks: list[float]) -> tuple[str, float]:
    """
    Returns (predicted_pose_name, confidence).
    Raises ValueError if the model isn't loaded or input shape is wrong.
    """
    if _model is None:
        raise RuntimeError("Model not loaded. Call load_model() at startup.")

    X = np.array(landmarks, dtype=float).reshape(1, -1)

    expected_features = getattr(_model, "n_features_in_", None)
    if expected_features is not None and X.shape[1] != expected_features:
        raise ValueError(
            f"Expected {expected_features} landmark features, got {X.shape[1]}. "
            "Check your MediaPipe flattening matches training-time preprocessing."
        )

    proba = _model.predict_proba(X)[0]
    pred_idx = int(np.argmax(proba))
    confidence = float(proba[pred_idx])

    raw_label = _model.classes_[pred_idx]

    if _label_encoder is not None:
        pose_name = _label_encoder.inverse_transform([raw_label])[0]
    else:
        pose_name = str(raw_label)

    return pose_name, confidence
