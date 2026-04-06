import re
from typing import Optional

def extract_video_id(url: str) -> Optional[str]:
    """
    Extracts the 11-character YouTube video ID from various URL formats.
    Matches:
    - youtube.com/watch?v=ID
    - youtu.be/ID
    - youtube.com/shorts/ID
    - m.youtube.com/...
    """
    pattern = r'(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    return None
