import asyncio
import logging
import os
import shutil
import tempfile
from typing import List

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("playwright not installed; screenshot capture disabled.")

try:
    from services.clip_service import rank_frames
except ImportError:
    def rank_frames(image_paths, section_title):
        return 0


def _get_candidate_times(request: dict) -> List[float]:
    """
    Return 3 candidate seek times within the section window.
    """
    preferred = float(request.get("preferred_seconds", request.get("seconds", 0)) or 0)
    window_start = float(request.get("window_start", max(0, preferred - 12)) or max(0, preferred - 12))
    window_end = float(request.get("window_end", preferred + 12) or preferred + 12)

    def clamp(value: float) -> float:
        return max(window_start, min(value, window_end))

    candidates = [
        clamp(window_start + 3),
        clamp(preferred),
        clamp((window_start + window_end) / 2),
    ]

    unique_candidates = []
    seen = set()
    for candidate in candidates:
        key = round(candidate, 1)
        if key not in seen:
            seen.add(key)
            unique_candidates.append(candidate)

    while len(unique_candidates) < 3:
        unique_candidates.append(clamp(unique_candidates[-1] + 2))

    return unique_candidates[:3]


async def _capture_frame(page, seek_time: float, output_path: str) -> bool:
    """Seek the embedded player and capture the current video frame."""
    try:
        await page.evaluate(
            "(seekTime) => { const video = document.querySelector('video'); if (video) video.currentTime = seekTime; }",
            seek_time,
        )
        await asyncio.sleep(0.6)
        video = page.locator("video")
        await video.screenshot(path=output_path, type="jpeg")
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1000
    except Exception as exc:
        logger.warning(f"Frame capture failed at {seek_time:.1f}s: {exc}")
        return False


async def extract_screenshots_playwright(
    video_id: str,
    screenshot_requests: List[dict],
    static_dir: str,
) -> List[dict]:
    """
    Capture screenshots by seeking within the YouTube embed player and choosing
    the strongest candidate frame for each request with CLIP.
    """
    if not PLAYWRIGHT_AVAILABLE:
        logger.warning("Playwright not available. Returning empty screenshot list.")
        return []

    os.makedirs(static_dir, exist_ok=True)
    candidate_root = os.path.join(static_dir, ".pw_candidates")
    os.makedirs(candidate_root, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix="pw_", dir=candidate_root)
    results = []

    embed_url = (
        f"https://www.youtube-nocookie.com/embed/{video_id}"
        f"?autoplay=1&mute=1&controls=0&rel=0&modestbranding=1"
    )

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            await page.goto(embed_url, wait_until="domcontentloaded", timeout=20000)

            try:
                await page.wait_for_selector("video", timeout=15000)
            except Exception:
                logger.error("Playwright: video element never appeared.")
                await browser.close()
                return []

            await page.evaluate(
                "() => { const video = document.querySelector('video'); if (video) video.pause(); }"
            )
            await asyncio.sleep(1.0)

            for request in screenshot_requests:
                section_title = request.get("section_title", "")
                caption = request.get("caption", "")
                candidate_times = _get_candidate_times(request)
                candidate_paths = []

                for index, seek_time in enumerate(candidate_times):
                    safe_title = "".join(char for char in section_title[:20] if char.isalnum() or char in ("_", "-")).strip()
                    title_part = safe_title or "section"
                    candidate_path = os.path.join(tmp_dir, f"{video_id}_{title_part}_{index}.jpg")
                    if await _capture_frame(page, seek_time, candidate_path):
                        candidate_paths.append((seek_time, candidate_path))

                if not candidate_paths:
                    logger.warning(f"No valid candidates for section '{section_title}'")
                    continue

                path_only = [path for _, path in candidate_paths]
                best_index = rank_frames(path_only, section_title=section_title or caption)
                best_time, best_path = candidate_paths[best_index]

                try:
                    actual_time = await page.evaluate(
                        "() => { const video = document.querySelector('video'); return video ? video.currentTime : null; }"
                    )
                except Exception:
                    actual_time = best_time

                actual_seconds = int(round(actual_time or best_time))
                final_name = f"{video_id}_{actual_seconds}.jpg"
                final_path = os.path.join(static_dir, final_name)
                shutil.copy2(best_path, final_path)

                results.append(
                    {
                        **request,
                        "actual_seconds": actual_seconds,
                        "filename": final_name,
                    }
                )

            await browser.close()
    except Exception as exc:
        logger.error(f"Playwright screenshot extraction failed: {exc}")
        return []
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        shutil.rmtree(candidate_root, ignore_errors=True)

    return results
