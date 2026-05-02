from utils.ytdlp_auth import (
    build_ytdlp_auth_variants,
    is_browser_cookie_error,
    is_youtube_auth_error,
    run_ytdlp_with_auth,
)


class StubLogger:
    def __init__(self):
        self.messages = []

    def warning(self, message, *args):
        self.messages.append(message % args if args else message)


def test_build_variants_prefers_cookie_file(monkeypatch):
    monkeypatch.setenv("YTDLP_COOKIES_FILE", "C:\\cookies.txt")
    monkeypatch.delenv("YTDLP_COOKIES_FROM_BROWSER", raising=False)
    variants = build_ytdlp_auth_variants({"quiet": True})

    assert len(variants) == 1
    assert variants[0][0] == "cookie-file"
    assert variants[0][1]["cookiefile"] == "C:\\cookies.txt"


def test_build_variants_uses_explicit_browser_env(monkeypatch):
    monkeypatch.delenv("YTDLP_COOKIES_FILE", raising=False)
    monkeypatch.setenv("YTDLP_COOKIES_FROM_BROWSER", "chrome,Default")
    variants = build_ytdlp_auth_variants({"quiet": True})

    assert len(variants) >= 2
    assert variants[0][0] == "browser-env"
    assert variants[0][1]["cookiesfrombrowser"] == ("chrome", "Default")
    assert variants[1][0] == "anonymous"


def test_build_variants_skips_duplicate_browser_after_explicit_env(monkeypatch):
    monkeypatch.delenv("YTDLP_COOKIES_FILE", raising=False)
    monkeypatch.setenv("YTDLP_COOKIES_FROM_BROWSER", "edge")
    monkeypatch.setenv("YTDLP_BROWSER_CANDIDATES", "edge,firefox")
    monkeypatch.setenv("YTDLP_AUTO_BROWSER_COOKIES", "true")
    variants = build_ytdlp_auth_variants({"quiet": True})

    assert [name for name, _ in variants] == ["browser-env", "anonymous", "browser:firefox"]


def test_build_variants_adds_anonymous_and_browser_retries(monkeypatch):
    monkeypatch.delenv("YTDLP_COOKIES_FILE", raising=False)
    monkeypatch.delenv("YTDLP_COOKIES_FROM_BROWSER", raising=False)
    monkeypatch.setenv("YTDLP_BROWSER_CANDIDATES", "edge,firefox")
    monkeypatch.setenv("YTDLP_AUTO_BROWSER_COOKIES", "true")
    variants = build_ytdlp_auth_variants({"quiet": True})

    assert [name for name, _ in variants] == ["anonymous", "browser:edge", "browser:firefox"]


def test_build_variants_stays_anonymous_by_default(monkeypatch):
    monkeypatch.delenv("YTDLP_COOKIES_FILE", raising=False)
    monkeypatch.delenv("YTDLP_COOKIES_FROM_BROWSER", raising=False)
    monkeypatch.delenv("YTDLP_AUTO_BROWSER_COOKIES", raising=False)
    variants = build_ytdlp_auth_variants({"quiet": True})

    assert [name for name, _ in variants] == ["anonymous"]


def test_run_ytdlp_retries_after_auth_error(monkeypatch):
    monkeypatch.delenv("YTDLP_COOKIES_FILE", raising=False)
    monkeypatch.delenv("YTDLP_COOKIES_FROM_BROWSER", raising=False)
    monkeypatch.setenv("YTDLP_BROWSER_CANDIDATES", "edge")
    monkeypatch.setenv("YTDLP_AUTO_BROWSER_COOKIES", "true")
    logger = StubLogger()

    def operation(opts):
        if "cookiesfrombrowser" not in opts:
            raise Exception(
                "Sign in to confirm you're not a bot. Use --cookies-from-browser or --cookies for the authentication."
            )
        return opts["cookiesfrombrowser"]

    assert run_ytdlp_with_auth({"quiet": True}, operation, logger) == ("edge",)
    assert logger.messages


def test_run_ytdlp_raises_helpful_error_after_all_auth_attempts_fail(monkeypatch):
    monkeypatch.delenv("YTDLP_COOKIES_FILE", raising=False)
    monkeypatch.delenv("YTDLP_COOKIES_FROM_BROWSER", raising=False)
    monkeypatch.setenv("YTDLP_BROWSER_CANDIDATES", "chrome")
    monkeypatch.setenv("YTDLP_AUTO_BROWSER_COOKIES", "true")
    logger = StubLogger()

    def operation(_opts):
        raise Exception(
            "Sign in to confirm you're not a bot. Use --cookies-from-browser or --cookies for the authentication."
        )

    try:
        run_ytdlp_with_auth({"quiet": True}, operation, logger)
        assert False, "Expected a RuntimeError"
    except RuntimeError as exc:
        assert str(exc).startswith("YOUTUBE_AUTH_REQUIRED:")


def test_run_ytdlp_skips_locked_browser_cookie_db(monkeypatch):
    monkeypatch.delenv("YTDLP_COOKIES_FILE", raising=False)
    monkeypatch.setenv("YTDLP_COOKIES_FROM_BROWSER", "chrome")
    monkeypatch.setenv("YTDLP_BROWSER_CANDIDATES", "chrome,edge")
    monkeypatch.setenv("YTDLP_AUTO_BROWSER_COOKIES", "true")
    logger = StubLogger()

    def operation(opts):
        browser = opts.get("cookiesfrombrowser")
        if browser == ("chrome",):
            raise Exception("Could not copy Chrome cookie database")
        if browser is None:
            raise Exception(
                "Sign in to confirm you're not a bot. Use --cookies-from-browser or --cookies for the authentication."
            )
        return browser

    assert run_ytdlp_with_auth({"quiet": True}, operation, logger) == ("edge",)


def test_run_ytdlp_raises_cookie_help_when_browser_db_unavailable(monkeypatch):
    monkeypatch.delenv("YTDLP_COOKIES_FILE", raising=False)
    monkeypatch.setenv("YTDLP_COOKIES_FROM_BROWSER", "chrome")
    monkeypatch.setenv("YTDLP_AUTO_BROWSER_COOKIES", "false")
    logger = StubLogger()

    def operation(_opts):
        raise Exception("Could not copy Chrome cookie database")

    try:
        run_ytdlp_with_auth({"quiet": True}, operation, logger)
        assert False, "Expected a RuntimeError"
    except RuntimeError as exc:
        assert str(exc).startswith("YTDLP_BROWSER_COOKIES_UNAVAILABLE:")


def test_is_youtube_auth_error_detects_cookie_prompt():
    assert is_youtube_auth_error(
        Exception("Use --cookies-from-browser or --cookies for the authentication")
    )


def test_is_browser_cookie_error_detects_locked_db():
    assert is_browser_cookie_error(Exception("Could not copy Chrome cookie database"))
