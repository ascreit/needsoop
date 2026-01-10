"""
Embedding generation using local sentence-transformers.

Generates vector embeddings for posts locally without API calls.
"""

import logging
from typing import Iterator

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384


class EmbeddingGenerator:
    """
    Generates embeddings using local sentence-transformers.

    No API key required. Runs entirely on local machine.
    """

    def __init__(self, model: str = DEFAULT_MODEL):
        """
        Initialize the embedding generator.

        Args:
            model: Model name for sentence-transformers.
        """
        self.model_name = model
        self._model = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            logger.info(f"Loading model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def generate(self, text: str) -> list[float]:
        """
        Generate embedding for a single text.

        Args:
            text: The text to embed.

        Returns:
            Embedding vector.
        """
        embedding = self.model.encode(text)
        return embedding.tolist()

    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []

        embeddings = self.model.encode(texts, show_progress_bar=False)
        return [e.tolist() for e in embeddings]

    def generate_all(
        self, texts: list[str], batch_size: int = 32, show_progress: bool = True
    ) -> Iterator[tuple[int, list[float]]]:
        """
        Generate embeddings for all texts with batching.

        Args:
            texts: List of texts to embed.
            batch_size: Number of texts per batch.
            show_progress: Whether to log progress.

        Yields:
            Tuples of (index, embedding) for each text.
        """
        total = len(texts)
        processed = 0

        for i in range(0, total, batch_size):
            batch = texts[i : i + batch_size]
            embeddings = self.generate_batch(batch)

            for j, embedding in enumerate(embeddings):
                yield i + j, embedding

            processed += len(batch)
            if show_progress:
                logger.info(f"Generated embeddings: {processed}/{total}")
