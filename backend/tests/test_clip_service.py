import os
import tempfile

from PIL import Image

TEST_TMP_ROOT = os.path.join(os.path.dirname(__file__), "_tmp")


def _make_test_image(color: tuple, path: str):
    """Create a solid-color JPEG for testing frame ranking."""
    img = Image.new("RGB", (64, 64), color=color)
    img.save(path, "JPEG")


def test_rank_frames_returns_valid_index():
    from services.clip_service import rank_frames

    os.makedirs(TEST_TMP_ROOT, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as tmpdir:
        red_path = os.path.join(tmpdir, "red.jpg")
        blue_path = os.path.join(tmpdir, "blue.jpg")
        _make_test_image((220, 30, 30), red_path)
        _make_test_image((30, 30, 220), blue_path)

        result = rank_frames([red_path, blue_path], section_title="red color sample")
        assert result in (0, 1)


def test_rank_frames_single_image_returns_zero():
    from services.clip_service import rank_frames

    os.makedirs(TEST_TMP_ROOT, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as tmpdir:
        img_path = os.path.join(tmpdir, "frame.jpg")
        _make_test_image((100, 100, 100), img_path)
        result = rank_frames([img_path], section_title="any text")
        assert result == 0


def test_rank_frames_empty_list_returns_zero():
    from services.clip_service import rank_frames

    result = rank_frames([], section_title="anything")
    assert result == 0
