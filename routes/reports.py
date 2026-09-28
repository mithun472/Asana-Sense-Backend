"""
Report generation and email dispatch routes for ASANA-SENSE API.
Handles Groq AI report synthesis, biomechanical fallback analysis, and PDF email delivery.
"""
import os
import json
import urllib.request
import urllib.error
import re
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status

from auth import get_current_user
from email_service import send_session_report_email

router = APIRouter(prefix="/api", tags=["Reports & AI Analysis"])


@router.post("/generate-session-report")
async def generate_session_report(payload: dict):
    """Generate dynamic AI session report with Groq API and past session progress analysis."""
    session_data = payload.get("sessionData", {})
    prev_session_data = payload.get("previousSessionData")
    groq_api_key = payload.get("groqApiKey") or os.getenv("GROQ_API_KEY")

    # 1. Try Groq API if key is available
    if groq_api_key:
        try:
            print("[Backend Groq AI] Calling llama-3.3-70b-versatile for human-understandable report...")
            system_prompt = (
                "You are Veda AI, an elite yoga therapist and warm master biomechanics coach for ASANA-SENSE.\n"
                "Communicate in clear, human-understandable, natural language (avoid dense medical jargon).\n"
                "Analyze the user's completed practice session and actual poses performed.\n"
                "If previous session data is provided and they practiced the same pose(s), specifically explain how they improved compared to last time with clear numbers and praise.\n"
                "Give a high-energy, uplifting 'boostingMessage' to inspire them to keep going!\n\n"
                "You MUST return a JSON object with:\n"
                "- overallScore: number (0 to 100)\n"
                "- flexibilityIndex: string (e.g. 'Exceptional Steadiness', 'Proficient Alignment', 'Developing Form')\n"
                "- coreStabilityScore: number (0 to 100)\n"
                "- boostingMessage: string (warm, encouraging 2-3 sentence motivational message)\n"
                "- comparisonWithPrevious: string (clear comparison showing how they improved if repeated pose or progress vs previous session)\n"
                "- keyStrengths: array of 2-3 positive observations on their actual poses\n"
                "- priorityGrowthAreas: array of 2-3 simple, actionable tips on how to improve in plain human language\n"
                "- masterTeacherNote: string (mindful, grounding wisdom from the master yoga teacher)\n"
                "- recommendedNextPoses: array of 3 pose names tailored to progress\n"
                "- poseImprovements: array of objects for each practiced pose with:\n"
                "    - poseName: string\n"
                "    - currentStatus: string (summary of hold steadiness and alignment today)\n"
                "    - actionableTips: array of 2-3 specific cues on how to improve this exact pose next time\n"
                "    - jointSafetyCue: string (anatomical checkpoint to protect knees/lower back/shoulders)\n"
                "- fitnessNutrition: object with:\n"
                "    - immediatePostWorkout: array of 2-3 recovery foods/drinks (e.g., electrolytes, protein smoothie, sprouted moong bowl)\n"
                "    - dailyStaminaFoods: array of 3-4 nutrient-dense foods for flexibility, joint health, and core strength\n"
                "    - foodsToAvoid: array of 2-3 inflammatory foods that hinder flexibility and joint recovery\n"
                "    - hydrationTip: string (cellular hydration guidance for spinal discs & fascia)\n"
                "    - dietSummary: string (warm 2-sentence nutritional advice for practitioner fitness)\n"
            )
            user_prompt = f"Current Session:\n{json.dumps(session_data, indent=2)}\n\n"
            if prev_session_data:
                user_prompt += f"Previous Session for Comparison:\n{json.dumps(prev_session_data, indent=2)}"
            else:
                user_prompt += "First session (baseline certification)."

            req_body = json.dumps({
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.5,
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=req_body,
                headers={
                    "Authorization": f"Bearer {groq_api_key}",
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                    "User-Agent": "ASANA-SENSE/2.0",
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=12) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                raw_content = res_data["choices"][0]["message"]["content"]
                # Strip markdown code blocks if present
                clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_content.strip(), flags=re.MULTILINE)
                parsed = json.loads(clean_json)
                parsed["aiProvider"] = "Groq (Llama 3.3 70B)"
                return {"success": True, "data": parsed}
        except Exception as e:
            print(f"[Backend Groq AI Error]: {e}")

    # Fallback: Dynamic Biomechanical Heuristics on REAL Poses
    current_poses = session_data.get("posesRecorded") or session_data.get("poses_recorded") or []
    prev_poses = (prev_session_data.get("posesRecorded") or prev_session_data.get("poses_recorded") or []) if prev_session_data else []

    current_score = session_data.get("overallAccuracy") or session_data.get("overall_accuracy") or 92
    prev_score = (prev_session_data.get("overallAccuracy") or prev_session_data.get("overall_accuracy")) if prev_session_data else None

    comparison_text = ""
    has_matched = False

    if current_poses and prev_poses:
        for cp in current_poses:
            cid = cp.get("poseId") or cp.get("pose_id")
            matched = next((p for p in prev_poses if (p.get("poseId") or p.get("pose_id")) == cid), None)
            if matched:
                has_matched = True
                curr_hold = cp.get("durationSeconds") or cp.get("duration_seconds") or 0
                prev_hold = matched.get("durationSeconds") or matched.get("duration_seconds") or 0
                curr_acc = cp.get("accuracyScore") or cp.get("accuracy_score") or 0
                prev_acc = matched.get("accuracyScore") or matched.get("accuracy_score") or 0
                pname = cp.get("poseName") or cp.get("pose_name") or "your pose"
                hdiff = curr_hold - prev_hold
                sdiff = curr_acc - prev_acc
                comparison_text = (
                    f"In your previous practice of {pname}, you held for {prev_hold}s at {prev_acc}% accuracy. "
                    f"In this session, you achieved {curr_hold}s ({'+' if hdiff >= 0 else ''}{hdiff}s) with {curr_acc}% accuracy ({'+' if sdiff >= 0 else ''}{sdiff}%)!"
                )
                break

    if not comparison_text:
        if prev_score is not None:
            diff = current_score - prev_score
            comparison_text = f"Overall session posture efficiency moved from {prev_score}% to {current_score}% ({'+' if diff >= 0 else ''}{diff}% difference) with improved core steadiness!"
        else:
            comparison_text = f"Baseline practice session certified! You established a strong foundational score of {current_score}% accuracy. Repeating these poses in your next session will unlock direct progress tracking."

    boosting_message = (
        f"Phenomenal dedication on the mat! Repeating {current_poses[0].get('poseName', 'your pose') if current_poses else 'your pose'} reinforced your neuromuscular alignment, noticeably reducing micro-wobbles and boosting your continuous hold endurance."
        if has_matched else
        "Outstanding effort today! By stepping onto the mat and completing these structured holds, you activated deep stabilizing muscle chains and built mental calm. Every session compounds your physical resilience!"
    )

    dynamic_strengths = []
    dynamic_pose_improvements = []
    
    # Specific pose improvement knowledge base for the actual yoga poses
    pose_advice_map = {
        "chair": {
            "tips": [
                "Shift your body weight 10-15% further back into your heels so your toes can remain lightly grounded without gripping.",
                "Draw your navel gently toward your lumbar spine to avoid excessive hyperextension in the lower back.",
                "Broaden across your collarbones and glide your shoulder blades down while extending arms overhead."
            ],
            "safety": "Ensure your knees stay behind your toes and remain parallel, avoiding inward valgus collapse."
        },
        "cobra": {
            "tips": [
                "Initiate the spinal extension from the thoracic spine (chest) rather than pushing aggressively through wrists.",
                "Hug your elbows tightly into your ribcage to keep your rotator cuff safely engaged.",
                "Keep the back of your neck long by directing your gaze 3-4 feet forward rather than cranking your chin up."
            ],
            "safety": "Keep your pubic bone firmly anchored to the floor to prevent pinching in the lumbar L4-L5 vertebrae."
        },
        "dog": {
            "tips": [
                "Firmly press through the knuckle pads of your index fingers and thumbs to decompress the median wrist nerve.",
                "Maintain a generous microbend in your knees if hamstrings feel tight, allowing your sit bones to lift higher.",
                "Rotate your outer armpits inward toward your ears to broaden the upper back and stabilize the scapulae."
            ],
            "safety": "Prioritize a straight, lengthened spine over forcing heels flat to the mat."
        },
        "shoulder_stand": {
            "tips": [
                "Walk your hands further down your back towards your shoulder blades to lift your chest into your chin.",
                "Keep your elbows tucked strictly shoulder-width apart without splaying outward on the mat.",
                "Reach upward through the balls of your feet, engaging your inner thighs and glutes."
            ],
            "safety": "CRITICAL: Never turn your head or neck sideways while in shoulder stand; keep your gaze centered on your chest."
        },
        "triangle": {
            "tips": [
                "Hinge strictly from the hip crease rather than rounding sideways through your waist.",
                "Stack your top shoulder and hip directly over the bottom ones as if flattened between two panes of glass.",
                "Engage your core obliques so very little weight rests on your lower hand or shin."
            ],
            "safety": "Maintain a subtle 5-degree micro-bend in the front knee to shield posterior cruciate ligaments."
        },
        "tree": {
            "tips": [
                "Firmly root through all four corners of your standing foot, lifting the inner arch for reflexive stability.",
                "Fix your drishti (unwavering gaze) on a stationary eye-level point 6-8 feet ahead of you.",
                "Hug the outer hip of the standing leg inward toward the midline rather than jutting it out."
            ],
            "safety": "Place the lifted foot on either the inner thigh or calf—never directly against the side of the knee joint."
        },
        "warrior": {
            "tips": [
                "Internally rotate the lifted thigh so both hip points face squarely toward the floor in a level horizontal plane.",
                "Actively drive through the heel of the lifted back leg to activate your gluteus medius and hamstrings.",
                "Create a continuous energetic line of power from your outstretched fingertips back through your flexed heel."
            ],
            "safety": "Keep a soft microbend in the supporting knee to protect the knee capsule from hyperextension."
        }
    }

    for p in current_poses:
        pname = p.get("poseName") or p.get("pose_name") or "Asana"
        pid = (p.get("poseId") or p.get("pose_id") or "").lower()
        bh = p.get("bestHoldSeconds") or p.get("best_hold_seconds") or p.get("durationSeconds") or p.get("duration_seconds") or 15
        acc = p.get("accuracyScore") or p.get("accuracy_score") or 92
        dynamic_strengths.append(f"Solid execution in {pname} with continuous hold of {bh}s and {acc}% joint angle accuracy.")

        # Find matching knowledge
        advice_key = next((k for k in pose_advice_map if k in pid or k in pname.lower()), "tree")
        advice = pose_advice_map[advice_key]

        dynamic_pose_improvements.append({
            "poseName": pname,
            "currentStatus": f"Held for {bh}s with {acc}% biomechanical alignment.",
            "actionableTips": advice["tips"],
            "jointSafetyCue": advice["safety"]
        })

    if not dynamic_strengths:
        dynamic_strengths = [
            "Consistent breath synchronization maintained through transitions.",
            "Pelvis leveling maintained with stable joint alignment.",
        ]
        dynamic_pose_improvements.append({
            "poseName": "Tree Pose Balance (Vrikshasana)",
            "currentStatus": "Strong foundational balance hold certified.",
            "actionableTips": pose_advice_map["tree"]["tips"],
            "jointSafetyCue": pose_advice_map["tree"]["safety"]
        })

    fitness_nutrition = {
        "immediatePostWorkout": [
            "Tender Coconut Water or Himalayan Pink Salt Lemon Water: Immediately replenishes vital electrolytes (potassium, sodium, magnesium) lost through sweat.",
            "Sprouted Moong Dal Salad or Plant Protein Smoothie: High bio-availability plant protein with chia seeds to rebuild muscle fibers and restore glycogen within 45 minutes.",
            "Warm Golden Turmeric Almond Milk: Curcumin reduces joint inflammation and accelerates fascial recovery after deep holds."
        ],
        "dailyStaminaFoods": [
            "Soaked Walnuts & Flaxseeds: Rich in plant-based Omega-3 fatty acids to lubricate synovial joint capsules and maintain ligament elasticity.",
            "Ancient Whole Millets (Ragi / Jowar) & Quinoa: Complex carbohydrates providing slow-burning energy for long yoga sessions without blood sugar spikes.",
            "Fresh Leafy Greens (Palak, Moringa, Methi): Dense in iron, magnesium, and calcium to prevent post-practice muscle cramping.",
            "Sesame Seeds & Soaked Almonds: Essential natural calcium and healthy fats to strengthen bone density for standing balances."
        ],
        "foodsToAvoid": [
            "Refined White Sugar & High-Fructose Syrups: Induces systemic fascial stiffness and delays muscle recovery.",
            "Ultra-Processed Deep-Fried Foods: High in trans fats that impair cellular oxygenation and cause post-practice lethargy.",
            "Excessive Caffeine Immediately Before Practice: Dehydrates spinal intervertebral discs and increases tremors during balance holds."
        ],
        "hydrationTip": "Drink 400-500ml of room-temperature or lukewarm water 30 minutes after your practice. Lukewarm water enhances digestive Agni and cellular hydration for spinal discs.",
        "dietSummary": "Nourish your body with clean, sattvic, whole foods rich in antioxidants and plant proteins. Prioritize deep hydration and anti-inflammatory foods to support joint longevity and muscular vitality."
    }

    return {
        "success": True,
        "data": {
            "overallScore": current_score,
            "flexibilityIndex": "Exceptional Steadiness" if current_score >= 90 else "Proficient Alignment" if current_score >= 80 else "Developing Form",
            "coreStabilityScore": min(100, max(75, current_score - 3)),
            "boostingMessage": boosting_message,
            "comparisonWithPrevious": comparison_text,
            "keyStrengths": dynamic_strengths[:3],
            "priorityGrowthAreas": [
                "Maintain a soft 5° micro-bend in your supporting knees to shield the joint capsule from excessive shear.",
                "Slide your scapulae down the back of your ribcage to neutralize trapezius tension.",
                "Ground evenly through all four corners of your feet for optimal drishti balance.",
            ],
            "poseImprovements": dynamic_pose_improvements,
            "fitnessNutrition": fitness_nutrition,
            "masterTeacherNote": "Consistency creates mastery. The steadiness and mindful presence you cultivated in today's holds will carry directly into your posture and daily energy throughout the week.",
            "recommendedNextPoses": ["Warrior III Pose", "Tree Pose Balance", "Downward-Facing Dog"],
            "aiProvider": "Veda AI Biomechanics Engine",
        }
    }


@router.post("/send-session-report-email")
async def send_session_report_email_endpoint(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Automatically generates PDF and sends certified session report to the
    authenticated user's registered email via SMTP. No manual email entry needed.
    """
    session_data = payload.get("sessionData", {})
    ai_report = payload.get("aiReport")

    to_email = current_user.get("email", "")
    user_name = current_user.get("name", "Yogi")

    if not to_email or "@" not in to_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid email address found on account. Please update your profile.",
        )

    # Run blocking SMTP/PDF in thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    success, message = await loop.run_in_executor(
        None,
        send_session_report_email,
        to_email,
        user_name,
        session_data,
        ai_report,
    )

    if success:
        return {
            "success": True,
            "message": f"Certified session report sent to {to_email}",
            "to_email": to_email,
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to send email: {message}",
        )