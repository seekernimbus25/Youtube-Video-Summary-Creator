import asyncio
import logging
import os
import shutil
import tempfile
import uuid
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
        clamp(preferred),
        clamp(preferred + 2.0),
        clamp(preferred + 5.0),
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
            """(seekTime) => {
                const video = document.querySelector('video');
                if (video) {
                    video.pause();
                    video.currentTime = seekTime;
                }
            }""",
            seek_time,
        )
        await page.wait_for_function(
            """() => {
                const video = document.querySelector('video');
                return !!video && video.readyState >= 2 && !video.seeking;
            }""",
            timeout=3000,
        )
        await asyncio.sleep(0.18)
        video = page.locator("video")
        await video.screenshot(path=output_path, type="jpeg")
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1000
    except Exception as exc:
        logger.warning(f"Frame capture failed at {seek_time:.1f}s: {exc}")
        return False


async def _log_page_diagnostics(page, prefix: str) -> None:
    """Log a compact snapshot of the current page state for debugging."""
    try:
        title = await page.title()
    except Exception:
        title = "<unavailable>"

    try:
        url = page.url
    except Exception:
        url = "<unavailable>"

    try:
        text_sample = await page.evaluate(
            """() => (document.body?.innerText || '')
                .replace(/\\s+/g, ' ')
                .trim()
                .slice(0, 400)"""
        )
    except Exception:
        text_sample = "<unavailable>"

    logger.error(
        "%s | url=%s | title=%s | body_sample=%s",
        prefix,
        url,
        title,
        text_sample,
    )


async def _accept_youtube_consent(page) -> None:
    """Best-effort click through consent prompts that block the video element."""
    selectors = [
        "button:has-text('I agree')",
        "button:has-text('Accept all')",
        "button:has-text('Accept the use of cookies and other data for the purposes described')",
        "button[aria-label*='Accept']",
        "form button + button",
    ]

    for selector in selectors:
        try:
            button = page.locator(selector).first
            if await button.count():
                await button.click(timeout=2000)
                await asyncio.sleep(1.0)
                logger.info(f"Playwright: clicked consent selector {selector}")
                return
        except Exception:
            continue


async def _wait_for_video_player(page, source_url: str) -> bool:
    """Load the player page and wait until a usable video element is present."""
    try:
        await page.goto(source_url, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        await _accept_youtube_consent(page)

        try:
            await page.wait_for_function(
                """() => {
                    const video = document.querySelector('video');
                    return !!video && (!!video.src || video.readyState >= 1);
                }""",
                timeout=20000,
            )
            return True
        except Exception:
            await _log_page_diagnostics(page, "Playwright: video element never appeared")
            return False
    except Exception as exc:
        logger.error(f"Playwright: failed loading player URL {source_url}: {exc}")
        await _log_page_diagnostics(page, "Playwright: load failure diagnostics")
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

    embed_urls = [
        f"https://www.youtube.com/watch?v={video_id}",
    ]

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    "--autoplay-policy=no-user-gesture-required",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            player_ready = False
            for embed_url in embed_urls:
                logger.info(f"Playwright: loading player URL {embed_url}")
                if await _wait_for_video_player(page, embed_url):
                    player_ready = True
                    break

            if not player_ready:
                await context.close()
                await browser.close()
                return []

            await page.evaluate(
                "() => { const video = document.querySelector('video'); if (video) video.pause(); }"
            )
            await asyncio.sleep(1.0)

            for req_index, request in enumerate(screenshot_requests):
                section_title = request.get("section_title", "")
                caption = request.get("caption", "")
                candidate_times = _get_candidate_times(request)
                candidate_paths = []
                request_id = request.get("request_id", f"req-{req_index}")

                for index, seek_time in enumerate(candidate_times):
                    safe_title = "".join(char for char in section_title[:20] if char.isalnum() or char in ("_", "-")).strip()
                    title_part = safe_title or "section"
                    unique_suffix = uuid.uuid4().hex[:8]
                    candidate_path = os.path.join(
                        tmp_dir,
                        f"{video_id}_{request_id}_{title_part}_{index}_{unique_suffix}.jpg"
                    )
                    if await _capture_frame(page, seek_time, candidate_path):
                        candidate_paths.append((seek_time, candidate_path))

                if not candidate_paths:
                    logger.warning(f"No valid candidates for section '{section_title}'")
                    continue

                path_only = [path for _, path in candidate_paths]
                best_index = rank_frames(path_only, section_title=section_title or caption)
                best_time, best_path = candidate_paths[best_index]
                actual_seconds = int(round(best_time))
                window_start = int(float(request.get("window_start", 0) or 0))
                window_end = int(float(request.get("window_end", actual_seconds) or actual_seconds))
                if actual_seconds < window_start or actual_seconds > window_end:
                    logger.warning(
                        "Chosen Playwright frame outside window for request_id=%s (selected=%s, window=%s-%s).",
                        request_id,
                        actual_seconds,
                        window_start,
                        window_end,
                    )
                    actual_seconds = max(window_start, min(actual_seconds, window_end))
                final_name = f"{video_id}_{actual_seconds}.jpg"
                final_path = os.path.join(static_dir, final_name)
                shutil.copy2(best_path, final_path)

                results.append(
                    {
                        **request,
                        "request_id": request_id,
                        "target_seconds": int(request.get("target_seconds", request.get("seconds", actual_seconds)) or actual_seconds),
                        "selected_seconds": actual_seconds,
                        "actual_seconds": actual_seconds,
                        "quality_score": 0.0,
                        "selection_reason": "playwright_clip_ranked",
                        "filename": final_name,
                    }
                )

            await context.close()
            await browser.close()
    except Exception as exc:
        logger.error(f"Playwright screenshot extraction failed: {exc}")
        return []
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        shutil.rmtree(candidate_root, ignore_errors=True)

    return results
