"""Model2Vec wrapper for computing and comparing embeddings."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import numpy.typing as npt

if TYPE_CHECKING:
    from archguard.core.models import Guardrail


def load_model(model_dir: Path) -> Any:
    """Load the Model2Vec static embedding model from disk."""
    from model2vec import StaticModel

    model_dir = Path(model_dir)
    if not model_dir.exists() or not any(model_dir.iterdir()):
        raise FileNotFoundError(f"Model directory is empty or missing: {model_dir}")
    return StaticModel.from_pretrained(str(model_dir))


def embed_text(model: Any, text: str) -> npt.NDArray[np.float32]:
    """Compute embedding for a single text string."""
    return model.encode(text)  # type: ignore[no-any-return]


def embed_guardrail(model: Any, g: Guardrail) -> npt.NDArray[np.float32]:
    """Compute embedding for a guardrail by concatenating key fields."""
    text = f"{g.title} {g.guidance} {g.rationale}"
    return embed_text(model, text)


def cosine_similarity(a: npt.NDArray[np.float32], b: npt.NDArray[np.float32]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def embedding_to_blob(embedding: npt.NDArray[np.float32]) -> bytes:
    """Convert a numpy float32 array to bytes for SQLite BLOB storage."""
    return embedding.astype(np.float32).tobytes()


def blob_to_embedding(blob: bytes) -> npt.NDArray[np.float32]:
    """Convert a SQLite BLOB back to a numpy float32 array."""
    return np.frombuffer(blob, dtype=np.float32)


MODEL_SUBDIR = Path("models") / "potion-base-8M"

# Bundled model ships inside the package itself
_BUNDLED_MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "potion-base-8M"


def bundled_model_dir() -> Path:
    """Return the path to the bundled potion-base-8M model."""
    return _BUNDLED_MODEL_DIR


def try_load_model(data_dir: Path) -> Any:
    """Try to load the Model2Vec model; return None if unavailable.

    Checks data_dir first (for overrides), then falls back to the
    bundled model shipped with the package.
    """
    for candidate in [data_dir / MODEL_SUBDIR, _BUNDLED_MODEL_DIR]:
        try:
            return load_model(candidate)
        except Exception:
            continue
    return None
