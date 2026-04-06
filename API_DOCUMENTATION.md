# x02 Vision V2 API Documentation

## Overview

The x02 Vision V2 API provides comprehensive media content moderation for images, GIFs, and videos using EfficientNet-B4 machine learning models. The API supports both synchronous and asynchronous processing with configurable concurrency limits.

## Base URL
```
Production: https://vision.x02.me
Development: http://localhost:8000
```

## Authentication
No authentication required for basic usage. Rate limiting is applied per IP address.

## CORS Policy
Cross-Origin Resource Sharing (CORS) is enabled for all origins:
- **Allow Origins:** * (all origins)
- **Allow Methods:** All HTTP methods (GET, POST, PUT, DELETE, etc.)
- **Allow Headers:** All headers
- **Credentials:** Enabled

## Rate Limits
- All endpoints: 100 requests/minute per IP

## Common Response Headers
- `X-Request-ID`: Unique identifier for request tracing

---

## API Endpoints

### GET /health

Health check endpoint to verify service status and configuration.

**Method:** GET
**Path:** /health
**Rate Limit:** None
**Authentication:** None

**Response (200 OK):**
```json
{
  "status": "healthy",
  "service": "x02 vision v2",
  "model": "EfficientNet-B4",
  "device": "cuda",
  "timestamp": "2026-04-06T12:00:00.000000+00:00",
  "max_concurrent_jobs": 8,
  "queue_worker_count": 4
}
```

**Response Fields:**
- `status`: "healthy" or "degraded"
- `service`: Service name
- `model`: Model type
- `device`: Computing device (cuda/cpu)
- `timestamp`: ISO 8601 timestamp
- `max_concurrent_jobs`: Maximum concurrent processing jobs
- `queue_worker_count`: Number of background workers
- `queued_jobs`: Current number of queued jobs

---

### POST /moderate-image

Moderate a single image for NSFW content.

**Method:** POST
**Path:** /moderate-image
**Content-Type:** multipart/form-data
**Rate Limit:** 100/minute per IP

**Parameters:**
- `file` (file, optional): Image file upload
- `image_url` (string, optional): HTTP/HTTPS URL to image

**Requirements:**
- Exactly one of `file` or `image_url` must be provided
- Supported formats: jpg, jpeg, png, webp, bmp
- Maximum file size: 500 MB
- Maximum download size: 100 MB

**Response (200 OK):**
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

---

### POST /moderate-gif

Moderate a GIF for NSFW content.

**Method:** POST
**Path:** /moderate-gif
**Content-Type:** multipart/form-data
**Rate Limit:** 100/minute per IP

**Parameters:**
- `file` (file, optional): GIF file upload
- `gif_url` (string, optional): HTTP/HTTPS URL to GIF

**Requirements:**
- Exactly one of `file` or `gif_url` must be provided
- Supported formats: gif
- Maximum file size: 500 MB
- Maximum download size: 100 MB

**Response:** Same as image moderation response above.

---

### POST /moderate-video

Moderate a video for NSFW content with configurable frame sampling.

**Method:** POST
**Path:** /moderate-video
**Content-Type:** multipart/form-data
**Rate Limit:** 100/minute per IP

**Parameters:**
- `file` (file, optional): Video file upload
- `video_url` (string, optional): HTTP/HTTPS URL to video
- `frame_interval` (integer, optional, default: 5): Frames to sample per second (1-30)

**Requirements:**
- Exactly one of `file` or `video_url` must be provided
- Supported formats: mp4, avi, mov, mkv, webm, flv, wmv, m4v
- Maximum file size: 500 MB
- Maximum download size: 100 MB

**Response:** Same as image moderation response above, but with multiple frames.

---

### POST /moderate-media

Auto-detect media type and moderate accordingly.

**Method:** POST
**Path:** /moderate-media
**Content-Type:** multipart/form-data
**Rate Limit:** 100/minute per IP

**Parameters:**
- `file` (file, optional): Media file upload
- `media_url` (string, optional): HTTP/HTTPS URL to media
- `frame_interval` (integer, optional, default: 5): Frames to sample per second for videos (1-30)

**Requirements:**
- Exactly one of `file` or `media_url` must be provided
- Auto-detects format from file extension or URL
- Maximum file size: 500 MB
- Maximum download size: 100 MB

**Response:** Same as above endpoints, format depends on detected media type.

---

### POST /jobs/moderate-gif

Queue a GIF moderation job for asynchronous processing.

**Method:** POST
**Path:** /jobs/moderate-gif
**Content-Type:** multipart/form-data
**Response Code:** 202 Accepted
**Rate Limit:** 100/minute per IP

**Parameters:**
- `file` (file, optional): GIF file upload
- `gif_url` (string, optional): HTTP/HTTPS URL to GIF

**Response Code:** 202 Accepted
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "status_url": "/jobs/550e8400-e29b-41d4-a716-446655440000",
  "result_url": "/jobs/550e8400-e29b-41d4-a716-446655440000/result"
}
```

---

### POST /jobs/moderate-video

Queue a video moderation job for asynchronous processing.

**Method:** POST
**Path:** /jobs/moderate-video
**Content-Type:** multipart/form-data
**Response Code:** 202 Accepted
**Rate Limit:** 100/minute per IP

**Parameters:**
- `file` (file, optional): Video file upload
- `video_url` (string, optional): HTTP/HTTPS URL to video
- `frame_interval` (integer, optional, default: 5): Frames to sample per second (1-30)

**Response:** Same as GIF job queue response above.

---

### GET /jobs/{job_id}

Get the status of a queued moderation job.

**Method:** GET
**Path:** /jobs/{job_id}
**Rate Limit:** None

**Path Parameters:**
- `job_id` (string): UUID of the job

**Response (200 OK):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "submitted_at": "2026-04-06T12:00:00.000000+00:00",
  "started_at": "2026-04-06T12:00:05.000000+00:00",
  "completed_at": null
}
```

**Status Values:**
- `queued`: Job is waiting in queue
- `processing`: Job is currently being processed
- `completed`: Job finished successfully
- `failed`: Job failed with error

---

### GET /jobs/{job_id}/result

Get the result of a completed moderation job.

**Method:** GET
**Path:** /jobs/{job_id}/result
**Rate Limit:** None

**Path Parameters:**
- `job_id` (string): UUID of the job

**Response (200 OK):** Same as synchronous moderation endpoints.

**Error Responses:**
- `202 Accepted`: Job still queued or processing
- `404 Not Found`: Job not found
- `500 Internal Server Error`: Job failed (with error details)

---

### GET /info

Get service configuration and capabilities information.

**Method:** GET
**Path:** /info
**Rate Limit:** None

**Response (200 OK):**
```json
{
  "service": "x02 Unified Media Moderation v2",
  "model": "EfficientNet-B4",
  "supported_formats": {
    "images": ["jpg", "jpeg", "png", "webp", "bmp"],
    "videos": ["mp4", "avi", "mov", "mkv", "webm", "flv", "wmv", "m4v"]
  },
  "max_file_size_mb": 500,
  "endpoints": {
    "health": "GET /health",
    "image": "POST /moderate-image",
    "gif": "POST /moderate-gif",
    "video": "POST /moderate-video",
    "auto": "POST /moderate-media",
    "queue_gif": "POST /jobs/moderate-gif",
    "queue_video": "POST /jobs/moderate-video",
    "job_status": "GET /jobs/{job_id}",
    "job_result": "GET /jobs/{job_id}/result"
  },
  "categories": {
    "0": "hentai",
    "1": "nsfw_real",
    "2": "sfw_anime",
    "3": "sfw_real"
  },
  "thresholds": {
    "allow": "< 40",
    "soft_flag": "40-80",
    "hard_block": "> 80"
  },
  "max_concurrent_jobs": 8,
  "queue_worker_count": 4
}
```

---

## Response Format Details

### Moderation Results

**recommendation**: Overall decision
- `"allow"`: Content is safe
- `"soft_flag"`: Content may be inappropriate, review recommended
- `"hard_block"`: Content is inappropriate, block recommended

**aggregated_scores**:
- `average_score`: Mean NSFW score across all frames (0-100)
- `max_score`: Highest NSFW score
- `min_score`: Lowest NSFW score
- `median_score`: Median NSFW score
- `std_dev`: Standard deviation of scores
- `flagged_frames_soft`: Frames with score 40-80
- `flagged_frames_hard`: Frames with score >80
- `flagged_percentage`: Percentage of flagged frames
- `total_frames`: Total number of frames analyzed

**frame_results**:
- `frame_scores`: Array of individual frame scores
- `individual_results`: Detailed per-frame results (usually empty for brevity)
- `frame_count`: Number of frames processed

**decision_reasoning**:
- `average_nsfw_score`: Same as aggregated_scores.average_score
- `max_nsfw_score`: Same as aggregated_scores.max_score
- `flagged_percentage`: Same as aggregated_scores.flagged_percentage
- `decision_rule`: Text explanation of decision logic

### Decision Rules

- **Allow**: `max_score < 40` OR (`flagged_percentage < 30` AND `average_score < 40`)
- **Soft Flag**: `flagged_percentage >= 30` OR `average_score >= 40`
- **Hard Block**: `max_score >= 85`

---

## Error Responses

### Common HTTP Status Codes

- `200`: Success
- `202`: Accepted (for queued jobs)
- `400`: Bad Request - Invalid input parameters
- `413`: Payload Too Large - File exceeds size limit
- `415`: Unsupported Media Type - Invalid file format
- `422`: Unprocessable Entity - All frames failed inference
- `429`: Too Many Requests - Rate limit exceeded
- `502`: Bad Gateway - Remote download failed
- `504`: Gateway Timeout - Remote download timed out

### Error Response Format
```json
{
  "detail": "Error description message"
}
```

### Rate Limit Response
```json
{
  "error": "rate_limit_exceeded",
  "detail": "Too many requests",
  "recommendation": "soft_flag"
}
```

---

## Usage Examples

### Moderate an uploaded image
```bash
curl -X POST https://vision.x02.me/moderate-image \
  -F "file=@image.jpg"
```

### Moderate an image by URL
```bash
curl -X POST https://vision.x02.me/moderate-image \
  -F "image_url=https://example.com/image.jpg"
```

### Moderate a video with custom frame interval
```bash
curl -X POST https://vision.x02.me/moderate-video \
  -F "file=@video.mp4" \
  -F "frame_interval=10"
```

### Queue a long video for processing
```bash
curl -X POST https://vision.x02.me/jobs/moderate-video \
  -F "video_url=https://example.com/long-video.mp4"
```

### Check job status
```bash
curl https://vision.x02.me/jobs/550e8400-e29b-41d4-a716-446655440000
```

### Get job result
```bash
curl https://vision.x02.me/jobs/550e8400-e29b-41d4-a716-446655440000/result
```

### Health check
```bash
curl https://vision.x02.me/health
```

### Service information
```bash
curl https://vision.x02.me/info
```

---

## Python SDK Examples

### Basic Image Moderation
```python
import requests

def moderate_image(file_path=None, image_url=None):
    """Moderate an image file or URL."""
    url = "https://vision.x02.me/moderate-image"

    if file_path:
        with open(file_path, 'rb') as f:
            response = requests.post(url, files={'file': f})
    elif image_url:
        response = requests.post(url, data={'image_url': image_url})
    else:
        raise ValueError("Must provide file_path or image_url")

    return response.json()

# Usage
result = moderate_image(image_url="https://example.com/image.jpg")
print(f"Recommendation: {result['recommendation']}")
```

### Video Moderation with Custom Settings
```python
import requests

def moderate_video(file_path=None, video_url=None, frame_interval=5):
    """Moderate a video with custom frame sampling."""
    url = "https://vision.x02.me/moderate-video"

    data = {'frame_interval': frame_interval}

    if file_path:
        with open(file_path, 'rb') as f:
            response = requests.post(url, files={'file': f}, data=data)
    elif video_url:
        data['video_url'] = video_url
        response = requests.post(url, data=data)
    else:
        raise ValueError("Must provide file_path or video_url")

    return response.json()

# Usage
result = moderate_video(video_url="https://example.com/video.mp4", frame_interval=10)
print(f"Flagged frames: {result['aggregated_scores']['flagged_percentage']}%")
```

### Async Job Processing
```python
import requests
import time

def queue_video_job(video_url, frame_interval=5):
    """Queue a video for async processing."""
    url = "https://vision.x02.me/jobs/moderate-video"

    data = {
        'video_url': video_url,
        'frame_interval': frame_interval
    }

    response = requests.post(url, data=data)
    return response.json()

def check_job_status(job_id):
    """Check the status of a queued job."""
    url = f"https://vision.x02.me/jobs/{job_id}"
    response = requests.get(url)
    return response.json()

def get_job_result(job_id):
    """Get the result of a completed job."""
    url = f"https://vision.x02.me/jobs/{job_id}/result"
    response = requests.get(url)
    return response.json()

# Usage
job = queue_video_job("https://example.com/long-video.mp4")
print(f"Job ID: {job['job_id']}")

# Poll for completion
while True:
    status = check_job_status(job['job_id'])
    print(f"Status: {status['status']}")

    if status['status'] == 'completed':
        result = get_job_result(job['job_id'])
        print(f"Result: {result['recommendation']}")
        break
    elif status['status'] == 'failed':
        print("Job failed")
        break

    time.sleep(5)  # Wait 5 seconds before checking again
```

### JavaScript/Node.js Examples
```javascript
// Using fetch API
async function moderateImage(imageUrl) {
    const formData = new FormData();
    formData.append('image_url', imageUrl);

    const response = await fetch('https://vision.x02.me/moderate-image', {
        method: 'POST',
        body: formData
    });

    const result = await response.json();
    return result;
}

// Usage
moderateImage('https://example.com/image.jpg')
    .then(result => {
        console.log(`Recommendation: ${result.recommendation}`);
        console.log(`Score: ${result.aggregated_scores.average_score}`);
    });
```

---

## File Size Limits

- Maximum upload file size: 500 MB
- Maximum download size: 100 MB
- Temporary files are automatically cleaned up after processing

## Supported Media Formats

### Images
- JPEG (.jpg, .jpeg)
- PNG (.png)
- WebP (.webp)
- BMP (.bmp)

### Videos
- MP4 (.mp4)
- AVI (.avi)
- MOV (.mov)
- MKV (.mkv)
- WebM (.webm)
- FLV (.flv)
- WMV (.wmv)
- M4V (.m4v)

### GIFs
- GIF (.gif)

## Security Features

- Only HTTP/HTTPS URLs accepted
- Private/local network addresses blocked
- File type validation by extension
- Automatic temporary file cleanup
- Request ID tracing for debugging
- Rate limiting per IP address

## Performance Notes

- Concurrent jobs limited to 8 by default
- Background queue workers: 4 by default
- Frame sampling interval: 5 FPS by default
- GPU acceleration when CUDA available
- OCR has been removed for better performance

---

## Integration Guide

### Content Moderation Workflow

1. **Receive content** (image, video, GIF, or URL)
2. **Call appropriate endpoint** based on content type
3. **Check recommendation**:
   - `allow`: Content is safe, proceed
   - `soft_flag`: Content may be inappropriate, review manually
   - `hard_block`: Content is inappropriate, block/reject
4. **Log decision** with request ID for auditing
5. **Handle errors** gracefully (rate limits, network issues)

### Error Handling Best Practices

```python
def safe_moderate_content(content_url, content_type='auto'):
    """Safely moderate content with proper error handling."""
    try:
        if content_type == 'image':
            result = requests.post(
                'https://vision.x02.me/moderate-image',
                data={'image_url': content_url},
                timeout=30
            )
        elif content_type == 'video':
            result = requests.post(
                'https://vision.x02.me/moderate-video',
                data={'video_url': content_url},
                timeout=60
            )
        else:
            # Auto-detect
            result = requests.post(
                'https://vision.x02.me/moderate-media',
                data={'media_url': content_url},
                timeout=60
            )

        result.raise_for_status()
        data = result.json()

        return {
            'success': True,
            'recommendation': data['recommendation'],
            'score': data['aggregated_scores']['average_score'],
            'request_id': result.headers.get('X-Request-ID')
        }

    except requests.exceptions.Timeout:
        return {'success': False, 'error': 'timeout', 'recommendation': 'soft_flag'}
    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': 'network', 'recommendation': 'soft_flag'}
    except Exception as e:
        return {'success': False, 'error': 'unknown', 'recommendation': 'soft_flag'}
```

### Rate Limit Handling

```python
def moderate_with_retry(content_url, max_retries=3):
    """Moderate content with automatic retry on rate limits."""
    for attempt in range(max_retries):
        try:
            result = requests.post(
                'https://vision.x02.me/moderate-image',
                data={'image_url': content_url}
            )

            if result.status_code == 429:
                # Rate limited, wait and retry
                wait_time = 2 ** attempt  # Exponential backoff
                time.sleep(wait_time)
                continue

            result.raise_for_status()
            return result.json()

        except requests.exceptions.RequestException:
            if attempt == max_retries - 1:
                raise
            time.sleep(1)

    raise Exception("Max retries exceeded")
```

---

## API Changelog

### Version 2.2.0 (Current)
- Removed OCR for improved performance
- Increased rate limit to 100/minute
- Increased concurrent jobs to 8
- Increased queue workers to 4

### Version 2.1.0
- Added async job queue for long videos
- Improved decision rules
- Enhanced error handling and logging
- Added request ID tracing