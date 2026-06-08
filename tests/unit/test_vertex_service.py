"""
Unit tests for the Vertex AI generative model service wrapper.
"""

from unittest.mock import MagicMock, patch

import pytest

from api.services.vertex_service import VertexService


@pytest.fixture
def mock_vertex_init():
    with patch("api.services.vertex_service.vertexai.init") as mock_init:
        yield mock_init


@pytest.fixture
def mock_generative_model():
    with patch("api.services.vertex_service.GenerativeModel") as mock_model_class:
        mock_instance = MagicMock()
        mock_model_class.return_value = mock_instance
        yield mock_instance


def test_vertex_service_ping(mock_vertex_init, mock_generative_model):
    # Setup mock return response
    mock_response = MagicMock()
    mock_response.text = "ok"
    mock_generative_model.generate_content.return_value = mock_response

    service = VertexService(
        project_id="test-proj",
        region="us-central1",
        model_id="gemini-1.5-pro",
        temperature=0.2,
        max_output_tokens=1024,
    )
    service.ping()
    mock_generative_model.generate_content.assert_called_once()


def test_vertex_service_generate_success(mock_vertex_init, mock_generative_model):
    mock_response = MagicMock()
    mock_candidate = MagicMock()
    mock_candidate.finish_reason.name = "STOP"
    mock_response.candidates = [mock_candidate]
    mock_response.text = "Here is the response."
    mock_generative_model.generate_content.return_value = mock_response

    service = VertexService(
        project_id="test-proj",
        region="us-central1",
        model_id="gemini-1.5-pro",
        temperature=0.2,
        max_output_tokens=1024,
    )
    res = service.generate("Hello model")
    assert res == "Here is the response."


def test_vertex_service_generate_safety_blocked(mock_vertex_init, mock_generative_model):
    mock_response = MagicMock()
    mock_candidate = MagicMock()
    mock_candidate.finish_reason.name = "SAFETY"
    mock_response.candidates = [mock_candidate]
    mock_generative_model.generate_content.return_value = mock_response

    service = VertexService(
        project_id="test-proj",
        region="us-central1",
        model_id="gemini-1.5-pro",
        temperature=0.2,
        max_output_tokens=1024,
    )
    with pytest.raises(ValueError, match="blocked by Vertex AI safety filter"):
        service.generate("unsafe input")
