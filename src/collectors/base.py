"""
Base classes for data collectors.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator


@dataclass
class Post:
    """
    Represents a collected post from any source.

    Attributes:
        id: Unique identifier (e.g., "bsky_{cid}")
        source: Source platform (e.g., "bluesky")
        text: Post content
        author_id: Author identifier (e.g., DID for Bluesky)
        created_at: When the post was created
        collected_at: When the post was collected
        signal_type: Detected signal type (e.g., "frustration", "desire")
        signal_matches: List of matched patterns
        embedding: Vector embedding (1536 dimensions for OpenAI)
        cluster_id: Cluster assignment (-1 = noise)
        likes: Number of likes
        reposts: Number of reposts
        replies: Number of replies
        language: Detected language code
        uri: Original URI of the post
        metadata: Additional source-specific metadata
    """
    id: str
    source: str
    text: str
    author_id: str
    created_at: datetime
    collected_at: datetime = field(default_factory=datetime.utcnow)

    # Analysis results (populated later)
    signal_type: str | None = None
    signal_matches: list[str] = field(default_factory=list)
    embedding: list[float] | None = None
    cluster_id: int = -1

    # Engagement metrics
    likes: int = 0
    reposts: int = 0
    replies: int = 0

    # Additional info
    language: str = "en"
    uri: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "source": self.source,
            "text": self.text,
            "author_id": self.author_id,
            "created_at": self.created_at.isoformat(),
            "collected_at": self.collected_at.isoformat(),
            "signal_type": self.signal_type,
            "signal_matches": self.signal_matches,
            "cluster_id": self.cluster_id,
            "likes": self.likes,
            "reposts": self.reposts,
            "replies": self.replies,
            "language": self.language,
            "uri": self.uri,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Post":
        """Create Post from dictionary."""
        data = data.copy()
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("collected_at"), str):
            data["collected_at"] = datetime.fromisoformat(data["collected_at"])
        # Remove embedding from dict as it's handled separately
        data.pop("embedding", None)
        return cls(**data)


class BaseCollector(ABC):
    """
    Abstract base class for data collectors.

    Subclasses must implement:
        - collect(): Generate posts from the source
        - source_name: Property returning the source identifier
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the source identifier (e.g., 'bluesky')."""
        pass

    @abstractmethod
    def collect(self, **kwargs) -> Iterator[Post]:
        """
        Collect posts from the source.

        Yields:
            Post objects matching the configured criteria.
        """
        pass

    def start(self, **kwargs) -> None:
        """
        Start continuous collection (for streaming sources).

        Override this method for sources that support real-time streaming.
        Default implementation just calls collect() in a loop.
        """
        for post in self.collect(**kwargs):
            yield post

    def stop(self) -> None:
        """
        Stop continuous collection.

        Override this method for sources that need cleanup.
        """
        pass
