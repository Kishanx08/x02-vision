"""
x02 Vision V2 Service
Production-ready FastAPI service for Image/GIF/Video moderation.
"""

import asyncio
import logging
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlparse

import torch
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.concurrency import run_in_threadpool

from efficientnet_model import X02VisionGuardV2
from media_processor import (
    BlockedURLError,
    DownloadFailedError,
    DownloadTimeoutError,
    FileTooLargeError,
    FrameInferenceFailedError,
    MediaProcessor,
    UnsupportedMediaTypeError,
)
from services.job_queue import JobQueueManager

IMAGE_EXTENSIONS = MediaProcessor.SUPPORTED_IMAGE_FORMATS
GIF_EXTENSIONS = {".gif"}
VIDEO_EXTENSIONS = MediaProcessor.SUPPORTED_VIDEO_FORMATS


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
logger.info("Using device: %s", DEVICE)

CONFIG = {
    "max_file_size": 500 * 1024 * 1024,
    "max_download_size": 100 * 1024 * 1024,
    "frame_interval": 5,
    "timeout": 30,
    "max_concurrent_jobs": 8,
    "queue_worker_count": 4,
    "torch_num_threads": 12,
    "max_batch_images": 50,
}

model = None
media_processor = None
inference_semaphore = asyncio.Semaphore(CONFIG["max_concurrent_jobs"])
job_queue_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model, media_processor, job_queue_manager

    logger.info("Starting up x02 Vision V2 Service")
    torch.set_num_threads(CONFIG["torch_num_threads"])

    model = X02VisionGuardV2(num_classes=4, pretrained=False)

    model_path = "x02_vision_v2_efficientnet_b4_best.pth"
    if Path(model_path).exists():
        model.load_model(model_path, device=DEVICE)
        logger.info("Model loaded from %s", model_path)
    else:
        logger.warning("Model weights not found at %s, using base model", model_path)

    model.eval()
    media_processor = MediaProcessor(
        model=model,
        device=DEVICE,
        frame_interval=CONFIG["frame_interval"],
        timeout=CONFIG["timeout"],
    )
    job_queue_manager = JobQueueManager(
        worker_count=CONFIG["queue_worker_count"],
        process_job=process_queue_job,
    )
    await job_queue_manager.start()

    logger.info("Service initialized successfully")
    try:
        yield
    finally:
        if job_queue_manager is not None:
            await job_queue_manager.stop()


app = FastAPI(
    title="x02 Vision V2",
    description="Image, GIF, and Video content moderation using EfficientNet-B4",
    version="2.1.0",
    lifespan=lifespan,
)

# Enable CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter


def get_request_id(request: Request) -> str:
    """Get or assign a request ID for request tracing."""
    if not hasattr(request.state, "request_id"):
        request.state.request_id = str(uuid.uuid4())
    return request.state.request_id


def validate_input_url(url: str) -> None:
    """Ensure only HTTP(S) URLs are accepted."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Invalid URL scheme")
    if not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid URL")


def get_file_extension_from_upload(upload: UploadFile) -> str:
    return Path(upload.filename or "").suffix.lower()


def get_file_extension_from_url(url: str) -> str:
    return Path(urlparse(url).path).suffix.lower()


def validate_file_upload_format(
    upload: UploadFile, allowed_extensions: set[str], endpoint_name: str
) -> None:
    ext = get_file_extension_from_upload(upload)
    if not ext:
        raise HTTPException(
            status_code=400,
            detail=f"{endpoint_name} uploads must include a file extension",
        )
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type for {endpoint_name}. Expected one of: {', '.join(sorted(allowed_extensions))}.",
        )


def validate_url_format(
    url: str, allowed_extensions: set[str], endpoint_name: str
) -> None:
    ext = get_file_extension_from_url(url)
    if not ext:
        return
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported URL media type for {endpoint_name}. Expected one of: {', '.join(sorted(allowed_extensions))}.",
        )


def to_http_exception(exc: Exception) -> HTTPException:
    """Translate domain failures to stable HTTP responses."""
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, FileTooLargeError):
        return HTTPException(status_code=413, detail=str(exc))
    if isinstance(exc, UnsupportedMediaTypeError):
        return HTTPException(status_code=415, detail=str(exc))
    if isinstance(exc, DownloadTimeoutError):
        return HTTPException(status_code=504, detail=str(exc))
    if isinstance(exc, (DownloadFailedError,)):
        return HTTPException(status_code=502, detail=str(exc))
    if isinstance(exc, BlockedURLError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, FrameInferenceFailedError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="Internal server error")


def build_job_payload(
    *,
    endpoint: str,
    source_value: str,
    is_url: bool,
    frame_interval: Optional[int] = None,
    cleanup_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an internal queue payload for async moderation jobs."""
    return {
        "endpoint": endpoint,
        "source_value": source_value,
        "is_url": is_url,
        "frame_interval": frame_interval,
        "cleanup_path": cleanup_path,
    }


async def save_upload_to_temp(upload: UploadFile, fallback_suffix: str = "") -> str:
    """Persist an uploaded file while preserving its suffix when possible."""
    original_suffix = Path(upload.filename or "").suffix
    suffix = original_suffix or fallback_suffix

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await upload.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty upload")
        if len(content) > CONFIG["max_file_size"]:
            raise HTTPException(status_code=413, detail="File too large")
        tmp.write(content)
        return tmp.name


async def process_media_request(
    request: Request,
    *,
    source_value: str,
    is_url: bool,
    frame_interval: Optional[int] = None,
) -> dict:
    """Run media processing in a worker thread with request-scoped logging."""
    req_id = get_request_id(request)
    logger.info(
        "%s start path=%s is_url=%s frame_interval=%s",
        req_id,
        source_value if is_url else "upload",
        is_url,
        frame_interval,
    )
    started_at = time.time()

    try:
        async with inference_semaphore:
            result = await run_in_threadpool(
                media_processor.process_media,
                source_value,
                is_url,
                frame_interval,
            )
    except Exception as exc:
        http_exc = to_http_exception(exc)
        logger.warning(
            "%s failed status=%s detail=%s",
            req_id,
            http_exc.status_code,
            http_exc.detail,
        )
        raise http_exc from exc

    result["inference_time_ms"] = int((time.time() - started_at) * 1000)
    logger.info("%s complete recommendation=%s", req_id, result.get("recommendation"))
    return result


async def process_queue_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """Run one queued moderation job."""
    async with inference_semaphore:
        return await run_in_threadpool(
            media_processor.process_media,
            job["source_value"],
            job["is_url"],
            job.get("frame_interval"),
        )


@app.middleware("http")
async def add_request_id_middleware(request: Request, call_next):
    """Add an ID to each request for tracing."""
    request_id = get_request_id(request)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy" if model and media_processor else "degraded",
        "service": "x02 vision v2",
        "model": "EfficientNet-B4",
        "device": DEVICE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "max_concurrent_jobs": CONFIG["max_concurrent_jobs"],
        "queue_worker_count": CONFIG["queue_worker_count"],
        "queued_jobs": job_queue_manager.size() if job_queue_manager else 0,
    }


@app.post("/moderate-image")
@limiter.limit("10/minute")
async def moderate_image(
    request: Request,
    file: Optional[UploadFile] = File(None),
    image_url: Optional[str] = Form(None),
):
    """Moderate a single image."""
    if not file and not image_url:
        raise HTTPException(status_code=400, detail="Either file or image_url required")
    if file and image_url:
        raise HTTPException(
            status_code=400, detail="Provide either file or image_url, not both"
        )
    if image_url:
        validate_input_url(image_url)
        validate_url_format(image_url, IMAGE_EXTENSIONS, "image")

    if file:
        validate_file_upload_format(file, IMAGE_EXTENSIONS, "image")
        temp_path = await save_upload_to_temp(file, fallback_suffix=".jpg")
        try:
            return await process_media_request(
                request, source_value=temp_path, is_url=False
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

    return await process_media_request(request, source_value=image_url, is_url=True)


@app.post("/moderate-gif")
@limiter.limit("5/minute")
async def moderate_gif(
    request: Request,
    file: Optional[UploadFile] = File(None),
    gif_url: Optional[str] = Form(None),
):
    """Moderate a GIF."""
    if not file and not gif_url:
        raise HTTPException(status_code=400, detail="Either file or gif_url required")
    if file and gif_url:
        raise HTTPException(
            status_code=400, detail="Provide either file or gif_url, not both"
        )
    if gif_url:
        validate_input_url(gif_url)
        validate_url_format(gif_url, GIF_EXTENSIONS, "gif")

    if file:
        validate_file_upload_format(file, GIF_EXTENSIONS, "gif")
        temp_path = await save_upload_to_temp(file, fallback_suffix=".gif")
        try:
            return await process_media_request(
                request, source_value=temp_path, is_url=False
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

    return await process_media_request(request, source_value=gif_url, is_url=True)


@app.post("/moderate-video")
@limiter.limit("3/minute")
async def moderate_video(
    request: Request,
    file: Optional[UploadFile] = File(None),
    video_url: Optional[str] = Form(None),
    frame_interval: Optional[int] = Form(5),
):
    """Moderate a video."""
    if not file and not video_url:
        raise HTTPException(status_code=400, detail="Either file or video_url required")
    if file and video_url:
        raise HTTPException(
            status_code=400, detail="Provide either file or video_url, not both"
        )
    if video_url:
        validate_input_url(video_url)
        validate_url_format(video_url, VIDEO_EXTENSIONS, "video")
    if frame_interval is None or frame_interval < 1 or frame_interval > 30:
        raise HTTPException(
            status_code=400, detail="frame_interval must be between 1 and 30"
        )

    if file:
        validate_file_upload_format(file, VIDEO_EXTENSIONS, "video")
        temp_path = await save_upload_to_temp(file, fallback_suffix=".mp4")
        try:
            return await process_media_request(
                request,
                source_value=temp_path,
                is_url=False,
                frame_interval=frame_interval,
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

    return await process_media_request(
        request,
        source_value=video_url,
        is_url=True,
        frame_interval=frame_interval,
    )


@app.post("/moderate-media")
@limiter.limit("10/minute")
async def moderate_media(
    request: Request,
    file: Optional[UploadFile] = File(None),
    media_url: Optional[str] = Form(None),
    frame_interval: Optional[int] = Form(5),
):
    """Auto-detect and moderate an image, GIF, or video."""
    if not file and not media_url:
        raise HTTPException(status_code=400, detail="Either file or media_url required")
    if file and media_url:
        raise HTTPException(
            status_code=400, detail="Provide either file or media_url, not both"
        )
    if media_url:
        validate_input_url(media_url)
    if frame_interval is None or frame_interval < 1 or frame_interval > 30:
        raise HTTPException(
            status_code=400, detail="frame_interval must be between 1 and 30"
        )

    if file:
        temp_path = await save_upload_to_temp(file)
        try:
            return await process_media_request(
                request,
                source_value=temp_path,
                is_url=False,
                frame_interval=frame_interval,
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

    return await process_media_request(
        request,
        source_value=media_url,
        is_url=True,
        frame_interval=frame_interval,
    )


async def create_async_job(
    request: Request,
    *,
    endpoint: str,
    file: Optional[UploadFile],
    source_url: Optional[str],
    fallback_suffix: str,
    frame_interval: Optional[int] = None,
) -> Dict[str, Any]:
    """Create a queued moderation job for longer-running media."""
    if not file and not source_url:
        raise HTTPException(
            status_code=400, detail=f"Either file or {endpoint}_url required"
        )
    if file and source_url:
        raise HTTPException(
            status_code=400, detail="Provide either file or URL, not both"
        )
    if source_url:
        validate_input_url(source_url)

    request_id = get_request_id(request)

    if file:
        temp_path = await save_upload_to_temp(file, fallback_suffix=fallback_suffix)
        payload = build_job_payload(
            endpoint=endpoint,
            source_value=temp_path,
            is_url=False,
            frame_interval=frame_interval,
            cleanup_path=temp_path,
        )
    else:
        payload = build_job_payload(
            endpoint=endpoint,
            source_value=source_url,
            is_url=True,
            frame_interval=frame_interval,
            cleanup_path=None,
        )

    job = await job_queue_manager.submit(payload, request_id)
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "status_url": f"/jobs/{job['job_id']}",
        "result_url": f"/jobs/{job['job_id']}/result",
    }


@app.post("/jobs/moderate-gif", status_code=202)
@limiter.limit("10/minute")
async def queue_moderate_gif(
    request: Request,
    file: Optional[UploadFile] = File(None),
    gif_url: Optional[str] = Form(None),
    enable_ocr: bool = Form(True),
):
    """Queue a GIF moderation job."""
    if gif_url:
        validate_input_url(gif_url)
        validate_url_format(gif_url, GIF_EXTENSIONS, "gif")
    if file:
        validate_file_upload_format(file, GIF_EXTENSIONS, "gif")

    return await create_async_job(
        request,
        endpoint="gif",
        file=file,
        source_url=gif_url,
        fallback_suffix=".gif",
    )


@app.post("/jobs/moderate-video", status_code=202)
@limiter.limit("10/minute")
async def queue_moderate_video(
    request: Request,
    file: Optional[UploadFile] = File(None),
    video_url: Optional[str] = Form(None),
    frame_interval: Optional[int] = Form(5),
):
    """Queue a video moderation job."""
    if frame_interval is None or frame_interval < 1 or frame_interval > 30:
        raise HTTPException(
            status_code=400, detail="frame_interval must be between 1 and 30"
        )
    if video_url:
        validate_input_url(video_url)
        validate_url_format(video_url, VIDEO_EXTENSIONS, "video")
    if file:
        validate_file_upload_format(file, VIDEO_EXTENSIONS, "video")

    return await create_async_job(
        request,
        endpoint="video",
        file=file,
        source_url=video_url,
        fallback_suffix=".mp4",
        frame_interval=frame_interval,
    )


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get background moderation job status."""
    job = job_queue_manager.get(job_id) if job_queue_manager else None
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response = {
        "job_id": job_id,
        "status": job["status"],
        "submitted_at": job.get("submitted_at"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
    }
    if job["status"] == "failed":
        response["error"] = job.get("error")
    return response


@app.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    """Get a completed moderation job result."""
    job = job_queue_manager.get(job_id) if job_queue_manager else None
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] == "queued":
        raise HTTPException(status_code=202, detail="Job still queued")
    if job["status"] == "processing":
        raise HTTPException(status_code=202, detail="Job still processing")
    if job["status"] == "failed":
        error = job.get("error", {})
        raise HTTPException(
            status_code=error.get("status_code", 500),
            detail=error.get("detail", "Job failed"),
        )
    return job["result"]


@app.get("/info")
async def info():
    """Get service information."""
    return {
        "service": "x02 Unified Media Moderation v2",
        "model": "EfficientNet-B4",
        "supported_formats": {
            "images": list(MediaProcessor.SUPPORTED_IMAGE_FORMATS),
            "videos": list(MediaProcessor.SUPPORTED_VIDEO_FORMATS),
        },
        "max_file_size_mb": CONFIG["max_file_size"] / (1024 * 1024),
        "endpoints": {
            "health": "GET /health",
            "image": "POST /moderate-image",
            "gif": "POST /moderate-gif",
            "video": "POST /moderate-video",
            "auto": "POST /moderate-media",
            "queue_gif": "POST /jobs/moderate-gif",
            "queue_video": "POST /jobs/moderate-video",
            "job_status": "GET /jobs/{job_id}",
            "job_result": "GET /jobs/{job_id}/result",
        },
        "categories": {
            "0": "hentai",
            "1": "nsfw_real",
            "2": "sfw_anime",
            "3": "sfw_real",
        },
        "thresholds": {
            "allow": "< 40",
            "soft_flag": "40-80",
            "hard_block": "> 80",
        },
        "max_concurrent_jobs": CONFIG["max_concurrent_jobs"],
        "queue_worker_count": CONFIG["queue_worker_count"],
    }


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limiting."""
    return JSONResponse(
        status_code=429,
        headers={"X-Request-ID": get_request_id(request)},
        content={
            "error": "rate_limit_exceeded",
            "detail": "Too many requests",
            "recommendation": "soft_flag",
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions."""
    logger.exception("%s unhandled exception", get_request_id(request), exc_info=exc)
    return JSONResponse(
        status_code=500,
        headers={"X-Request-ID": get_request_id(request)},
        content={
            "error": "internal_server_error",
            "detail": str(exc),
            "recommendation": "soft_flag",
        },
    )


if __name__ == "__main__":
    uvicorn.run(
        "x02_vision_v2_api:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        workers=1,
    )
