"""
Bluesky Firehose collector.

Connects to the Bluesky AT Protocol Firehose to collect posts
that match configured signal patterns.
"""

import logging
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


class BlueskyCollector(BaseCollector):
    """
    Collector for Bluesky posts via the AT Protocol Firehose.

    The Firehose provides a real-time stream of all public posts on Bluesky.
    This collector filters posts based on signal patterns and yields matching posts.
    """

    def __init__(
        self,
        signal_matcher: Callable[[str], tuple[str | None, list[str]]] | None = None,
        min_length: int = 20,
        max_length: int = 1000,
    ):
        """
        Initialize the Bluesky collector.

        Args:
            signal_matcher: Function that takes text and returns (signal_type, matches).
                           If None, all posts are collected.
            min_length: Minimum post length to consider.
            max_length: Maximum post length to consider.
        """
        self.signal_matcher = signal_matcher
        self.min_length = min_length
        self.max_length = max_length
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

            # Signal matching
            signal_type = None
            signal_matches = []
            if self.signal_matcher:
                signal_type, signal_matches = self.signal_matcher(text)
                if signal_type is None:
                    return None  # No signal detected, skip

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
                signal_type=signal_type,
                signal_matches=signal_matches,
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
