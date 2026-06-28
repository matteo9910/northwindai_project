from __future__ import annotations

from backend.config import Settings, get_settings


class LocalBgeEmbeddings:
    def __init__(self, settings: Settings | None = None):
        settings = settings or get_settings()
        self.model_name = settings.embedding_model
        self.dimension = settings.embedding_dimension
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is required for local BGE embeddings"
            ) from exc
        self._model = SentenceTransformer(self.model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
