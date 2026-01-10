"""
Bluesky Firehose collector.

Connects to the Bluesky AT Protocol Firehose to collect posts.
Uses minimal exclusion filtering (politics) instead of keyword matching.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Callable, Iterator

from atproto import (
    CAR,
    FirehoseSubscribeReposClient,
    firehose_models,
    models,
    parse_subscribe_repos_message,
)

# Type aliases for cleaner code
Commit = models.ComAtprotoSyncSubscribeRepos.Commit
RepoOp = models.ComAtprotoSyncSubscribeRepos.RepoOp

from .base import BaseCollector, Post

logger = logging.getLogger(__name__)

# Political/news keywords to exclude (case-insensitive)
EXCLUSION_KEYWORDS = [
    "trump", "biden", "maga", "congress", "senate",
    "democrat", "republican", "liberal", "conservative",
    "election", "vote", "voting",
    "israel", "gaza", "palestine", "ukraine",
    "murder",
]

# Compile regex for efficient matching
EXCLUSION_PATTERN = re.compile(
    r"\b(" + "|".join(EXCLUSION_KEYWORDS) + r")\b",
    re.IGNORECASE
)


class BlueskyCollector(BaseCollector):
    """
    Collector for Bluesky posts via the AT Protocol Firehose.

    The Firehose provides a real-time stream of all public posts on Bluesky.
    Uses minimal exclusion filtering (politics/news) instead of keyword matching.
    """

    def __init__(
        self,
        min_length: int = 50,
        max_length: int = 1000,
        japanese_only: bool = False,
    ):
        """
        Initialize the Bluesky collector.

        Args:
            min_length: Minimum post length to consider.
            max_length: Maximum post length to consider.
            japanese_only: If True, only collect posts with Japanese language tag.
        """
        self.min_length = min_length
        self.max_length = max_length
        self.japanese_only = japanese_only
        self._client: FirehoseSubscribeReposClient | None = None
        self._running = False
        self._collected_posts: list[Post] = []

    @property
    def source_name(self) -> str:
        return "bluesky"

    def _parse_post_record(
        self, commit: Commit, op: RepoOp
    ) -> Post | None:
        """
        Parse a post from a Firehose operation.

        Args:
            commit: The repository commit containing the post.
            op: The operation (create, update, delete).

        Returns:
            Post object if valid, None otherwise.
        """
        try:
            # Decode the CAR file to get the record
            car = CAR.from_bytes(commit.blocks)
            record = car.blocks.get(op.cid)

            if record is None:
                return None

            # Parse as a post record
            post_record = models.AppBskyFeedPost.Record.model_validate(record)
            text = post_record.text

            # Length filter
            if len(text) < self.min_length or len(text) > self.max_length:
                return None

            # Exclusion filter (politics/news)
            if EXCLUSION_PATTERN.search(text):
                return None

            # Japanese language filter
            if self.japanese_only:
                langs = post_record.langs or []
                if "ja" not in langs:
                    return None

            # Parse creation time
            created_at = datetime.now(timezone.utc)
            if post_record.created_at:
                try:
                    created_at = datetime.fromisoformat(
                        post_record.created_at.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            # Build the post URI
            uri = f"at://{commit.repo}/app.bsky.feed.post/{op.path.split('/')[-1]}"

            # Create Post object
            post = Post(
                id=f"bsky_{op.cid}",
                source=self.source_name,
                text=text,
                author_id=commit.repo,  # DID
                created_at=created_at,
                uri=uri,
                metadata={
                    "cid": str(op.cid),
                    "reply_parent": (
                        post_record.reply.parent.uri if post_record.reply else None
                    ),
                    "langs": post_record.langs or [],
                },
            )

            # Set language if available
            if post_record.langs and len(post_record.langs) > 0:
                post.language = post_record.langs[0]

            return post

        except Exception as e:
            logger.debug(f"Failed to parse post: {e}")
            return None

    def collect(self, limit: int | None = None, **kwargs) -> Iterator[Post]:
        """
        Collect posts from Firehose (non-streaming, collects up to limit).

        Args:
            limit: Maximum number of posts to collect. If None, collects indefinitely.

        Yields:
            Post objects matching the signal patterns.
        """
        self._collected_posts = []
        count = 0

        def on_message(message: firehose_models.MessageFrame) -> None:
            nonlocal count

            # Check if we've reached the limit
            if limit is not None and count >= limit:
                self.stop()
                return

            try:
                commit = parse_subscribe_repos_message(message)

                # Only process commits
                if not isinstance(commit, models.ComAtprotoSyncSubscribeRepos.Commit):
                    return

                # Skip commits without operations
                if not commit.ops:
                    return

                for op in commit.ops:
                    # Only process post creates
                    if op.action != "create":
                        continue
                    if not op.path.startswith("app.bsky.feed.post"):
                        continue

                    post = self._parse_post_record(commit, op)
                    if post:
                        self._collected_posts.append(post)
                        count += 1
                        logger.debug(f"Collected post {count}: {post.text[:50]}...")

                        if limit is not None and count >= limit:
                            self.stop()
                            return

            except FirehoseError as e:
                logger.error(f"Firehose error: {e}")
            except Exception as e:
                logger.debug(f"Error processing message: {e}")

        self._client = FirehoseSubscribeReposClient()
        self._running = True

        try:
            logger.info("Starting Bluesky Firehose collection...")
            self._client.start(on_message)
        except Exception as e:
            if self._running:  # Unexpected error
                logger.error(f"Firehose collection error: {e}")
                raise
        finally:
            self._running = False

        # Yield collected posts
        for post in self._collected_posts:
            yield post

    def start_streaming(
        self, callback: Callable[[Post], None], **kwargs
    ) -> None:
        """
        Start continuous streaming collection.

        Args:
            callback: Function to call for each collected post.
        """

        def on_message(message: firehose_models.MessageFrame) -> None:
            try:
                commit = parse_subscribe_repos_message(message)

                if not isinstance(commit, models.ComAtprotoSyncSubscribeRepos.Commit):
                    return

                if not commit.ops:
                    return

                for op in commit.ops:
                    if op.action != "create":
                        continue
                    if not op.path.startswith("app.bsky.feed.post"):
                        continue

                    post = self._parse_post_record(commit, op)
                    if post:
                        callback(post)

            except FirehoseError as e:
                logger.error(f"Firehose error: {e}")
            except Exception as e:
                logger.debug(f"Error processing message: {e}")

        self._client = FirehoseSubscribeReposClient()
        self._running = True

        try:
            logger.info("Starting Bluesky Firehose streaming...")
            self._client.start(on_message)
        except Exception as e:
            if self._running:
                logger.error(f"Firehose streaming error: {e}")
                raise
        finally:
            self._running = False

    def stop(self) -> None:
        """Stop the Firehose collection."""
        self._running = False
        if self._client:
            try:
                self._client.stop()
            except Exception:
                pass
            self._client = None
        logger.info("Bluesky Firehose collection stopped.")
