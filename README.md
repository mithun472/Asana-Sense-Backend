# Asana-Sense Backend

FastAPI backend that connects your trained Extra Trees yoga-pose classifier
to MongoDB Atlas. When the model detects the user is doing the wrong pose,
it fetches the correct reference pose (image + merits + demerits) from the DB.

## 1. Project layout

```
asana-sense-backend/
├── app/
│   ├── main.py            # FastAPI app, startup/shutdown
│   ├── config.py          # env-based settings
│   ├── database.py        # MongoDB (Motor async) connection
│   ├── ml_model.py         # loads your .pkl model, runs predictions
│   ├── schemas.py          # Pydantic request/response models
│   └── routers/
│       ├── poses.py        # CRUD for pose documents
│       └── predict.py      # /predict/check — the core "detect mistake" flow
├── seed_data/
│   └── seed_db.py          # one-time script to load your 5 poses into Atlas
├── model_files/            # put your trained .pkl model here
├── requirements.txt
└── .env.example
```

## 2. Setup

```bash
cd asana-sense-backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
```

Edit `.env`:
- `MONGO_URI` — your MongoDB Atlas connection string (Atlas → Connect → Drivers → Python)
- `MODEL_PATH` — path to your saved Extra Trees model
- `LABEL_ENCODER_PATH` — only needed if you encoded pose names to integers before training

Drop your trained model file into `model_files/`, e.g.:
```
model_files/extra_trees_pose_model.pkl
```

## 3. Seed the database with your 5 poses

Edit `seed_data/seed_db.py` — replace the placeholder `image_url` values with
real hosted image URLs (Cloudinary, S3, imgur, or a GitHub raw link), and fill
in real merits/demerits copy. Then run:

```bash
python seed_data/seed_db.py
```

This upserts 5 documents into the `poses` collection, so it's safe to re-run.

## 4. Run the API

```bash
uvicorn app.main:app --reload
```

Visit `http://127.0.0.1:8000/docs` for interactive Swagger docs.

## 5. Endpoints

| Method | Path                  | Purpose                                      |
|--------|-----------------------|-----------------------------------------------|
| GET    | `/poses`              | List all 5 poses                              |
| GET    | `/poses/{pose_name}`  | Get one pose                                  |
| POST   | `/poses`              | Add a new pose                                |
| PUT    | `/poses/{pose_name}`  | Update a pose                                 |
| DELETE | `/poses/{pose_name}`  | Delete a pose                                 |
| POST   | `/predict/check`      | Run ML prediction + fetch correction if wrong |
| GET    | `/health`             | Health check                                  |

### `POST /predict/check`

Request body:
```json
{
  "landmarks": [0.51, 0.42, -0.03, 0.99, "... one float per landmark feature ..."],
  "expected_pose": "Vrikshasana"
}
```

- `landmarks`: the flattened feature vector your model expects (e.g. MediaPipe's
  33 landmarks × [x, y, z, visibility] = 132 floats — must match however you
  built features during training).
- `expected_pose`: the `pose_name` the user is currently practicing (drives
  which pose gets fetched from the DB if there's a mismatch).

Response when the user does it wrong:
```json
{
  "predicted_pose": "Tadasana",
  "confidence": 0.87,
  "is_correct": false,
  "message": "You're doing 'Tadasana' but this pose should be 'Vrikshasana'. Here's the correct reference.",
  "correction": {
    "_id": "...",
    "pose_name": "Vrikshasana",
    "display_name": "Tree Pose",
    "image_url": "https://...",
    "description": "...",
    "merits": ["..."],
    "demerits": ["..."]
  }
}
```

## 6. Wiring your existing ML pipeline

You said the ML code (feature extraction from MediaPipe → landmarks →
Extra Trees classifier) already exists. The only two things this backend
needs from that pipeline:

1. **The saved model file** — `joblib.dump(your_model, "extra_trees_pose_model.pkl")`,
   placed at `MODEL_PATH`.
2. **The exact same feature vector shape/order** at inference time as you used
   for training — whatever function turns a MediaPipe frame into a list of
   floats, reuse it client-side (or in a separate `/extract-landmarks` step)
   before calling `/predict/check`.

If your frontend captures video and extracts landmarks in the browser
(e.g. via `@mediapipe/tasks-vision` in JS) it can POST the landmarks array
straight to `/predict/check`. If landmark extraction instead happens on the
server from an uploaded image/frame, tell me and I'll add an
`/predict/from-image` endpoint that runs MediaPipe server-side first.
