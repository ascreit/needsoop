"""
ChromaDB storage for posts and embeddings.

Provides semantic search and storage capabilities using ChromaDB
as the vector database backend.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

from src.collectors.base import Post

logger = logging.getLogger(__name__)


class PostStore:
    """
    ChromaDB-backed storage for posts with embedding support.

    Provides methods for:
    - Storing posts with their embeddings
    - Semantic similarity search
    - Filtering by metadata (signal type, date, etc.)
    """

    COLLECTION_NAME = "posts"

    def __init__(
        self,
        persist_directory: str | Path | None = None,
        embedding_function: Any | None = None,
    ):
        """
        Initialize the post store.

        Args:
            persist_directory: Directory for persistent storage.
                              If None, uses in-memory storage.
            embedding_function: ChromaDB embedding function.
                               If None, embeddings must be provided manually.
        """
        if persist_directory:
            persist_directory = Path(persist_directory)
            persist_directory.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(persist_directory),
                settings=Settings(anonymized_telemetry=False),
            )
            logger.info(f"Using persistent ChromaDB at: {persist_directory}")
        else:
            self._client = chromadb.Client(
                settings=Settings(anonymized_telemetry=False)
            )
            logger.info("Using in-memory ChromaDB")

        self._embedding_function = embedding_function

        # Get or create the collection
        collection_kwargs = {
            "name": self.COLLECTION_NAME,
            "metadata": {"hnsw:space": "cosine"},
        }
        if embedding_function:
            collection_kwargs["embedding_function"] = embedding_function

        self._collection = self._client.get_or_create_collection(**collection_kwargs)
        logger.info(f"Collection '{self.COLLECTION_NAME}' ready with {self.count()} posts")

    def add(self, post: Post, embedding: list[float] | None = None) -> None:
        """
        Add a single post to the store.

        Args:
            post: The Post to add.
            embedding: Optional embedding vector. Required if no embedding function.
        """
        self.add_many([post], [embedding] if embedding else None)

    def add_many(
        self, posts: list[Post], embeddings: list[list[float]] | None = None
    ) -> None:
        """
        Add multiple posts to the store.

        Args:
            posts: List of Posts to add.
            embeddings: Optional list of embedding vectors.
        """
        if not posts:
            return

        ids = [post.id for post in posts]
        documents = [post.text for post in posts]
        metadatas = [
            {
                "source": post.source,
                "signal_type": post.signal_type or "",
                "signal_matches": ",".join(post.signal_matches),
                "author_id": post.author_id,
                "created_at": post.created_at.isoformat(),
                "collected_at": post.collected_at.isoformat(),
                "likes": post.likes,
                "reposts": post.reposts,
                "replies": post.replies,
                "language": post.language,
                "uri": post.uri or "",
                "cluster_id": post.cluster_id,
            }
            for post in posts
        ]

        add_kwargs = {
            "ids": ids,
            "documents": documents,
            "metadatas": metadatas,
        }

        if embeddings:
            add_kwargs["embeddings"] = embeddings

        try:
            self._collection.add(**add_kwargs)
            logger.debug(f"Added {len(posts)} posts to store")
        except Exception as e:
            # Handle duplicate IDs by upserting
            if "already exists" in str(e).lower():
                self._collection.upsert(**add_kwargs)
                logger.debug(f"Upserted {len(posts)} posts to store")
            else:
                raise

    def get(self, post_id: str) -> Post | None:
        """
        Get a post by ID.

        Args:
            post_id: The post ID.

        Returns:
            Post object if found, None otherwise.
        """
        result = self._collection.get(ids=[post_id], include=["documents", "metadatas"])

        if not result["ids"]:
            return None

        return self._result_to_post(
            result["ids"][0],
            result["documents"][0],
            result["metadatas"][0],
        )

    def search(
        self,
        query: str | None = None,
        query_embedding: list[float] | None = None,
        n_results: int = 10,
        signal_type: str | None = None,
        min_likes: int | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[tuple[Post, float]]:
        """
        Search for similar posts.

        Args:
            query: Text query for semantic search.
            query_embedding: Pre-computed embedding for search.
            n_results: Maximum number of results.
            signal_type: Filter by signal type.
            min_likes: Minimum number of likes.
            start_date: Filter posts created after this date.
            end_date: Filter posts created before this date.

        Returns:
            List of (Post, distance) tuples, sorted by similarity.
        """
        # Build where clause
        where = {}
        where_conditions = []

        if signal_type:
            where_conditions.append({"signal_type": signal_type})

        if min_likes is not None:
            where_conditions.append({"likes": {"$gte": min_likes}})

        if start_date:
            where_conditions.append({"created_at": {"$gte": start_date.isoformat()}})

        if end_date:
            where_conditions.append({"created_at": {"$lte": end_date.isoformat()}})

        if len(where_conditions) == 1:
            where = where_conditions[0]
        elif len(where_conditions) > 1:
            where = {"$and": where_conditions}

        # Perform query
        query_kwargs = {
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }

        if where:
            query_kwargs["where"] = where

        if query_embedding:
            query_kwargs["query_embeddings"] = [query_embedding]
        elif query:
            query_kwargs["query_texts"] = [query]
        else:
            # No query, return all (up to n_results)
            result = self._collection.get(
                include=["documents", "metadatas"],
                limit=n_results,
                where=where if where else None,
            )
            posts = []
            for i in range(len(result["ids"])):
                post = self._result_to_post(
                    result["ids"][i],
                    result["documents"][i],
                    result["metadatas"][i],
                )
                posts.append((post, 0.0))
            return posts

        result = self._collection.query(**query_kwargs)

        # Convert results to Post objects
        posts = []
        for i in range(len(result["ids"][0])):
            post = self._result_to_post(
                result["ids"][0][i],
                result["documents"][0][i],
                result["metadatas"][0][i],
            )
            distance = result["distances"][0][i] if result.get("distances") else 0.0
            posts.append((post, distance))

        return posts

    def get_all(
        self,
        signal_type: str | None = None,
        limit: int | None = None,
    ) -> list[Post]:
        """
        Get all posts, optionally filtered.

        Args:
            signal_type: Filter by signal type.
            limit: Maximum number of posts to return.

        Returns:
            List of Post objects.
        """
        where = {"signal_type": signal_type} if signal_type else None

        result = self._collection.get(
            include=["documents", "metadatas"],
            where=where,
            limit=limit,
        )

        posts = []
        for i in range(len(result["ids"])):
            post = self._result_to_post(
                result["ids"][i],
                result["documents"][i],
                result["metadatas"][i],
            )
            posts.append(post)

        return posts

    def get_embeddings(self, post_ids: list[str] | None = None) -> dict[str, list[float]]:
        """
        Get embeddings for posts.

        Args:
            post_ids: List of post IDs. If None, gets all embeddings.

        Returns:
            Dictionary mapping post IDs to embeddings.
        """
        if post_ids:
            result = self._collection.get(ids=post_ids, include=["embeddings"])
        else:
            result = self._collection.get(include=["embeddings"])

        embeddings = {}
        for i, post_id in enumerate(result["ids"]):
            if result["embeddings"] and result["embeddings"][i]:
                embeddings[post_id] = result["embeddings"][i]

        return embeddings

    def update_cluster(self, post_id: str, cluster_id: int) -> None:
        """
        Update the cluster ID for a post.

        Args:
            post_id: The post ID.
            cluster_id: The new cluster ID.
        """
        self._collection.update(
            ids=[post_id],
            metadatas=[{"cluster_id": cluster_id}],
        )

    def update_clusters(self, cluster_assignments: dict[str, int]) -> None:
        """
        Update cluster IDs for multiple posts.

        Args:
            cluster_assignments: Dictionary mapping post IDs to cluster IDs.
        """
        if not cluster_assignments:
            return

        ids = list(cluster_assignments.keys())
        metadatas = [{"cluster_id": cid} for cid in cluster_assignments.values()]

        self._collection.update(ids=ids, metadatas=metadatas)
        logger.debug(f"Updated cluster assignments for {len(ids)} posts")

    def count(self) -> int:
        """Get the total number of posts in the store."""
        return self._collection.count()

    def count_by_signal_type(self) -> dict[str, int]:
        """Get post counts grouped by signal type."""
        # ChromaDB doesn't have built-in aggregation, so we need to get all
        result = self._collection.get(include=["metadatas"])

        counts: dict[str, int] = {}
        for metadata in result["metadatas"]:
            signal_type = metadata.get("signal_type", "unknown")
            counts[signal_type] = counts.get(signal_type, 0) + 1

        return counts

    def delete(self, post_id: str) -> None:
        """Delete a post by ID."""
        self._collection.delete(ids=[post_id])

    def clear(self) -> None:
        """Delete all posts from the store."""
        # ChromaDB requires deleting by IDs
        result = self._collection.get()
        if result["ids"]:
            self._collection.delete(ids=result["ids"])
        logger.info("Cleared all posts from store")

    def _result_to_post(
        self, post_id: str, document: str, metadata: dict
    ) -> Post:
        """Convert a ChromaDB result to a Post object."""
        return Post(
            id=post_id,
            source=metadata.get("source", "unknown"),
            text=document,
            author_id=metadata.get("author_id", ""),
            created_at=datetime.fromisoformat(metadata.get("created_at", datetime.now().isoformat())),
            collected_at=datetime.fromisoformat(metadata.get("collected_at", datetime.now().isoformat())),
            signal_type=metadata.get("signal_type") or None,
            signal_matches=metadata.get("signal_matches", "").split(",") if metadata.get("signal_matches") else [],
            cluster_id=metadata.get("cluster_id", -1),
            likes=metadata.get("likes", 0),
            reposts=metadata.get("reposts", 0),
            replies=metadata.get("replies", 0),
            language=metadata.get("language", "en"),
            uri=metadata.get("uri") or None,
        )
