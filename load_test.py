"""
load_test.py — simulate N users streaming pose landmarks at the same time.

Usage (server must be running):
    python load_test.py                 # 10 users, 15 s, ~10 fps each
    python load_test.py 25 20 10        # 25 users, 20 s, 10 fps each

Reports per-user and overall response latency. If numbers stay low and
stable as you raise N, the backend is handling users concurrently.
"""
import asyncio
import json
import random
import sys
import time

import websockets

URL = "ws://localhost:8000/ws/pose-detect"
POSES = ["tree", "warrior", "chair", "cobra", "dog", "triangle", "shoulder_stand"]


def fake_landmarks():
    # 33 (x, y) points, roughly a standing figure with a little jitter
    return [[0.5 + random.uniform(-0.05, 0.05), i / 33 + random.uniform(-0.01, 0.01)] for i in range(33)]


async def one_user(uid: int, seconds: int, fps: int, results: list):
    latencies = []
    errors = 0
    try:
        async with websockets.connect(URL) as ws:
            target = random.choice(POSES)
            end = time.time() + seconds
            while time.time() < end:
                t0 = time.perf_counter()
                await ws.send(json.dumps({
                    "type": "landmarks",
                    "target_pose": target,
                    "landmarks": fake_landmarks(),
                }))
                await ws.recv()
                latencies.append((time.perf_counter() - t0) * 1000)
                await asyncio.sleep(max(0, 1 / fps - (time.perf_counter() - t0)))
    except Exception as e:
        errors += 1
        print(f"user {uid} error: {e}")
    results.append((uid, latencies, errors))


async def main():
    users = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    fps = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    print(f"{users} users, {seconds}s, {fps} fps each -> {URL}")

    results: list = []
    await asyncio.gather(*(one_user(i, seconds, fps, results) for i in range(users)))

    all_lat = sorted(l for _, lats, _ in results for l in lats)
    errs = sum(e for _, _, e in results)
    if not all_lat:
        print("no responses received — is the server running and model loaded?")
        return
    p = lambda q: all_lat[min(len(all_lat) - 1, int(len(all_lat) * q))]
    print(f"frames answered : {len(all_lat)}")
    print(f"failed users    : {errs}")
    print(f"latency avg     : {sum(all_lat) / len(all_lat):.1f} ms")
    print(f"latency p50/p95 : {p(0.50):.1f} / {p(0.95):.1f} ms")
    print(f"latency max     : {all_lat[-1]:.1f} ms")


if __name__ == "__main__":
    asyncio.run(main())
