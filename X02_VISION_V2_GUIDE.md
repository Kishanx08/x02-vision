# x02 Vision V2 API

## Overview

This service is a FastAPI app for moderating:
- Images
- GIFs
- Videos
- Remote HTTP/HTTPS URLs

It uses:
- [efficientnet_model.py](efficientnet_model.py) for EfficientNet-B4 inference
- [media_processor.py](media_processor.py) for download, extraction, and aggregation
- [x02_vision_v2_api.py](x02_vision_v2_api.py) for the API layer
- [services/job_queue.py](services/job_queue.py) for async GIF/video jobs

## Production behavior

- Uploaded files are written to temporary files and deleted after processing.
- URL inputs are downloaded to a temporary file and deleted after processing, including on failures after download.
- Only `http` and `https` URLs are accepted.
- Requests to private or local addresses are blocked to reduce SSRF risk.
- Moderation work runs in a threadpool with bounded concurrency.
- GIF and video jobs can also be submitted to a background queue.
- Each response includes an `X-Request-ID` header for tracing.

## Endpoints

### `GET /health`

Returns service status, device, timestamp, and configured concurrency.

### `POST /moderate-image`

Accepts either:
- `file`
- `image_url`

### `POST /moderate-gif`

Accepts either:
- `file`
- `gif_url`

### `POST /moderate-video`

Accepts either:
- `file`
- `video_url`

Optional:
- `frame_interval` from `1` to `30`

### `POST /moderate-media`

Auto-detects uploaded or remote media type.

Accepts either:
- `file`
- `media_url`

Optional:
- `frame_interval` from `1` to `30`

### `GET /info`

Returns supported formats, categories, thresholds, and concurrency config.

### `POST /jobs/moderate-gif`

Queues a GIF job and returns `202` with a `job_id`.

### `POST /jobs/moderate-video`

Queues a video job and returns `202` with a `job_id`.

### `GET /jobs/{job_id}`

Returns job status: `queued`, `processing`, `completed`, or `failed`.

### `GET /jobs/{job_id}/result`

Returns the completed moderation result.

## Validation rules

- Exactly one of file or URL must be provided.
- Empty uploads return `400`.
- Invalid URL schemes return `400`.
- Unsupported types return `415`.
- Oversized uploads or downloads return `413`.

## HTTP status codes

- `200`: moderation completed successfully
- `400`: bad input, empty upload, invalid scheme, blocked URL
- `413`: file too large
- `415`: unsupported media type
- `422`: all extracted frames failed inference
- `429`: rate limit exceeded
- `502`: remote download failed
- `504`: remote download timed out

## OCR text moderation

OCR has been removed for better performance.

## Example requests

### Upload an image

```bash
curl -X POST http://localhost:8000/moderate-image \
  -F "file=@image.jpg"
```

### Moderate an image by URL

```bash
curl -X POST http://localhost:8000/moderate-image \
  -F "image_url=https://example.com/image.jpg"
```

### Upload a video

```bash
curl -X POST http://localhost:8000/moderate-video \
  -F "file=@video.mp4" \
  -F "frame_interval=5"
```

### Unified endpoint

```bash
curl -X POST http://localhost:8000/moderate-media \
  -F "media_url=https://example.com/video.mp4" \
  -F "frame_interval=5"
```

## Response shape

Successful responses include:

```json
{
  "model": "x02_vision_v2_efficientnet_b4",
  "media_type": "image",
  "source": "upload",
  "recommendation": "allow",
  "aggregated_scores": {
    "average_score": 2.5,
    "max_score": 5.3,
    "min_score": 0.2,
    "median_score": 2.5,
    "std_dev": 1.7,
    "flagged_frames_soft": 0,
    "flagged_frames_hard": 0,
    "flagged_percentage": 0.0,
    "total_frames": 1
  },
  "frame_results": {
    "frame_scores": [2.5],
    "individual_results": [],
    "frame_count": 1
  },
  "decision_reasoning": {
    "average_nsfw_score": 2.5,
    "max_nsfw_score": 5.3,
    "flagged_percentage": 0.0,
    "decision_rule": "All frames safe, average score < 40%"
  },
  "inference_time_ms": 234
}
```

Error responses include:

```json
{
  "detail": "Unsupported file format: .txt"
}
```

## Decision rules

- `hard_block` if `max_score > 85`
- `soft_flag` if `flagged_percentage > 30` or `average_score > 40`
- `allow` otherwise

## Concurrency notes

- The app allows several moderation jobs to run at once per process.
- The current default is `8` concurrent jobs per process.
- Rate limit is 100 requests per minute per IP.

## Ubuntu VPS deployment

Install system packages first:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nginx
```

Create a virtual environment and install Python packages:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Run locally:

```bash
python x02_vision_v2_api.py
```

Recommended production command behind Nginx:

```bash
uvicorn x02_vision_v2_api:app --host 127.0.0.1 --port 8000 --workers 1
```

Notes:
- Keep `workers=1` if you are using one GPU-bound model copy.
- On CPU-only VPS, you can consider more than one worker, but each worker loads its own model into memory.
- Put Nginx in front for TLS, request buffering, and public exposure.
- PM2 and an example Nginx site file are included in this folder.
- See [DEPLOY_UBUNTU.md](DEPLOY_UBUNTU.md) for the full VPS setup.

## Temporary file cleanup

Yes, URL moderation downloads the remote media to a temporary file first.

That temporary file is deleted in the `finally` block in [media_processor.py](media_processor.py#L503), so it is cleaned up after processing completes or if processing raises after the download step.

Uploaded files are also deleted after each request in [x02_vision_v2_api.py](x02_vision_v2_api.py).
