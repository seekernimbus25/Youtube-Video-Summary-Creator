import re
from typing import Optional
from urllib.parse import urlparse

def extract_video_id(url: str) -> Optional[str]:
    """
    Extracts the 11-character YouTube video ID from various URL formats.
    Matches:
    - youtube.com/watch?v=ID
    - youtu.be/ID
    - youtube.com/embed/ID
    - youtube.com/v/ID
    - youtube.com/e/ID
    - m.youtube.com/...
    """
    normalized_url = url.strip()
    if not normalized_url:
        return None

    if "://" not in normalized_url:
        normalized_url = f"https://{normalized_url}"

    parsed = urlparse(normalized_url)
    hostname = (parsed.hostname or "").lower()

    is_youtube_host = hostname == "youtu.be" or hostname == "youtube.com" or hostname.endswith(".youtube.com")
    if not is_youtube_host:
        return None

    pattern = r'(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, normalized_url)
    if match:
        return match.group(1)
    return None
