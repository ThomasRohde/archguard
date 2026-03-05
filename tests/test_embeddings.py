"""Tests for embeddings module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from archguard.core.embeddings import (
    blob_to_embedding,
    cosine_similarity,
    embed_guardrail,
    embed_text,
    embedding_to_blob,
    load_model,
)


class TestCosinesimilarity:
    def test_identical_vectors(self) -> None:
        a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        assert abs(cosine_similarity(a, a) - 1.0) < 1e-6

    def test_orthogonal_vectors(self) -> None:
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        assert abs(cosine_similarity(a, b)) < 1e-6

    def test_opposite_vectors(self) -> None:
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([-1.0, 0.0], dtype=np.float32)
        assert abs(cosine_similarity(a, b) + 1.0) < 1e-6

    def test_zero_vector(self) -> None:
        a = np.array([0.0, 0.0], dtype=np.float32)
        b = np.array([1.0, 1.0], dtype=np.float32)
        assert cosine_similarity(a, b) == 0.0


class TestBlobRoundTrip:
    def test_roundtrip(self) -> None:
        original = np.array([0.1, 0.2, 0.3, -0.5], dtype=np.float32)
        blob = embedding_to_blob(original)
        recovered = blob_to_embedding(blob)
        np.testing.assert_array_almost_equal(original, recovered)

    def test_blob_is_bytes(self) -> None:
        vec = np.array([1.0, 2.0], dtype=np.float32)
        blob = embedding_to_blob(vec)
        assert isinstance(blob, bytes)
        assert len(blob) == 2 * 4  # 2 floats * 4 bytes each


class TestLoadModel:
    def test_missing_dir(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            load_model(tmp_path / "nonexistent")

    def test_empty_dir(self, tmp_path) -> None:
        empty = tmp_path / "empty_model"
        empty.mkdir()
        with pytest.raises(FileNotFoundError):
            load_model(empty)

    def test_loads_from_pretrained(self, tmp_path) -> None:
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "config.json").write_text("{}")

        mock_model = MagicMock()
        with patch("model2vec.StaticModel") as mock_cls:
            mock_cls.from_pretrained.return_value = mock_model
            result = load_model(model_dir)
            mock_cls.from_pretrained.assert_called_once_with(str(model_dir))
            assert result is mock_model


class TestEmbedText:
    def test_calls_model_encode(self) -> None:
        mock_model = MagicMock()
        expected = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        mock_model.encode.return_value = expected
        result = embed_text(mock_model, "test text")
        mock_model.encode.assert_called_once_with("test text")
        np.testing.assert_array_equal(result, expected)


class TestEmbedGuardrail:
    def test_concatenates_fields(self) -> None:
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([0.1], dtype=np.float32)

        # Create a minimal guardrail-like object
        g = MagicMock()
        g.title = "Test Title"
        g.guidance = "Test Guidance"
        g.rationale = "Test Rationale"

        embed_guardrail(mock_model, g)
        call_args = mock_model.encode.call_args[0][0]
        assert "Test Title" in call_args
        assert "Test Guidance" in call_args
        assert "Test Rationale" in call_args
