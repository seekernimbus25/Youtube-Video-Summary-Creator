import os
from copy import deepcopy


AUTH_ERROR_MARKERS = (
    "sign in to confirm you're not a bot",
    "sign in to confirm you\u2019re not a bot",
    "use --cookies-from-browser or --cookies for the authentication",
    "requested format is not available",
    "video unavailable. this content isn't available",
    "the following content is not available on this app",
)

COOKIE_DB_ERROR_MARKERS = (
    "could not copy chrome cookie database",
    "could not copy edge cookie database",
    "could not copy brave cookie database",
    "could not copy firefox cookie database",
    "failed to decrypt",
    "unable to open database file",
    "database is locked",
    "permission denied",
)

DEFAULT_BROWSER_CANDIDATES = ("chrome", "edge", "brave", "firefox")


def is_youtube_auth_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in AUTH_ERROR_MARKERS)


def is_browser_cookie_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in COOKIE_DB_ERROR_MARKERS)


def _parse_browser_tuple(raw_value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw_value.split(",") if part.strip())


def _auto_browser_cookies_enabled() -> bool:
    raw_value = os.environ.get("YTDLP_AUTO_BROWSER_COOKIES", "false").strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


def _browser_candidates() -> tuple[str, ...]:
    raw_value = os.environ.get("YTDLP_BROWSER_CANDIDATES", "").strip()
    if not raw_value:
        return DEFAULT_BROWSER_CANDIDATES
    parts = tuple(part.strip() for part in raw_value.split(",") if part.strip())
    return parts or DEFAULT_BROWSER_CANDIDATES


def build_ytdlp_auth_variants(base_opts: dict) -> list[tuple[str, dict]]:
    variants: list[tuple[str, dict]] = []

    cookie_file = os.environ.get("YTDLP_COOKIES_FILE", "").strip()
    if cookie_file:
        opts = deepcopy(base_opts)
        opts["cookiefile"] = cookie_file
        return [("cookie-file", opts)]

    from_browser_raw = os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "").strip()
    seen_browser_names: set[str] = set()
    if from_browser_raw:
        opts = deepcopy(base_opts)
        browser_parts = _parse_browser_tuple(from_browser_raw)
        opts["cookiesfrombrowser"] = browser_parts
        variants.append(("browser-env", opts))
        if browser_parts:
            seen_browser_names.add(browser_parts[0].lower())

    variants.append(("anonymous", deepcopy(base_opts)))
    if not _auto_browser_cookies_enabled():
        return variants

    for browser_name in _browser_candidates():
        if browser_name.lower() in seen_browser_names:
            continue
        opts = deepcopy(base_opts)
        opts["cookiesfrombrowser"] = (browser_name,)
        variants.append((f"browser:{browser_name}", opts))

    return variants


def youtube_auth_help_message() -> str:
    return (
        "YOUTUBE_AUTH_REQUIRED: YouTube blocked anonymous access for this video. "
        "Add `YTDLP_COOKIES_FROM_BROWSER=chrome` (or `edge`, `brave`, `firefox`) "
        "or set `YTDLP_COOKIES_FILE=/absolute/path/to/cookies.txt` in `backend/.env`, "
        "then restart the server."
    )


def browser_cookie_help_message() -> str:
    return (
        "YTDLP_BROWSER_COOKIES_UNAVAILABLE: yt-dlp could not read the browser cookie database. "
        "Close the target browser completely, or switch to another browser in `YTDLP_COOKIES_FROM_BROWSER` "
        "(for example `edge`), or export cookies to a Netscape cookies.txt file and set "
        "`YTDLP_COOKIES_FILE=/absolute/path/to/cookies.txt`, then restart the server."
    )


def run_ytdlp_with_auth(base_opts: dict, operation, logger):
    auth_error_seen = False
    cookie_error_seen = False
    last_error = None

    for variant_name, variant_opts in build_ytdlp_auth_variants(base_opts):
        try:
            return operation(variant_opts)
        except Exception as exc:
            last_error = exc
            if is_youtube_auth_error(exc):
                auth_error_seen = True
                logger.warning("yt-dlp auth gate hit using %s: %s", variant_name, exc)
                continue
            if is_browser_cookie_error(exc):
                cookie_error_seen = True
                logger.warning("yt-dlp browser cookie access failed using %s: %s", variant_name, exc)
                continue
            raise

    if cookie_error_seen and not auth_error_seen:
        raise RuntimeError(browser_cookie_help_message())
    if auth_error_seen:
        raise RuntimeError(youtube_auth_help_message())
    if cookie_error_seen:
        raise RuntimeError(
            f"{youtube_auth_help_message()} Also, browser cookie access failed for at least one configured browser."
        )
    if last_error:
        raise last_error
    raise RuntimeError("yt-dlp failed before executing any auth strategy.")
