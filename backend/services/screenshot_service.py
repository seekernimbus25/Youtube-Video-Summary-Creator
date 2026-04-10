import os
import shutil
import subprocess
import tempfile
import asyncio
import logging
import time
import re
from difflib import SequenceMatcher
from typing import List, Optional
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from utils.network import without_proxy_env

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    cv2 = None

try:
    from rapidfuzz import fuzz  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    fuzz = None

try:
    from paddleocr import PaddleOCR  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    PaddleOCR = None

try:
    from scenedetect import open_video, SceneManager  # type: ignore
    from scenedetect.detectors import ContentDetector  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    open_video = None
    SceneManager = None
    ContentDetector = None

logger = logging.getLogger(__name__)

FRAME_OFFSET_AFTER_SCENE = 0.35
MIN_SCENE_GAP_SECONDS = 2
FINGERPRINT_DUPLICATE_DISTANCE = 6
MAX_CANDIDATES_PER_REQUEST = 12
SCENE_OFFSETS = [0.35, 0.9, 1.6]
BLUR_THRESHOLD = 45.0
EDGE_DENSITY_THRESHOLD = 0.015
TEXT_MATCH_ACCEPT_THRESHOLD = 35
_ocr_engine = None

# Thread pool for synchronous blocking tasks like yt-dlp and ffmpeg
executor = ThreadPoolExecutor(max_workers=4)


def _find_ffmpeg() -> Optional[str]:
    """Find the ffmpeg executable, checking PATH and common Windows install locations."""
    path = shutil.which("ffmpeg")
    if path:
        return path
    # Fallback: check common Windows paths (e.g. WinGet, manual installs)
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
    ]
    for p in candidates:
        if os.path.isfile(p):
            logger.info(f"Found ffmpeg at fallback path: {p}")
            return p
    return None


FFMPEG_PATH: Optional[str] = _find_ffmpeg()
FFMPEG_AVAILABLE: bool = FFMPEG_PATH is not None

if FFMPEG_AVAILABLE:
    logger.info(f"ffmpeg detected at: {FFMPEG_PATH}")
else:
    logger.warning("ffmpeg not found — screenshot extraction will be disabled.")

def cleanup_old_screenshots(static_dir: str):
    """Cleanup files > 24h old at request start"""
    now = time.time()
    try:
        os.makedirs(static_dir, exist_ok=True)
        for filename in os.listdir(static_dir):
            if filename.endswith(".jpg"):
                filepath = os.path.join(static_dir, filename)
                if os.stat(filepath).st_mtime < now - 86400:
                    try:
                        os.unlink(filepath)
                    except Exception:
                        pass
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is False:
        return None
    if _ocr_engine is None:
        try:
            _ocr_engine = PaddleOCR(use_textline_orientation=False, lang="en")
        except Exception as e:
            logger.warning(f"PaddleOCR failed to initialize: {e}. OCR features will be disabled.")
            _ocr_engine = False
            return None
    return _ocr_engine


def _fuzzy_match_score(left: str, right: str) -> float:
    left_norm = _normalize_text(left)
    right_norm = _normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    if fuzz is not None:
        return float(fuzz.token_set_ratio(left_norm, right_norm))
    return SequenceMatcher(None, left_norm, right_norm).ratio() * 100.0


def _extract_text_from_image(image_path: str) -> str:
    ocr_engine = _get_ocr_engine()
    if ocr_engine is None:
        return ""

    try:
        results = ocr_engine.ocr(image_path, cls=False)
    except Exception as e:
        logger.warning(f"OCR failed for {image_path}: {e}")
        return ""

    lines = []
    for group in results or []:
        for item in group or []:
            try:
                lines.append(item[1][0])
            except Exception:
                continue
    return " ".join(lines).strip()


def _detect_scene_timestamps(temp_video_path: str, duration_seconds: int) -> List[int]:
    """Detect likely scene-change timestamps from the video using ffmpeg."""
    if open_video and SceneManager and ContentDetector:
        try:
            video = open_video(temp_video_path)
            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector(threshold=27.0))
            scene_manager.detect_scenes(video=video)
            detected = []
            max_second = max(0, duration_seconds - 2)
            seen = set()
            for start_time, _ in scene_manager.get_scene_list():
                sec = max(0, min(int(round(start_time.get_seconds())), max_second))
                if sec not in seen:
                    seen.add(sec)
                    detected.append(sec)
            if detected:
                logger.info(f"Detected {len(detected)} scene candidates with PySceneDetect.")
                return detected
        except Exception as e:
            logger.warning(f"PySceneDetect failed, falling back to ffmpeg scene detection: {e}")

    if not FFMPEG_PATH:
        return []

    cmd = [
        FFMPEG_PATH,
        "-hide_banner",
        "-i", temp_video_path,
        "-vf", "select='gt(scene,0.22)',showinfo",
        "-an",
        "-f", "null",
        "-"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
    except Exception as e:
        logger.warning(f"Scene detection failed to run: {e}")
        return []

    if result.returncode not in (0, 255):
        logger.warning(f"Scene detection ffmpeg exited with {result.returncode}: {result.stderr.decode(errors='replace')[:300]}")
        return []

    stderr = result.stderr.decode(errors='replace')
    matches = re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", stderr)

    max_second = max(0, duration_seconds - 2)
    seen = set()
    scene_seconds = []
    for match in matches:
        sec = max(0, min(int(round(float(match))), max_second))
        if sec in seen:
            continue
        seen.add(sec)
        scene_seconds.append(sec)

    logger.info(f"Detected {len(scene_seconds)} scene candidates for screenshot selection.")
    return scene_seconds


def _extract_signalstat_value(stats_text: str, key: str) -> Optional[float]:
    match = re.search(rf"{re.escape(key)}=([0-9]+(?:\.[0-9]+)?)", stats_text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _score_frame_quality(temp_video_path: str, seek_time: float) -> dict:
    if not FFMPEG_PATH:
        return {"rejected": False, "score": 0.0}

    cmd = [
        FFMPEG_PATH,
        "-hide_banner",
        "-ss", f"{seek_time:.3f}",
        "-i", temp_video_path,
        "-frames:v", "1",
        "-vf", "signalstats,metadata=print",
        "-f", "null",
        "-"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
    except Exception as e:
        logger.warning(f"Frame quality analysis failed at {seek_time:.2f}s: {e}")
        return {"rejected": False, "score": 0.0}

    stats_text = (result.stdout + result.stderr).decode(errors='replace')
    yavg = _extract_signalstat_value(stats_text, "lavfi.signalstats.YAVG")
    satavg = _extract_signalstat_value(stats_text, "lavfi.signalstats.SATAVG")
    ylow = _extract_signalstat_value(stats_text, "lavfi.signalstats.YLOW")
    yhigh = _extract_signalstat_value(stats_text, "lavfi.signalstats.YHIGH")

    if yavg is None or satavg is None:
        return {"rejected": False, "score": 0.0}

    dynamic_range = (yhigh - ylow) if yhigh is not None and ylow is not None else 0.0
    is_too_dark = yavg < 18
    is_blank_white = yavg > 245 and satavg < 10
    is_flat_slate = dynamic_range < 10 and satavg < 12
    rejected = is_too_dark or is_blank_white or is_flat_slate

    # Prefer colorful, readable, non-flat frames near normal brightness.
    brightness_penalty = abs(yavg - 128) / 16
    score = satavg + (dynamic_range / 6) - brightness_penalty

    return {
        "rejected": rejected,
        "score": score,
    }


def _compute_frame_fingerprint(temp_video_path: str, seek_time: float) -> Optional[int]:
    if not FFMPEG_PATH:
        return None

    cmd = [
        FFMPEG_PATH,
        "-hide_banner",
        "-ss", f"{seek_time:.3f}",
        "-i", temp_video_path,
        "-frames:v", "1",
        "-vf", "scale=8:8,format=gray",
        "-f", "rawvideo",
        "-"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
    except Exception as e:
        logger.warning(f"Frame fingerprinting failed at {seek_time:.2f}s: {e}")
        return None

    if result.returncode != 0 or len(result.stdout) < 64:
        return None

    pixels = list(result.stdout[:64])
    avg = sum(pixels) / len(pixels)
    bits = 0
    for idx, pixel in enumerate(pixels):
        if pixel >= avg:
            bits |= 1 << idx
    return bits


def _fingerprint_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def _is_duplicate_fingerprint(fingerprint: Optional[int], used_fingerprints: List[int]) -> bool:
    if fingerprint is None:
        return False
    return any(_fingerprint_distance(fingerprint, used) <= FINGERPRINT_DUPLICATE_DISTANCE for used in used_fingerprints)


def _build_candidate_seek_times(request: dict, duration_seconds: int, scene_seconds: List[int], used_seconds: set[int]) -> List[float]:
    max_second = max(0, duration_seconds - 2)
    preferred = max(0, min(int(request.get("preferred_seconds", request.get("seconds", 0)) or 0), max_second))
    fallback = max(0, min(int(request.get("seconds", preferred) or preferred), max_second))
    window_start = max(0, min(int(request.get("window_start", fallback - 12) or (fallback - 12)), max_second))
    window_end = max(window_start, min(int(request.get("window_end", fallback + 12) or (fallback + 12)), max_second))

    candidates = []
    for sec in scene_seconds:
        if sec < window_start or sec > window_end or sec in used_seconds:
            continue
        if candidates and abs(sec - candidates[-1]) < MIN_SCENE_GAP_SECONDS:
            continue
        candidates.append(sec)

    candidates.sort(key=lambda sec: (abs(sec - preferred), abs(sec - fallback), sec))

    seek_times: list[float] = []
    seen_seek_keys = set()

    for candidate in candidates:
        for offset in SCENE_OFFSETS:
            seek_time = max(float(window_start), min(float(candidate) + offset, float(window_end), float(max_second)))
            seek_key = round(seek_time, 2)
            if seek_key not in seen_seek_keys:
                seen_seek_keys.add(seek_key)
                seek_times.append(seek_time)

    fallback_candidates = [
        fallback,
        preferred,
        min(window_start + 2, window_end),
        min(window_start + 5, window_end),
        window_start,
    ]
    for candidate in fallback_candidates:
        seek_time = max(float(window_start), min(float(candidate) + FRAME_OFFSET_AFTER_SCENE, float(window_end), float(max_second)))
        seek_key = round(seek_time, 2)
        if candidate not in used_seconds and seek_key not in seen_seek_keys:
            seen_seek_keys.add(seek_key)
            seek_times.append(seek_time)

    return seek_times[:MAX_CANDIDATES_PER_REQUEST]


def _extract_frame_to_path(video_path: str, seek_time: float, output_path: str) -> bool:
    if not FFMPEG_PATH:
        return False

    cmd = [
        FFMPEG_PATH, "-y",
        "-ss", f"{seek_time:.3f}",
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        output_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            logger.warning(f"ffmpeg candidate extraction failed at {seek_time:.2f}s: {result.stderr.decode(errors='replace')[:250]}")
            return False
    except Exception as e:
        logger.warning(f"ffmpeg candidate extraction errored at {seek_time:.2f}s: {e}")
        return False
    return os.path.exists(output_path)


def _compute_image_fingerprint(image_path: str) -> Optional[int]:
    if cv2 is None:
        return None
    image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None
    resized = cv2.resize(image, (8, 8), interpolation=cv2.INTER_AREA)
    avg = float(resized.mean())
    bits = 0
    for idx, pixel in enumerate(resized.flatten()):
        if float(pixel) >= avg:
            bits |= 1 << idx
    return bits


def _score_frame_file(image_path: str, request: dict, used_fingerprints: List[int], seek_time: float) -> dict:
    section_title = request.get("section_title", "")
    section_context = request.get("section_context", "")

    if cv2 is None:
        return {
            "rejected": False,
            "score": max(0.0, 10.0 - abs(seek_time - float(request.get("preferred_seconds", request.get("seconds", 0)) or 0))),
            "fingerprint": None,
            "ocr_text": "",
        }

    image = cv2.imread(image_path)
    if image is None:
        return {"rejected": True, "score": -1.0, "fingerprint": None, "ocr_text": ""}

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    contrast = float(gray.std())
    edges = cv2.Canny(gray, 80, 160)
    edge_density = float(edges.mean() / 255.0)

    fingerprint = _compute_image_fingerprint(image_path)
    is_duplicate = _is_duplicate_fingerprint(fingerprint, used_fingerprints)

    ocr_text = _extract_text_from_image(image_path)
    title_match = _fuzzy_match_score(ocr_text, section_title)
    context_match = _fuzzy_match_score(ocr_text, section_context)
    text_score = max(title_match, context_match)

    quality_score = min(blur / 20.0, 15.0) + min(edge_density * 100.0, 12.0) + min(contrast / 8.0, 8.0)
    brightness_score = max(0.0, 15.0 - abs(brightness - 128.0) / 8.0)
    proximity_score = max(0.0, 10.0 - abs(seek_time - float(request.get("preferred_seconds", request.get("seconds", 0)) or 0)))
    duplicate_penalty = 30.0 if is_duplicate else 0.0

    rejected = (
        blur < BLUR_THRESHOLD or
        brightness < 20.0 or
        (brightness > 245.0 and contrast < 12.0) or
        (contrast < 10.0 and edge_density < EDGE_DENSITY_THRESHOLD)
    )

    if not ocr_text and section_context:
        text_score *= 0.4

    total_score = (text_score * 0.45) + (quality_score * 0.20) + (brightness_score * 0.10) + (proximity_score * 0.10) - duplicate_penalty

    return {
        "rejected": rejected and text_score < TEXT_MATCH_ACCEPT_THRESHOLD,
        "score": total_score,
        "fingerprint": fingerprint,
        "ocr_text": ocr_text,
    }


def _choose_best_timestamp(request: dict, temp_video_path: str, duration_seconds: int, scene_seconds: List[int], used_seconds: set[int], used_fingerprints: List[int]) -> dict:
    max_second = max(0, duration_seconds - 2)
    window_end = max(0, min(int(request.get("window_end", max_second) or max_second), max_second))
    candidate_seek_times = _build_candidate_seek_times(request, duration_seconds, scene_seconds, used_seconds)

    best_non_rejected = None
    best_any = None

    candidate_dir = tempfile.mkdtemp(prefix="shot_candidates_")
    try:
        for idx, seek_time in enumerate(candidate_seek_times):
            bounded_seek_time = max(0.0, min(float(seek_time), float(window_end), float(max_second)))
            candidate_second = int(round(bounded_seek_time))
            candidate_path = os.path.join(candidate_dir, f"candidate_{idx}_{candidate_second}.jpg")
            if not _extract_frame_to_path(temp_video_path, bounded_seek_time, candidate_path):
                continue

            ranking = _score_frame_file(candidate_path, request, used_fingerprints, bounded_seek_time)
            ranked = (
                0 if _is_duplicate_fingerprint(ranking["fingerprint"], used_fingerprints) else 1,
                ranking["score"],
                -abs(candidate_second - int(request.get("preferred_seconds", candidate_second) or candidate_second)),
                -candidate_second
            )

            if best_any is None or ranked > best_any[0]:
                best_any = (ranked, candidate_second, ranking["fingerprint"], bounded_seek_time, ranking.get("ocr_text", ""))

            if not ranking["rejected"]:
                if best_non_rejected is None or ranked > best_non_rejected[0]:
                    best_non_rejected = (ranked, candidate_second, ranking["fingerprint"], bounded_seek_time, ranking.get("ocr_text", ""))
    finally:
        shutil.rmtree(candidate_dir, ignore_errors=True)

    if best_non_rejected is not None:
        return {
            "actual_seconds": best_non_rejected[1],
            "seek_time": best_non_rejected[3],
            "fingerprint": best_non_rejected[2],
            "ocr_text": best_non_rejected[4],
        }
    if best_any is not None:
        return {
            "actual_seconds": best_any[1],
            "seek_time": best_any[3],
            "fingerprint": best_any[2],
            "ocr_text": best_any[4],
        }

    fallback = max(0, min(int(request.get("seconds", 0) or 0), max_second))
    fallback_seek = min(fallback + FRAME_OFFSET_AFTER_SCENE, window_end, float(max_second))
    return {
        "actual_seconds": fallback,
        "seek_time": fallback_seek,
        "fingerprint": None,
        "ocr_text": "",
    }


async def extract_screenshots_for_video(video_url: str, video_id: str, duration_seconds: int, screenshot_requests: List[dict], static_dir: str) -> List[dict]:
    """
    Downloads minimum video quality, detects scene changes, extracts frames using ffmpeg,
    cleans up temp files gracefully, and returns metadata for generated screenshots.
    """
    if not FFMPEG_AVAILABLE or not FFMPEG_PATH:
        logger.warning("ffmpeg is not available. Skipping screenshot extraction.")
        return []
        
    cleanup_old_screenshots(static_dir)

    loop = asyncio.get_running_loop()
    temp_dir = tempfile.mkdtemp()
    temp_video_path = os.path.join(temp_dir, f"{video_id}.mp4")
    
    generated_files = []

    try:
        # Video download using yt-dlp via ThreadPoolExecutor
        def download_video():
            ydl_opts = {
                'format': 'bestvideo[height<=360][ext=mp4]/bestvideo[height<=360]/best[height<=360]/best',
                'outtmpl': temp_video_path,
                'quiet': True,
                'no_warnings': True,
                'merge_output_format': 'mp4',
                'proxy': '',
            }
            with without_proxy_env():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([video_url])
        
        logger.info(f"Downloading short video segment to {temp_video_path}...")
        await loop.run_in_executor(executor, download_video)

        # yt-dlp may write the file with a different extension — find it
        if not os.path.exists(temp_video_path):
            candidates = [f for f in os.listdir(temp_dir) if f.startswith(video_id)]
            if candidates:
                temp_video_path = os.path.join(temp_dir, candidates[0])
                logger.info(f"Using downloaded file: {temp_video_path}")
            else:
                raise RuntimeError("Video download failed.")

        scene_seconds = await loop.run_in_executor(executor, _detect_scene_timestamps, temp_video_path, duration_seconds)

        used_seconds = set()
        used_fingerprints = []
        resolved_requests = []
        for request in screenshot_requests:
            selection = _choose_best_timestamp(
                request,
                temp_video_path,
                duration_seconds,
                scene_seconds,
                used_seconds,
                used_fingerprints
            )
            actual_sec = int(selection.get("actual_seconds", request.get("seconds", 0)) or 0)
            fingerprint = selection.get("fingerprint")
            used_seconds.add(actual_sec)
            if fingerprint is not None:
                used_fingerprints.append(fingerprint)
            resolved_requests.append({
                **request,
                "actual_seconds": actual_sec,
                "seek_time": float(selection.get("seek_time", actual_sec + FRAME_OFFSET_AFTER_SCENE) or (actual_sec + FRAME_OFFSET_AFTER_SCENE))
            })

        # Extract frames concurrently using ffmpeg (run in thread pool to avoid Windows asyncio subprocess issues)
        def extract_frame_sync(request: dict) -> Optional[dict]:
            # Clamp timestamp: max(0, min(seconds, duration_seconds - 2))
            clamped_sec = max(0, min(int(request.get("actual_seconds", request.get("seconds", 0)) or 0), duration_seconds - 2))
            seek_time = max(0.0, min(float(request.get("seek_time", clamped_sec) or clamped_sec), float(max(0, duration_seconds - 2))))

            output_filename = f"{video_id}_{clamped_sec}.jpg"
            output_filepath = os.path.join(static_dir, output_filename)

            if os.path.exists(output_filepath):
                return {
                    **request,
                    "actual_seconds": clamped_sec,
                    "filename": output_filename
                }

            # Accurate seek: -ss after -i ensures frame-exact extraction
            cmd = [FFMPEG_PATH, "-y", "-ss", f"{seek_time:.3f}", "-i", temp_video_path, "-vframes", "1", "-q:v", "2", output_filepath]

            try:
                result = subprocess.run(cmd, capture_output=True, timeout=30)
                if result.returncode != 0:
                    logger.warning(f"ffmpeg failed for sec={clamped_sec}: {result.stderr.decode(errors='replace')[:300]}")
            except Exception as e:
                logger.error(f"ffmpeg subprocess error for sec={clamped_sec}: {e}")

            if os.path.exists(output_filepath):
                return {
                    **request,
                    "actual_seconds": clamped_sec,
                    "filename": output_filename
                }
            return None

        # Run extraction concurrently in thread pool
        frame_futures = [loop.run_in_executor(executor, extract_frame_sync, request) for request in resolved_requests]
        results = await asyncio.gather(*frame_futures)
        generated_files = [res for res in results if res is not None]

    except Exception as e:
        logger.error(f"Screenshot extraction failed: {e}")
        # Explicit error but non-fatal for whole request
        return []
    finally:
        # Wrap os.unlink in try/except for Windows locks
        try:
            if os.path.exists(temp_video_path):
                os.unlink(temp_video_path)
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            logger.error(f"Failed to clean up temp files: {e}")

    return generated_files
