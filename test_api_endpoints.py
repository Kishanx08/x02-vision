import os
import time
import requests

BASE = "http://127.0.0.1:8000"
SAMPLE_IMAGE = r"C:/Users/Kishan Soni/OneDrive/Desktop/train/hentai/0.jpg"


def wait_for_server(url: str, retries: int = 15, delay: float = 1.0):
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, timeout=5)
            return response
        except Exception as exc:
            print(f"waiting for server ({attempt}/{retries})... {exc}")
            time.sleep(delay)
    raise SystemExit("server did not respond")


def print_result(name: str, response):
    print(f"\n{name}: {response.status_code}")
    try:
        print(response.json())
    except Exception:
        print(response.text)


def submit_job(endpoint: str, file_path: str, frame_interval: int = 5):
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, "application/octet-stream")}
        data = {"frame_interval": frame_interval}
        return requests.post(BASE + endpoint, files=files, data=data, timeout=180)


def poll_job(job_id: str, timeout_sec: int = 120):
    status_url = BASE + f"/jobs/{job_id}"
    result_url = BASE + f"/jobs/{job_id}/result"
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        r = requests.get(status_url, timeout=10)
        print(f"poll {job_id}: {r.status_code} {r.json().get('status')}")
        if r.status_code == 200 and r.json().get("status") in {"completed", "failed"}:
            return requests.get(result_url, timeout=30)
        time.sleep(2)
    raise TimeoutError("Job did not complete in time")


if __name__ == "__main__":
    if not os.path.exists(SAMPLE_IMAGE):
        raise FileNotFoundError(SAMPLE_IMAGE)

    health = wait_for_server(BASE + "/health")
    print_result("GET /health", health)

    info = requests.get(BASE + "/info", timeout=10)
    print_result("GET /info", info)

    with open(SAMPLE_IMAGE, "rb") as f:
        files = {"file": (os.path.basename(SAMPLE_IMAGE), f, "image/jpeg")}
        r = requests.post(BASE + "/moderate-image", files=files, timeout=180)
        print_result("POST /moderate-image", r)

    with open(SAMPLE_IMAGE, "rb") as f:
        files = {"file": (os.path.basename(SAMPLE_IMAGE), f, "image/jpeg")}
        r = requests.post(BASE + "/moderate-media", files=files, timeout=180)
        print_result("POST /moderate-media", r)

    with open(SAMPLE_IMAGE, "rb") as f:
        files = {"file": (os.path.basename(SAMPLE_IMAGE), f, "image/jpeg")}
        r = requests.post(BASE + "/moderate-gif", files=files, timeout=180)
        print_result("POST /moderate-gif with jpg file", r)

    with open(SAMPLE_IMAGE, "rb") as f:
        files = {"file": (os.path.basename(SAMPLE_IMAGE), f, "image/jpeg")}
        r = requests.post(BASE + "/moderate-video", files=files, data={"frame_interval": 5}, timeout=180)
        print_result("POST /moderate-video with jpg file", r)

    r = requests.post(BASE + "/moderate-image", timeout=10)
    print_result("POST /moderate-image empty", r)

    queue_gif = submit_job("/jobs/moderate-gif", SAMPLE_IMAGE)
    print_result("POST /jobs/moderate-gif", queue_gif)
    if queue_gif.status_code == 202:
        job_id = queue_gif.json().get("job_id")
        if job_id:
            result = poll_job(job_id)
            print_result(f"GET /jobs/{job_id}/result", result)

    queue_video = submit_job("/jobs/moderate-video", SAMPLE_IMAGE, frame_interval=5)
    print_result("POST /jobs/moderate-video", queue_video)
    if queue_video.status_code == 202:
        job_id = queue_video.json().get("job_id")
        if job_id:
            result = poll_job(job_id)
            print_result(f"GET /jobs/{job_id}/result", result)
