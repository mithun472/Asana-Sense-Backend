"""
WebSocket route for real-time pose detection and biomechanics evaluation.
"""
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pose_engine import pose_engine, CONF_THRESHOLD

router = APIRouter(tags=["WebSocket Pose Detection"])


@router.websocket("/ws/pose-detect")
async def websocket_pose_detect(websocket: WebSocket):
    """
    Real-time pose detection pipeline via WebSocket.

    Client sends: { "type": "landmarks", "target_pose": "tree", "landmarks": [[x,y], ...] }
    Server responds: { "type": "pose_result", "predicted_pose": ..., "is_correct": ..., "joints": [...], ... }

    Timer logic:
    - "start": all joints correct, pose matches target → timer should start
    - "continue": still correct → timer keeps running
    - "stop": mismatch detected → timer stops, save as attempt
    - "idle": no valid pose or no_pose detected → timer stays idle
    """
    await websocket.accept()
    print("[WS] Client connected for pose detection")

    # Per-connection state for timer action tracking and prediction debouncing
    was_running = False
    mismatch_counter = 0

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = data.get("type", "")
            if msg_type != "landmarks":
                continue

            target_pose = data.get("target_pose", "")
            landmarks = data.get("landmarks", [])

            if not target_pose or len(landmarks) != 33:
                await websocket.send_json({
                    "type": "pose_result",
                    "predicted_pose": "unknown",
                    "confidence": 0,
                    "target_pose": target_pose,
                    "is_correct": False,
                    "has_red": True,
                    "has_yellow": False,
                    "joints": [],
                    "timer_action": "idle",
                    "correction_message": "",
                })
                continue

            try:
                # 1. Classify the pose
                predicted, confidence, probs = pose_engine.classify(landmarks)

                # 2. If predicted is no_pose or confidence too low → idle
                if predicted == "no_pose" or confidence < CONF_THRESHOLD:
                    timer_action = "stop" if was_running else "idle"
                    was_running = False
                    mismatch_counter = 0
                    await websocket.send_json({
                        "type": "pose_result",
                        "predicted_pose": predicted,
                        "confidence": round(confidence, 4),
                        "target_pose": target_pose,
                        "is_correct": False,
                        "has_red": True,
                        "has_yellow": False,
                        "joints": [],
                        "timer_action": timer_action,
                        "correction_message": "",
                    })
                    continue

                # 3. Check if predicted pose matches target
                # Handle model class name mapping (typos in model)
                model_name_map = {
                    "shoulder_stand": "shoudler_stand",
                    "triangle": "traingle",
                }
                target_model_check = model_name_map.get(target_pose, target_pose)

                raw_match = (predicted == target_model_check) and confidence >= CONF_THRESHOLD
                if raw_match:
                    mismatch_counter = 0
                    pose_matches = True
                else:
                    mismatch_counter += 1
                    # Debounce: require 3 consecutive mismatch frames before flagging different pose
                    pose_matches = mismatch_counter < 3

                # 4. Evaluate per-joint correctness
                is_correct, has_yellow, has_red, joints, correction = pose_engine.evaluate_joints(
                    landmarks, target_pose
                )

                # Override: if confirmed wrong pose after debouncing, flag as red
                if not pose_matches:
                    is_correct = False
                    has_red = True
                    correction = f"You're doing {predicted.replace('_', ' ').title()}. Switch to {target_pose.replace('_', ' ').title()}."

                # 5. Determine timer action:
                # Yellow does NOT stop the timer! Timer runs until RED is detected!
                if not has_red:
                    timer_action = "start" if not was_running else "continue"
                    was_running = True
                else:
                    timer_action = "stop" if was_running else "idle"
                    was_running = False

                # 6. Send result
                await websocket.send_json({
                    "type": "pose_result",
                    "predicted_pose": predicted,
                    "confidence": round(confidence, 4),
                    "target_pose": target_pose,
                    "is_correct": is_correct,
                    "has_red": has_red,
                    "has_yellow": has_yellow,
                    "joints": joints,
                    "timer_action": timer_action,
                    "correction_message": correction,
                })

            except Exception as e:
                print(f"[WS] Processing error: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"Processing error: {str(e)}",
                })

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Unexpected error: {e}")
