from unittest.mock import AsyncMock, patch

import pytest

import services.study_service as svc


@pytest.mark.anyio
async def test_generate_flashcards_validates_json_payload():
    with patch("services.study_service.rag_service.search", AsyncMock(return_value=[
        {"text": "Utilities scale and invert CV signals.", "timestamp": "02:14", "start_time": 134.0}
    ])), patch("services.study_service.complete_llm_text", AsyncMock(return_value="""
    {
      "cards": [
        {
          "id": "fc-1",
          "front": "What does an attenuverter do?",
          "back": "It scales and can invert a control-voltage signal.",
          "topic": "Utilities",
          "timestamp": "02:14"
        }
      ]
    }
    """)):
        result = await svc.generate_flashcards("vid1")

    assert result.cards[0].topic == "Utilities"
    assert result.cards[0].timestamp == "02:14"


@pytest.mark.anyio
async def test_generate_quiz_raises_on_malformed_json():
    with patch("services.study_service.rag_service.search", AsyncMock(return_value=[
        {"text": "Filters shape harmonics.", "timestamp": "01:20", "start_time": 80.0}
    ])), patch("services.study_service.complete_llm_text", AsyncMock(return_value="{not json")):
        with pytest.raises(Exception):
            await svc.generate_quiz("vid1")
