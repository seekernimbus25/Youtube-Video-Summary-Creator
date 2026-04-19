import logging
from typing import List

logger = logging.getLogger(__name__)

_model = None
_processor = None
_clip_available = None


def _load_clip() -> bool:
    global _model, _processor, _clip_available

    if _clip_available is not None:
        return _clip_available

    try:
        from transformers import CLIPModel, CLIPProcessor

        _model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        _processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        _model.eval()
        _clip_available = True
        logger.info("CLIP model loaded successfully.")
    except Exception as exc:
        logger.warning(f"CLIP unavailable: {exc}. Falling back to index 0.")
        _clip_available = False

    return _clip_available


def rank_frames(image_paths: List[str], section_title: str) -> int:
    """
    Return the index of the image most semantically similar to section_title.
    Falls back to 0 if CLIP is unavailable or ranking fails.
    """
    if not image_paths or len(image_paths) == 1:
        return 0

    if not _load_clip():
        return 0

    try:
        import torch
        from PIL import Image

        images = []
        valid_indices = []
        for index, image_path in enumerate(image_paths):
            try:
                images.append(Image.open(image_path).convert("RGB"))
                valid_indices.append(index)
            except Exception as exc:
                logger.warning(f"Could not open image {image_path}: {exc}")

        if not images:
            return 0

        inputs = _processor(
            text=[section_title],
            images=images,
            return_tensors="pt",
            padding=True,
        )

        with torch.no_grad():
            outputs = _model(**inputs)

        scores = outputs.logits_per_image[:, 0].tolist()
        best_local_index = scores.index(max(scores))
        return valid_indices[best_local_index]
    except Exception as exc:
        logger.warning(f"CLIP ranking failed: {exc}. Falling back to index 0.")
        return 0
