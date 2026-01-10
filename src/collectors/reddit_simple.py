"""
Reddit collector without API authentication.

Uses Reddit's public JSON endpoints (adding .json to URLs).
No API key required, but rate limited.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Iterator

import requests

from .base import BaseCollector, Post

logger = logging.getLogger(__name__)

# Default subreddits for indie hacker / startup pain points
DEFAULT_SUBREDDITS = [
    "Entrepreneur",
    "smallbusiness",
    "startups",
    "SaaS",
    "indiehackers",
    "microsaas",
    "SideProject",
    "freelance",
]

class RedditSimpleCollector(BaseCollector):
    """
    Collector for Reddit posts using public JSON endpoints.

    No API key required. Uses https://reddit.com/r/{subreddit}.json
    """

    def __init__(
        self,
        subreddits: list[str] | None = None,
        min_score: int = 1,
        min_length: int = 50,
        max_length: int = 5000,
        delay: float = 2.0,  # Delay between requests to avoid rate limiting
    ):
        self.subreddits = subreddits or DEFAULT_SUBREDDITS
        self.min_score = min_score
        self.min_length = min_length
        self.max_length = max_length
        self.delay = delay

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })

    @property
    def source_name(self) -> str:
        return "reddit"

    def _fetch_subreddit(
        self,
        subreddit: str,
        sort: str = "hot",
        limit: int = 25,
        after: str | None = None,
    ) -> dict | None:
        """Fetch posts from a subreddit using JSON endpoint."""
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
        params = {"limit": min(limit, 100)}  # Reddit max is 100
        if after:
            params["after"] = after

        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch r/{subreddit}: {e}")
            return None

    def _parse_post(self, post_data: dict) -> Post | None:
        """Parse a post from Reddit JSON data."""
        try:
            data = post_data.get("data", {})

            # Combine title and selftext
            title = data.get("title", "")
            selftext = data.get("selftext", "")
            if selftext and selftext != "[removed]" and selftext != "[deleted]":
                text = f"{title}\n\n{selftext}"
            else:
                text = title

            # Length filter
            if len(text) < self.min_length or len(text) > self.max_length:
                return None

            # Score filter
            score = data.get("score", 0)
            if score < self.min_score:
                return None

            # Parse creation time
            created_utc = data.get("created_utc", 0)
            created_at = datetime.fromtimestamp(created_utc, tz=timezone.utc)

            return Post(
                id=f"reddit_{data.get('id', '')}",
                source=self.source_name,
                text=text,
                author_id=data.get("author", "[deleted]"),
                created_at=created_at,
                signal_type=None,
                signal_matches=[],
                likes=score,
                replies=data.get("num_comments", 0),
                uri=f"https://reddit.com{data.get('permalink', '')}",
                metadata={
                    "subreddit": data.get("subreddit", ""),
                    "flair": data.get("link_flair_text"),
                    "is_self": data.get("is_self", False),
                    "upvote_ratio": data.get("upvote_ratio", 0),
                },
            )

        except Exception as e:
            logger.debug(f"Failed to parse post: {e}")
            return None

    def collect(
        self,
        limit: int = 50,
        sort: str = "hot",
        **kwargs
    ) -> Iterator[Post]:
        """
        Collect posts from configured subreddits.

        Args:
            limit: Maximum posts per subreddit.
            sort: Sort method (hot, new, top, rising).

        Yields:
            Post objects.
        """
        collected = 0

        for subreddit in self.subreddits:
            logger.info(f"Collecting from r/{subreddit}...")

            data = self._fetch_subreddit(subreddit, sort=sort, limit=limit)
            if not data:
                continue

            posts = data.get("data", {}).get("children", [])

            for post_data in posts:
                post = self._parse_post(post_data)
                if post:
                    collected += 1
                    yield post

            # Rate limiting
            time.sleep(self.delay)

        logger.info(f"Collection complete. Total: {collected}")

    def search(
        self,
        query: str,
        limit: int = 50,
        sort: str = "relevance",
        time_filter: str = "week",
        **kwargs
    ) -> Iterator[Post]:
        """
        Search Reddit for posts matching a query.

        Args:
            query: Search query.
            limit: Maximum posts.
            sort: Sort (relevance, hot, top, new, comments).
            time_filter: Time filter (hour, day, week, month, year, all).

        Yields:
            Post objects.
        """
        url = "https://www.reddit.com/search.json"
        params = {
            "q": query,
            "sort": sort,
            "t": time_filter,
            "limit": min(limit, 100),
        }

        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return

        posts = data.get("data", {}).get("children", [])
        collected = 0

        for post_data in posts:
            post = self._parse_post(post_data)
            if post:
                collected += 1
                yield post

        logger.info(f"Search complete. Found: {collected}")
