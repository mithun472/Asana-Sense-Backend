"""
Seed MongoDB with the 7 yoga poses that match the TFLite model classes.
Also computes and stores reference landmark distributions.
"""
import asyncio
from database import connect_db, poses_collection
from cloudinary_utils import get_pose_image_url, configure_cloudinary
from reference_poses import load_or_compute_references

# Model class mapping:
# TFLite: ['chair', 'cobra', 'dog', 'no_pose', 'shoudler_stand', 'traingle', 'tree', 'warrior']
# We exclude 'no_pose' and use clean names for the frontend.

YOGA_POSES = [
    {
        "pose_id": "chair",
        "name": "Chair Pose",
        "sanskrit_name": "Utkatasana",
        "difficulty": "Beginner",
        "category": "Standing & Strength",
        "description": "A powerful standing squat that builds leg endurance, core strength, and heat throughout the body.",
        "target_muscles": ["Quadriceps", "Glutes", "Core", "Calves", "Shoulders"],
        "benefits": [
            "Strengthens ankles, thighs, calves, and spine",
            "Stretches shoulders and chest",
            "Stimulates the heart, diaphragm, and abdominal organs",
            "Builds stamina and endurance in lower body",
        ],
        "wrong_posture_impacts": [
            {
                "mistake": "Knees extending past the toes",
                "impact": "Puts excessive pressure on knee joints and patella tendon.",
                "correction": "Shift weight back into heels and sit deeper as if into an invisible chair.",
            },
            {
                "mistake": "Arching the lower back excessively",
                "impact": "Compresses lumbar vertebrae and strains lower back muscles.",
                "correction": "Tuck tailbone slightly and engage core to maintain neutral spine.",
            },
            {
                "mistake": "Shoulders hunching up toward ears",
                "impact": "Creates tension in trapezius and restricts breathing.",
                "correction": "Roll shoulders down and back, extending arms overhead with relaxed trapezius.",
            },
        ],
        "ideal_hold_duration_seconds": 30,
        "voice_keywords": ["chair", "chair pose", "utkatasana", "sitting pose"],
        "key_alignment_checkpoints": [
            "Feet hip-width apart and parallel",
            "Knees bent deeply, tracking over second toes",
            "Weight grounded through heels",
            "Arms extended overhead alongside ears",
            "Core engaged, tailbone lengthening down",
        ],
        "model_class_name": "chair",
        "model_class_index": 0,
    },
    {
        "pose_id": "cobra",
        "name": "Cobra Pose",
        "sanskrit_name": "Bhujangasana",
        "difficulty": "Beginner",
        "category": "Backbend & Spine",
        "description": "An invigorating prone backbend that unlocks thoracic extension, opens the heart center, and strengthens back musculature.",
        "target_muscles": ["Erector Spinae", "Glutes", "Trapezius", "Pectorals", "Abdominals"],
        "benefits": [
            "Counteracts desk hunching by expanding thoracic spinal extension",
            "Strengthens the entire posterior spine and stabilizes deep back muscles",
            "Stimulates abdominal digestive organs and kidneys",
            "Elevates mood and expands vital lung breathing capacity",
        ],
        "wrong_posture_impacts": [
            {
                "mistake": "Cranking the neck backwards into extreme hyperextension",
                "impact": "Compresses cervical vertebrae and restricts arterial blood flow.",
                "correction": "Keep the back of the neck elongated; lift from the heart rather than throwing the chin up.",
            },
            {
                "mistake": "Flaring elbows outward away from the body",
                "impact": "Disengages latissimus dorsi and pinches shoulder impingement zones.",
                "correction": "Keep elbows tucked tightly alongside the ribcage pointing back.",
            },
            {
                "mistake": "Over-pushing with arms while lifting hips off the floor",
                "impact": "Crunches the L4-L5 lumbar vertebrae with sheer force.",
                "correction": "Keep the pubic bone anchored to the ground and use posterior spinal strength.",
            },
        ],
        "ideal_hold_duration_seconds": 30,
        "voice_keywords": ["cobra", "cobra pose", "bhujangasana", "snake pose"],
        "key_alignment_checkpoints": [
            "Tops of both feet pressed firmly into the mat",
            "Hands placed under shoulders with elbows hugging ribs",
            "Lift chest using back muscles rather than pushing with hands",
            "Pelvis and pubic bone remain on the floor",
            "Neutral cervical spine with gaze forward",
        ],
        "model_class_name": "cobra",
        "model_class_index": 1,
    },
    {
        "pose_id": "dog",
        "name": "Downward-Facing Dog",
        "sanskrit_name": "Adho Mukha Svanasana",
        "difficulty": "Beginner",
        "category": "Inversion & Core",
        "description": "The cornerstone inversion of yoga that lengthens the posterior muscular chain while building upper body strength.",
        "target_muscles": ["Latissimus Dorsi", "Hamstrings", "Calves", "Triceps", "Serratus Anterior"],
        "benefits": [
            "Deeply decompresses the spine and stretches hamstrings",
            "Strengthens shoulders, arms, wrists, and core stabilizers",
            "Calms the brain and relieves mild fatigue and backache",
            "Enhances blood flow to the upper torso and head",
        ],
        "wrong_posture_impacts": [
            {
                "mistake": "Rounding the upper and lower back",
                "impact": "Puts excessive compressive pressure on lumbar discs.",
                "correction": "Bend knees generously and focus on sending tailbone up and back.",
            },
            {
                "mistake": "Dumping all weight onto wrists",
                "impact": "Leads to carpal tunnel irritation and wrist strain.",
                "correction": "Press firmly into knuckle pads and fingertips to distribute weight.",
            },
            {
                "mistake": "Crowding the neck by scrunching shoulders",
                "impact": "Impairs rotator cuff mechanics and causes tension headaches.",
                "correction": "Broaden through upper back and externally rotate upper arms.",
            },
        ],
        "ideal_hold_duration_seconds": 60,
        "voice_keywords": ["downward dog", "down dog", "adho mukha", "dog pose", "dog"],
        "key_alignment_checkpoints": [
            "Hands shoulder-width apart with fingers spread wide",
            "Press through index finger base and thumb to protect wrists",
            "Sit bones reaching high toward the ceiling (inverted V)",
            "Ears aligned with upper biceps, neck relaxed",
            "Heels reaching gently toward the floor",
        ],
        "model_class_name": "dog",
        "model_class_index": 2,
    },
    {
        "pose_id": "shoulder_stand",
        "name": "Shoulder Stand",
        "sanskrit_name": "Sarvangasana",
        "difficulty": "Advanced",
        "category": "Inversion & Core",
        "description": "The queen of asanas — a full body inversion that stimulates the thyroid, strengthens the core, and calms the nervous system.",
        "target_muscles": ["Core", "Trapezius", "Deltoids", "Glutes", "Neck Extensors"],
        "benefits": [
            "Stimulates thyroid and parathyroid glands",
            "Improves venous blood return and reduces leg swelling",
            "Strengthens shoulders, arms, and core stabilizers",
            "Calms the nervous system and aids sleep",
        ],
        "wrong_posture_impacts": [
            {
                "mistake": "Turning the head while weight is on the neck",
                "impact": "Can cause severe cervical spine injury and nerve damage.",
                "correction": "Keep head absolutely still and centered, gaze directly at the ceiling.",
            },
            {
                "mistake": "Collapsing the elbows outward",
                "impact": "Transfers body weight onto the cervical spine instead of shoulders.",
                "correction": "Keep elbows shoulder-width apart and firmly press into the floor.",
            },
            {
                "mistake": "Allowing the hips to sag behind the shoulders",
                "impact": "Strains the lower back and reduces the inversion benefit.",
                "correction": "Engage core and walk hands higher up the back for support.",
            },
        ],
        "ideal_hold_duration_seconds": 60,
        "voice_keywords": ["shoulder stand", "shoulderstand", "sarvangasana", "inversion"],
        "key_alignment_checkpoints": [
            "Weight distributed across shoulders and upper arms, not neck",
            "Body aligned vertically from shoulders through hips to toes",
            "Elbows shoulder-width, hands supporting mid-back",
            "Chin tucked toward chest naturally",
            "Legs active and together, toes reaching toward ceiling",
        ],
        "model_class_name": "shoudler_stand",  # matches model typo
        "model_class_index": 4,
    },
    {
        "pose_id": "triangle",
        "name": "Triangle Pose",
        "sanskrit_name": "Trikonasana",
        "difficulty": "Intermediate",
        "category": "Standing & Strength",
        "description": "A foundation lateral standing pose cultivating geometric alignment, deep hamstring extension, and torso rotation.",
        "target_muscles": ["Hamstrings", "Obliques", "Groin", "Latissimus Dorsi", "Quadriceps"],
        "benefits": [
            "Deeply stretches hamstrings, calves, and inner thighs",
            "Strengthens thighs, knees, ankles, and spinal stabilizers",
            "Relieves backache and improves digestion",
            "Develops spatial awareness and geometric equilibrium",
        ],
        "wrong_posture_impacts": [
            {
                "mistake": "Collapsing the top hip and shoulder forward",
                "impact": "Destroys lateral spine elongation and strains lumbar spine.",
                "correction": "Stack top hip over bottom hip and roll top chest open.",
            },
            {
                "mistake": "Hyperextending and locking the front knee",
                "impact": "Damages posterior knee capsule ligaments over time.",
                "correction": "Engage front quadriceps and maintain subtle micro-bend.",
            },
            {
                "mistake": "Resting full body weight on the front shin",
                "impact": "Compromises leg alignment and disengages core stabilizers.",
                "correction": "Rest fingertips lightly on a block or hover with oblique strength.",
            },
        ],
        "ideal_hold_duration_seconds": 45,
        "voice_keywords": ["triangle", "triangle pose", "trikonasana"],
        "key_alignment_checkpoints": [
            "Front foot pointing straight forward, back foot at 45-60 degrees",
            "Both legs straight without hyperextending front knee",
            "Hinge from front hip joint, not from waist",
            "Torso rotated open with arms in vertical line",
            "Spine lengthening parallel to the floor",
        ],
        "model_class_name": "traingle",  # matches model typo
        "model_class_index": 5,
    },
    {
        "pose_id": "tree",
        "name": "Tree Pose",
        "sanskrit_name": "Vrikshasana",
        "difficulty": "Beginner",
        "category": "Standing & Balance",
        "description": "A classic balancing posture that establishes grounding, postural equilibrium, and neuro-muscular poise.",
        "target_muscles": ["Calves", "Quadriceps", "Ankles", "Gluteus Medius", "Core"],
        "benefits": [
            "Strengthens ankles, calves, thighs, and spinal column",
            "Improves neuromuscular balance, proprioception, and focus",
            "Helps alleviate mild sciatica when performed symmetrically",
            "Opens hips and stretches groin and inner thigh adductors",
        ],
        "wrong_posture_impacts": [
            {
                "mistake": "Resting the foot directly against the knee joint",
                "impact": "Applies harmful lateral shear force against the MCL and meniscus.",
                "correction": "Place foot above the knee on upper thigh or below on calf.",
            },
            {
                "mistake": "Pushing the standing hip out to the side",
                "impact": "Compresses the SI joint and weakens gluteus medius.",
                "correction": "Hug outer hip inward toward midline to keep hips level.",
            },
            {
                "mistake": "Arching lower back excessively",
                "impact": "Pinches lumbar vertebrae and disengages abdominal stabilization.",
                "correction": "Tuck tailbone slightly and engage transverse abdominis.",
            },
        ],
        "ideal_hold_duration_seconds": 45,
        "voice_keywords": ["tree", "tree pose", "vrikshasana", "balance pose"],
        "key_alignment_checkpoints": [
            "Standing leg straight and rooted into all four corners of foot",
            "Foot placed on inner thigh or calf (NEVER on knee)",
            "Hips squared forward with pelvis level",
            "Spine elongated with shoulders rolled down and back",
            "Gaze (Drishti) fixed on unmoving point at eye level",
        ],
        "model_class_name": "tree",
        "model_class_index": 6,
    },
    {
        "pose_id": "warrior",
        "name": "Warrior III",
        "sanskrit_name": "Virabhadrasana III",
        "difficulty": "Intermediate",
        "category": "Balance & Core Strength",
        "description": "A balancing horizontal T-shape posture that strengthens the posterior chain, stabilizes the standing leg, and demands deep core integration.",
        "target_muscles": ["Hamstrings", "Glutes", "Spinal Erectors", "Core", "Ankles", "Shoulders"],
        "benefits": [
            "Strengthens the entire back body including spine, hamstrings, and glutes",
            "Sharpens full-body balance, proprioception, and spatial awareness",
            "Firms abdominal core muscles and stabilizing pelvic muscles",
            "Develops stabilizing strength and arch endurance in standing ankle and foot",
        ],
        "wrong_posture_impacts": [
            {
                "mistake": "Opening the hip of the lifted leg",
                "impact": "Twists the sacroiliac (SI) joint and destabilizes balance.",
                "correction": "Internally rotate lifted thigh so both hip points face the mat.",
            },
            {
                "mistake": "Arching or sagging the lumbar spine",
                "impact": "Compresses lumbar vertebrae under leverage.",
                "correction": "Draw navel toward spine and reach actively through back heel.",
            },
            {
                "mistake": "Locking or hyperextending standing knee",
                "impact": "Places strain on knee capsule and reduces stabilizing control.",
                "correction": "Maintain a soft microbend in the standing knee.",
            },
        ],
        "ideal_hold_duration_seconds": 45,
        "voice_keywords": ["warrior", "warrior three", "warrior 3", "virabhadrasana", "virabhadrasana 3", "warrior two", "warrior 2"],
        "key_alignment_checkpoints": [
            "Standing leg grounded with microbend",
            "Torso and lifted leg horizontal in T-shape",
            "Pelvis squared level to floor",
            "Arms extended forward alongside ears",
            "Active drive through back heel",
        ],
        "model_class_name": "warrior",
        "model_class_index": 7,
    },
]


async def seed_poses():
    """Insert or update all 7 yoga poses into MongoDB."""
    configure_cloudinary()
    coll = poses_collection()

    for pose in YOGA_POSES:
        pose["image_url"] = get_pose_image_url(pose["pose_id"])
        await coll.replace_one(
            {"pose_id": pose["pose_id"]},
            pose,
            upsert=True,
        )
        print(f"  ✓ Seeded: {pose['name']} ({pose['pose_id']})")

    # Create indexes
    await coll.create_index("pose_id", unique=True)
    print(f"[Seed] {len(YOGA_POSES)} poses seeded successfully.")


async def seed_references():
    """Compute and store reference pose landmark distributions."""
    refs = await load_or_compute_references("../train_landmarks.csv")
    print(f"[Seed] Reference poses computed for {len(refs)} classes.")
    return refs


async def main():
    """Run the full seed process."""
    await connect_db()
    print("\n=== Seeding Yoga Poses ===")
    await seed_poses()
    print("\n=== Computing Reference Poses ===")
    await seed_references()
    print("\n=== Seed Complete ===")


if __name__ == "__main__":
    from database import connect_db
    asyncio.run(main())
