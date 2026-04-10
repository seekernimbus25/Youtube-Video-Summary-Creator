import os
from contextlib import contextmanager


PROXY_ENV_VARS = [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
]


def disable_system_proxies_if_configured() -> None:
    """
    Disable inherited proxy environment variables by default.

    Set USE_SYSTEM_PROXY=true to preserve the host proxy configuration.
    """
    if os.environ.get("USE_SYSTEM_PROXY", "").strip().lower() in {"1", "true", "yes"}:
        return

    for env_name in PROXY_ENV_VARS:
        os.environ.pop(env_name, None)


@contextmanager
def without_proxy_env():
    saved = {env_name: os.environ.get(env_name) for env_name in PROXY_ENV_VARS}
    try:
        for env_name in PROXY_ENV_VARS:
            os.environ.pop(env_name, None)
        yield
    finally:
        for env_name, value in saved.items():
            if value is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = value
