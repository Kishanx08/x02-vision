"""
x02 Media Processor - Handles Images, GIFs, and Videos
Extracts frames, classifies using EfficientNet-B4
Supports both file uploads and remote URLs
"""

import cv2
import numpy as np
from PIL import Image
import requests
import tempfile
import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import logging
from urllib.parse import urlparse
import socket
import ipaddress

from services.text_moderation_service import TextModerationService

logger = logging.getLogger(__name__)


class MediaProcessingError(Exception):
    """Base exception for media moderation failures."""


class UnsupportedMediaTypeError(MediaProcessingError):
    """Raised when the media type cannot be determined or is unsupported."""


class FileTooLargeError(MediaProcessingError):
    """Raised when a file exceeds the allowed size."""


class DownloadFailedError(MediaProcessingError):
    """Raised when a remote download fails."""


class DownloadTimeoutError(MediaProcessingError):
    """Raised when a remote download times out."""


class BlockedURLError(MediaProcessingError):
    """Raised when a URL targets a blocked/private address."""


class FrameInferenceFailedError(MediaProcessingError):
    """Raised when all extracted frames fail during inference."""


class MediaProcessor:
    """Process different media types: images, GIFs, videos"""

    SUPPORTED_IMAGE_FORMATS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
    SUPPORTED_VIDEO_FORMATS = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm"}
    MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
    MAX_DOWNLOAD_SIZE = 100 * 1024 * 1024  # 100MB for remote files

    def __init__(
        self,
        model,
        device="cpu",
        frame_interval=5,
        timeout=30,
        batch_size: Optional[int] = None,
        enable_ocr: bool = True,
        text_moderation_service: Optional[TextModerationService] = None,
    ):
        """
        Initialize media processor

        Args:
            model: EfficientNet-B4 model
            device: 'cpu' or 'cuda'
            frame_interval: Extract every Nth frame for video (5 = every 5th)
            timeout: Download timeout in seconds
        """
        self.model = model
        self.device = device
        self.frame_interval = frame_interval
        self.timeout = timeout
        self.temp_dir = tempfile.gettempdir()
        self.batch_size = batch_size or (16 if device == "cuda" else 8)
        self.enable_ocr = enable_ocr
        self.text_moderation_service = (
            text_moderation_service or TextModerationService()
        )

    def get_file_type(self, file_path: str) -> str:
        """Determine if file is image, gif, or video"""
        ext = Path(file_path).suffix.lower()

        if ext == ".gif":
            return "gif"
        elif ext in self.SUPPORTED_IMAGE_FORMATS:
            return "image"
        elif ext in self.SUPPORTED_VIDEO_FORMATS:
            return "video"
        else:
            raise UnsupportedMediaTypeError(
                f"Unsupported file format: {ext or 'missing extension'}"
            )

    def validate_remote_url(self, url: str) -> None:
        """Block obvious SSRF targets by rejecting private and local addresses."""
        parsed = urlparse(url)
        host = parsed.hostname

        if not host:
            raise DownloadFailedError("URL is missing a hostname")
        if host.lower() == "localhost":
            raise BlockedURLError("Blocked URL")

        try:
            addrinfo = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise DownloadFailedError(f"Could not resolve host: {host}") from exc

        for entry in addrinfo:
            ip_str = entry[4][0]
            ip_obj = ipaddress.ip_address(ip_str)
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_multicast
                or ip_obj.is_reserved
                or ip_obj.is_unspecified
            ):
                raise BlockedURLError("Blocked URL")

    def download_file(self, url: str) -> str:
        """
        Download file from URL to temp location

        Args:
            url: URL to download from

        Returns:
            Path to downloaded file
        """
        try:
            logger.info(f"Downloading from: {url}")
            self.validate_remote_url(url)

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            try:
                response = requests.get(
                    url, timeout=self.timeout, headers=headers, stream=True
                )
            except requests.Timeout as exc:
                raise DownloadTimeoutError("Download timed out") from exc
            except requests.RequestException as exc:
                raise DownloadFailedError(f"Download request failed: {exc}") from exc
            response.raise_for_status()

            # Check file size
            content_length = int(response.headers.get("content-length", 0))
            if content_length > self.MAX_DOWNLOAD_SIZE:
                raise FileTooLargeError(
                    f"File too large: {content_length} bytes (max {self.MAX_DOWNLOAD_SIZE})"
                )

            # Get file extension from URL or content-type
            ext = Path(urlparse(url).path).suffix.lower()
            if not ext:
                content_type = response.headers.get("content-type", "").lower()
                if "image/gif" in content_type:
                    ext = ".gif"
                elif "image" in content_type:
                    ext = ".jpg"
                elif "video" in content_type:
                    ext = ".mp4"
                else:
                    ext = ".tmp"

            # Save to temp file
            temp_path = os.path.join(
                self.temp_dir, f"x02_download_{os.getpid()}_{hash(url) % 10000}{ext}"
            )

            with open(temp_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        if os.path.getsize(temp_path) > self.MAX_DOWNLOAD_SIZE:
                            os.remove(temp_path)
                            raise FileTooLargeError("File too large during download")

            logger.info(f"Downloaded successfully: {temp_path}")
            return temp_path

        except Exception as e:
            logger.error(f"Download error: {e}")
            raise

    def extract_image_frames(self, image_path: str) -> List[np.ndarray]:
        """
        Extract frames from image file

        Args:
            image_path: Path to image

        Returns:
            List containing single frame
        """
        try:
            image = Image.open(image_path).convert("RGB")
            frame = np.array(image)
            return [frame]
        except Exception as e:
            logger.error(f"Error reading image: {e}")
            raise

    def extract_gif_frames(self, gif_path: str) -> List[np.ndarray]:
        """
        Extract all frames from GIF

        Args:
            gif_path: Path to GIF file

        Returns:
            List of frames as numpy arrays
        """
        try:
            logger.info(f"Extracting GIF frames from: {gif_path}")

            gif = Image.open(gif_path)
            frames = []

            # Extract all frames
            for frame_idx in range(gif.n_frames):
                gif.seek(frame_idx)
                frame_rgb = gif.convert("RGB")
                frame = np.array(frame_rgb)
                frames.append(frame)

            logger.info(f"Extracted {len(frames)} frames from GIF")
            return frames

        except Exception as e:
            logger.error(f"Error reading GIF: {e}")
            raise

    def extract_video_frames(
        self,
        video_path: str,
        frame_interval: Optional[int] = None,
        max_frames: int = 1000,
    ) -> Tuple[List[np.ndarray], int]:
        """
        Extract frames from video at intervals

        Args:
            video_path: Path to video file
            max_frames: Maximum frames to extract (safety limit)

        Returns:
            Tuple of (frames list, total frame count)
        """
        try:
            logger.info(f"Extracting video frames from: {video_path}")

            cap = cv2.VideoCapture(video_path)

            if not cap.isOpened():
                raise UnsupportedMediaTypeError("Cannot open video file")

            # Get video info
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 0

            logger.info(
                f"Video: {total_frames} frames, {fps} fps, {duration:.2f}s duration"
            )

            effective_interval = frame_interval or self.frame_interval

            # Check if video is too long
            if duration > 3600:  # 1 hour
                logger.warning(
                    "Video is longer than 1 hour, processing with larger interval"
                )
                effective_interval = max(10, int(effective_interval * 5))

            frames = []
            frame_idx = 0
            extracted_count = 0

            while True:
                ret, frame = cap.read()

                if not ret:
                    break

                # Extract every Nth frame
                if frame_idx % effective_interval == 0:
                    # Convert BGR to RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frames.append(frame_rgb)
                    extracted_count += 1

                    # Safety limit
                    if extracted_count >= max_frames:
                        logger.warning(
                            f"Reached max frame limit ({max_frames}), stopping extraction"
                        )
                        break

                frame_idx += 1

            cap.release()

            logger.info(f"Extracted {extracted_count} frames from {total_frames} total")
            return frames, total_frames

        except Exception as e:
            logger.error(f"Error reading video: {e}")
            raise

    def process_frames(self, frames: List[np.ndarray]) -> Dict:
        """
        Process frames through vision model

        Args:
            frames: List of frame arrays

        Returns:
            Dictionary with scores and statistics
        """
        results = {
            "frame_scores": [],
            "individual_results": [],
            "frame_count": len(frames),
        }

        logger.info(f"Processing {len(frames)} frames through model...")

        for batch_start in range(0, len(frames), self.batch_size):
            try:
                batch_frames = frames[batch_start : batch_start + self.batch_size]
                pil_images = [
                    Image.fromarray(frame.astype("uint8")) for frame in batch_frames
                ]
                predictions = self.model.predict_batch(pil_images, device=self.device)

                for idx, prediction in enumerate(predictions, start=batch_start):
                    nsfw_score = prediction["nsfw_score"]
                    results["frame_scores"].append(nsfw_score)
                    results["individual_results"].append(
                        {
                            "frame_idx": idx,
                            "class": prediction["primary_class"],
                            "confidence": prediction["confidence"],
                            "scores": prediction["classes"],
                            "recommendation": prediction["recommendation"],
                        }
                    )

                processed_count = min(batch_start + len(batch_frames), len(frames))
                if processed_count % 10 == 0 or processed_count == len(frames):
                    logger.info(f"Processed {processed_count}/{len(frames)} frames")

            except Exception as e:
                logger.error(
                    f"Error processing frames {batch_start}-{batch_start + self.batch_size - 1}: {e}"
                )
                continue

        return results

    def aggregate_scores(self, frame_scores: List[float]) -> Dict:
        """
        Aggregate frame scores to make final decision

        Args:
            frame_scores: List of NSFW scores for each frame

        Returns:
            Dictionary with aggregated metrics
        """
        if not frame_scores:
            return {
                "average_score": 0,
                "max_score": 0,
                "min_score": 0,
                "std_dev": 0,
                "flagged_frames": 0,
                "flagged_percentage": 0,
            }

        frame_scores = np.array(frame_scores)

        # Count flagged frames
        flagged = (frame_scores > 40).sum()
        very_flagged = (frame_scores > 80).sum()

        return {
            "average_score": float(np.mean(frame_scores)),
            "max_score": float(np.max(frame_scores)),
            "min_score": float(np.min(frame_scores)),
            "median_score": float(np.median(frame_scores)),
            "std_dev": float(np.std(frame_scores)),
            "flagged_frames_soft": int(flagged),
            "flagged_frames_hard": int(very_flagged),
            "flagged_percentage": float((flagged / len(frame_scores)) * 100),
            "total_frames": len(frame_scores),
        }

    def analyze_text_content(self, frames: List[np.ndarray]) -> Dict:
        """OCR disabled - returns placeholder."""
        return {
            "enabled": False,
            "available": False,
            "reason": "OCR has been removed",
            "matched": False,
            "categories": [],
            "recommendation": "allow",
        }

    def make_decision(
        self, average_score: float, max_score: float, flagged_percentage: float
    ) -> str:
        """
        Make moderation decision based on metrics

        Args:
            average_score: Average NSFW score
            max_score: Maximum NSFW score
            flagged_percentage: Percentage of flagged frames

        Returns:
            'allow', 'soft_flag', or 'hard_block'
        """
        # If even one frame is very bad, hard block
        if max_score > 85:
            return "hard_block"

        # If many frames are flagged, flag for review
        if flagged_percentage > 30 or average_score > 60:
            return "soft_flag"

        # If average is high, soft flag
        if average_score > 40:
            return "soft_flag"

        return "allow"

    def process_media(
        self,
        file_path_or_url: str,
        is_url: bool = False,
        frame_interval: Optional[int] = None,
        enable_ocr: Optional[bool] = None,
    ) -> Dict:
        """
        Main method: Process any media file

        Args:
            file_path_or_url: Path to file or URL
            is_url: Whether input is URL

        Returns:
            Complete analysis with decision
        """

        # Download if URL
        if is_url:
            try:
                actual_path = self.download_file(file_path_or_url)
            except MediaProcessingError:
                raise
            except Exception as e:
                raise DownloadFailedError(f"Download failed: {str(e)}") from e
        else:
            actual_path = file_path_or_url
            if not os.path.exists(actual_path):
                raise FileNotFoundError(f"File not found: {actual_path}")

        try:
            # Determine media type
            media_type = self.get_file_type(actual_path)
            logger.info(f"Processing {media_type}: {actual_path}")

            # Extract frames based on type
            if media_type == "image":
                frames = self.extract_image_frames(actual_path)
            elif media_type == "gif":
                frames = self.extract_gif_frames(actual_path)
            elif media_type == "video":
                frames, total_frames = self.extract_video_frames(
                    actual_path, frame_interval=frame_interval
                )
            else:
                raise UnsupportedMediaTypeError(f"Unknown media type: {media_type}")

            if not frames:
                raise UnsupportedMediaTypeError("No frames extracted")

            # Process frames through model
            frame_results = self.process_frames(frames)
            if not frame_results["frame_scores"]:
                raise FrameInferenceFailedError(
                    "Frame inference failed for all extracted frames"
                )

            # Aggregate scores
            aggregated = self.aggregate_scores(frame_results["frame_scores"])
            ocr_requested = enable_ocr if enable_ocr is not None else self.enable_ocr
            if media_type in {"gif", "video"}:
                ocr_requested = False

            ocr_analysis = (
                self.analyze_text_content(frames)
                if ocr_requested
                else {
                    "enabled": False,
                    "available": False,
                    "reason": "OCR not applied for GIF or video media",
                }
            )

            # Make decision
            recommendation = self.make_decision(
                aggregated["average_score"],
                aggregated["max_score"],
                aggregated["flagged_percentage"],
            )
            if (
                ocr_analysis.get("recommendation") == "soft_flag"
                and recommendation == "allow"
            ):
                recommendation = "soft_flag"

            # Build response
            result = {
                "model": "x02_vision_v2_efficientnet_b4",
                "media_type": media_type,
                "source": "url" if is_url else "upload",
                "recommendation": recommendation,
                "aggregated_scores": aggregated,
                "frame_results": frame_results,
                "ocr_analysis": ocr_analysis,
                "decision_reasoning": {
                    "average_nsfw_score": aggregated["average_score"],
                    "max_nsfw_score": aggregated["max_score"],
                    "flagged_percentage": aggregated["flagged_percentage"],
                    "decision_rule": self._get_decision_rule(recommendation),
                    "ocr_flagged": ocr_analysis.get("matched", False),
                },
            }

            logger.info(f"Processing complete: {recommendation}")
            return result

        except Exception as e:
            logger.error(f"Processing error: {e}")
            raise

        finally:
            # Cleanup downloaded file
            if is_url and os.path.exists(actual_path):
                try:
                    os.remove(actual_path)
                except:
                    pass

    def _get_decision_rule(self, recommendation: str) -> str:
        """Explain why this decision was made"""
        rules = {
            "allow": "All frames safe, average score < 40%",
            "soft_flag": "Some frames suspicious, 30-60% frames flagged or average 40-60%",
            "hard_block": "Very explicit content detected, max score > 85%",
        }
        return rules.get(recommendation, "Unknown rule")
