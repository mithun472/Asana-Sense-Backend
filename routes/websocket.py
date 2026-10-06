"""
WebSocket route for real-time pose detection and biomechanics evaluation.

Client sends:  { "type": "landmarks", "target_pose": "tree", "landmarks": [[x,y] x33] }
Server sends:  { "type": "pose_result", ... }  or  { "type": "error", "code": ..., "message": ... }

pose_result fields:
  predicted_pose, confidence, target_pose
  is_correct      all joints green AND pose matches
  has_red         >=1 joint critical (joint-level only)
  has_yellow      >=1 joint warning
  joints          [{index, name, status: correct|warning|critical, deviation}]
  pose_mismatch   user is confirmed doing a different pose (joints empty then)
  pose_detected   False when no_pose / low confidence (joints empty then)
  reference_available  False => joints are NOT really scored (no reference data)
  timer_action    start | continue | stop | idle
  correction_message
"""
import json
import math
import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pose_engine import pose_engine, CONF_THRESHOLD
from live_feed import live_feed

logger = logging.getLogger("ws.pose")
router = APIRouter(tags=["WebSocket Pose Detection"])

MISMATCH_CONFIRM_FRAMES = 3  # frames of wrong pose before flagging
RED_CONFIRM_FRAMES = 3       # consecutive red frames before timer stops
MAX_MESSAGE_CHARS = 20_000   # 33 landmarks is ~1-2 KB; reject anything absurd


def _clean_landmarks(raw):
    """Return list of 33 [x, y] floats, or None if malformed / non-finite."""
    if not isinstance(raw, list) or len(raw) != 33:
        return None
    out = []
    for p in raw:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return None
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError):
            return None
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        out.append([x, y])
    return out


def _result(target_pose, predicted="unknown", confidence=0.0, *, is_correct=False,
            has_red=False, has_yellow=False, joints=None, timer_action="idle",
            correction="", pose_mismatch=False, pose_detected=True,
            reference_available=True):
    return {
        "type": "pose_result",
        "predicted_pose": predicted,
        "confidence": round(float(confidence), 4),
        "target_pose": target_pose,
        "is_correct": is_correct,
        "has_red": has_red,
        "has_yellow": has_yellow,
        "joints": joints or [],
        "pose_mismatch": pose_mismatch,
        "pose_detected": pose_detected,
        "reference_available": reference_available,
        "timer_action": timer_action,
        "correction_message": correction,
    }


def _pretty(name: str) -> str:
    return name.replace("_", " ").title()


@router.websocket("/ws/pose-detect")
async def websocket_pose_detect(websocket: WebSocket):
    await websocket.accept()
    logger.info("client connected")
    await live_feed.record({
        "method": "WebSocket",
        "path": "/ws/pose-detect",
        "status": 101,
        "duration_ms": 0,
        "time": datetime.utcnow().isoformat(),
        "category": "pose",
        "category_label": "POSE-DETECT",
        "client": websocket.client.host if websocket.client else "",
    })

    # Per-connection state
    was_running = False
    mismatch_counter = 0
    red_streak = 0
    current_target = None
    model_error_sent = False

    try:
        while True:
            raw = await websocket.receive_text()
            if len(raw) > MAX_MESSAGE_CHARS:
                await websocket.send_json({"type": "error", "code": "too_large", "message": "Message too large"})
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "code": "bad_json", "message": "Invalid JSON"})
                continue
            if not isinstance(data, dict) or data.get("type") != "landmarks":
                continue

            target_pose = data.get("target_pose", "")
            landmarks = _clean_landmarks(data.get("landmarks"))

            # Reset per-pose state when user switches target pose
            if target_pose != current_target:
                current_target = target_pose
                was_running = False
                mismatch_counter = 0
                red_streak = 0

            if not target_pose or landmarks is None:
                timer_action = "stop" if was_running else "idle"
                was_running = False
                red_streak = 0
                await websocket.send_json(_result(
                    target_pose, timer_action=timer_action, pose_detected=False,
                ))
                continue

            if not pose_engine.is_ready:
                if not model_error_sent:
                    model_error_sent = True
                    await websocket.send_json({
                        "type": "error", "code": "model_not_loaded",
                        "message": "Pose model is not loaded on the server.",
                    })
                continue

            try:
                # 1. Classify
                predicted, confidence, _ = await asyncio.to_thread(pose_engine.classify, landmarks)

                # 2. No pose / low confidence -> idle (not red: nothing to blame)
                if predicted == "no_pose" or confidence < CONF_THRESHOLD:
                    timer_action = "stop" if was_running else "idle"
                    was_running = False
                    mismatch_counter = 0
                    red_streak = 0
                    await websocket.send_json(_result(
                        target_pose, predicted, confidence,
                        timer_action=timer_action, pose_detected=False,
                    ))
                    continue

                # 3. Match against target (model class names == app pose ids)
                if predicted == target_pose:
                    mismatch_counter = 0
                else:
                    mismatch_counter += 1
                pose_mismatch = mismatch_counter >= MISMATCH_CONFIRM_FRAMES

                # 4. Confirmed wrong pose: joint scoring is meaningless, skip it
                if pose_mismatch:
                    timer_action = "stop" if was_running else "idle"
                    was_running = False
                    red_streak = 0
                    await websocket.send_json(_result(
                        target_pose, predicted, confidence,
                        pose_mismatch=True, timer_action=timer_action,
                        correction=f"You're doing {_pretty(predicted)}. Switch to {_pretty(target_pose)}.",
                    ))
                    continue

                # 5. Per-joint evaluation
                is_correct, has_yellow, has_red, joints, correction = await asyncio.to_thread(
                    pose_engine.evaluate_joints, landmarks, target_pose
                )

                # 6. Timer: yellow never stops it; red must persist N frames to stop a running timer
                red_streak = red_streak + 1 if has_red else 0
                timer_blocked = has_red and (not was_running or red_streak >= RED_CONFIRM_FRAMES)
                if not timer_blocked:
                    timer_action = "continue" if was_running else "start"
                    was_running = True
                else:
                    timer_action = "stop" if was_running else "idle"
                    was_running = False

                await websocket.send_json(_result(
                    target_pose, predicted, confidence,
                    is_correct=is_correct, has_red=has_red, has_yellow=has_yellow,
                    joints=joints, timer_action=timer_action, correction=correction,
                    reference_available=pose_engine.has_reference(target_pose),
                ))

            except Exception:
                logger.exception("processing error")
                await websocket.send_json({
                    "type": "error", "code": "processing_error",
                    "message": "Pose processing failed.",
                })

    except WebSocketDisconnect:
        logger.info("client disconnected")
    except Exception:
        logger.exception("unexpected websocket error")
