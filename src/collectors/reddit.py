"""
Reddit collector.

Collects posts from specified subreddits using PRAW (Python Reddit API Wrapper).
Focuses on pain points, frustrations, and unmet needs.
"""

import logging
import os
import re
from datetime import datetime, timezone
from typing import Iterator

import praw
from praw.models import Submission

from .base import BaseCollector, Post

logger = logging.getLogger(__name__)

# Subreddits focused on indie hackers, startups, and business problems
DEFAULT_SUBREDDITS = [
    "Entrepreneur",
    "smallbusiness",
    "startups",
    "SaaS",
    "indiehackers",
    "microsaas",
    "SideProject",
    "slavelabour",  # People looking for solutions
    "freelance",
    "digitalnomad",
]

# Keywords that indicate pain points or needs
PAIN_KEYWORDS = [
    # Frustration signals
    r"\bhate\b",
    r"\bfrustrat",
    r"\bannoying\b",
    r"\bpain\b",
    r"\bstruggl",
    r"\btedious\b",
    r"\bwaste.{0,10}time\b",
    r"\btime.{0,10}consuming\b",
    # Need signals
    r"\bneed\b",
    r"\bwish\b",
    r"\bwant\b",
    r"\blooking for\b",
    r"\bsearching for\b",
    r"\bdoes anyone know\b",
    r"\bis there a\b",
    r"\bany.{0,10}(tool|app|service|solution)\b",
    # Problem signals
    r"\bproblem\b",
    r"\bissue\b",
    r"\bchalleng",
    r"\bdifficult",
    r"\bhard to\b",
    r"\bcan't\b",
    r"\bcannot\b",
    r"\bunable to\b",
    # Question signals
    r"\bhow do (i|you|we)\b",
    r"\bhow can (i|you|we)\b",
    r"\bwhat.{0,10}(tool|app|service|solution)\b",
    r"\brecommend",
    r"\bsuggestion",
    r"\badvice\b",
]

PAIN_PATTERN = re.compile(
    "|".join(PAIN_KEYWORDS),
    re.IGNORECASE
)


class RedditCollector(BaseCollector):
    """
    Collector for Reddit posts using PRAW.

    Requires environment variables:
        - REDDIT_CLIENT_ID
        - REDDIT_CLIENT_SECRET
        - REDDIT_USER_AGENT (optional, defaults to "needscoop:v1.0")
    """

    def __init__(
        self,
        subreddits: list[str] | None = None,
        min_score: int = 1,
        min_comments: int = 0,
        min_length: int = 50,
        max_length: int = 5000,
        filter_pain_keywords: bool = True,
    ):
        """
        Initialize the Reddit collector.

        Args:
            subreddits: List of subreddit names to collect from.
            min_score: Minimum post score (upvotes - downvotes).
            min_comments: Minimum number of comments.
            min_length: Minimum post length.
            max_length: Maximum post length.
            filter_pain_keywords: If True, only collect posts matching pain keywords.
        """
        self.subreddits = subreddits or DEFAULT_SUBREDDITS
        self.min_score = min_score
        self.min_comments = min_comments
        self.min_length = min_length
        self.max_length = max_length
        self.filter_pain_keywords = filter_pain_keywords

        self._reddit: praw.Reddit | None = None

    @property
    def source_name(self) -> str:
        return "reddit"

    def _get_reddit(self) -> praw.Reddit:
        """Get or create Reddit API client."""
        if self._reddit is None:
            client_id = os.environ.get("REDDIT_CLIENT_ID")
            client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
            user_agent = os.environ.get("REDDIT_USER_AGENT", "needscoop:v1.0")

            if not client_id or not client_secret:
                raise ValueError(
                    "Reddit API credentials not found. "
                    "Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET environment variables."
                )

            self._reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )
            logger.info("Reddit API client initialized")

        return self._reddit

    def _parse_submission(self, submission: Submission) -> Post | None:
        """
        Parse a Reddit submission into a Post.

        Args:
            submission: PRAW Submission object.

        Returns:
            Post object if valid, None otherwise.
        """
        try:
            # Combine title and selftext
            text = submission.title
            if submission.selftext and submission.selftext != "[removed]":
                text = f"{submission.title}\n\n{submission.selftext}"

            # Length filter
            if len(text) < self.min_length or len(text) > self.max_length:
                return None

            # Score filter
            if submission.score < self.min_score:
                return None

            # Comments filter
            if submission.num_comments < self.min_comments:
                return None

            # Pain keywords filter
            if self.filter_pain_keywords:
                if not PAIN_PATTERN.search(text):
                    return None

            # Parse creation time
            created_at = datetime.fromtimestamp(
                submission.created_utc, tz=timezone.utc
            )

            # Detect signal type based on matched keywords
            signal_matches = PAIN_PATTERN.findall(text.lower())
            signal_type = self._classify_signal(signal_matches)

            return Post(
                id=f"reddit_{submission.id}",
                source=self.source_name,
                text=text,
                author_id=str(submission.author) if submission.author else "[deleted]",
                created_at=created_at,
                signal_type=signal_type,
                signal_matches=list(set(signal_matches))[:5],  # Top 5 unique matches
                likes=submission.score,
                replies=submission.num_comments,
                uri=f"https://reddit.com{submission.permalink}",
                metadata={
                    "subreddit": submission.subreddit.display_name,
                    "flair": submission.link_flair_text,
                    "is_self": submission.is_self,
                    "upvote_ratio": submission.upvote_ratio,
                },
            )

        except Exception as e:
            logger.debug(f"Failed to parse submission: {e}")
            return None

    def _classify_signal(self, matches: list[str]) -> str:
        """Classify the signal type based on matched keywords."""
        matches_lower = [m.lower() for m in matches]

        if any(m in matches_lower for m in ["hate", "frustrat", "annoying", "tedious"]):
            return "frustration"
        elif any(m in matches_lower for m in ["need", "want", "wish", "looking for"]):
            return "desire"
        elif any(m in matches_lower for m in ["problem", "issue", "challeng", "difficult"]):
            return "problem"
        elif any(m in matches_lower for m in ["how do", "how can", "recommend", "advice"]):
            return "question"
        else:
            return "general"

    def collect(
        self,
        limit: int | None = 100,
        time_filter: str = "week",
        sort: str = "hot",
        **kwargs
    ) -> Iterator[Post]:
        """
        Collect posts from configured subreddits.

        Args:
            limit: Maximum number of posts to collect per subreddit.
            time_filter: Time filter for top/controversial (hour, day, week, month, year, all).
            sort: Sort method (hot, new, top, rising, controversial).

        Yields:
            Post objects matching the configured criteria.
        """
        reddit = self._get_reddit()
        collected = 0

        for subreddit_name in self.subreddits:
            logger.info(f"Collecting from r/{subreddit_name}...")

            try:
                subreddit = reddit.subreddit(subreddit_name)

                # Get submissions based on sort method
                if sort == "hot":
                    submissions = subreddit.hot(limit=limit)
                elif sort == "new":
                    submissions = subreddit.new(limit=limit)
                elif sort == "top":
                    submissions = subreddit.top(time_filter=time_filter, limit=limit)
                elif sort == "rising":
                    submissions = subreddit.rising(limit=limit)
                elif sort == "controversial":
                    submissions = subreddit.controversial(time_filter=time_filter, limit=limit)
                else:
                    submissions = subreddit.hot(limit=limit)

                for submission in submissions:
                    post = self._parse_submission(submission)
                    if post:
                        collected += 1
                        logger.debug(f"Collected post {collected}: {post.text[:50]}...")
                        yield post

            except Exception as e:
                logger.error(f"Error collecting from r/{subreddit_name}: {e}")
                continue

        logger.info(f"Collection complete. Total collected: {collected}")

    def collect_search(
        self,
        query: str,
        limit: int | None = 100,
        time_filter: str = "week",
        sort: str = "relevance",
        subreddits: list[str] | None = None,
        **kwargs
    ) -> Iterator[Post]:
        """
        Search for posts matching a query.

        Args:
            query: Search query string.
            limit: Maximum number of posts to collect.
            time_filter: Time filter (hour, day, week, month, year, all).
            sort: Sort method (relevance, hot, top, new, comments).
            subreddits: Specific subreddits to search in (None for all).

        Yields:
            Post objects matching the search query.
        """
        reddit = self._get_reddit()
        collected = 0

        # Build subreddit string
        if subreddits:
            subreddit_str = "+".join(subreddits)
        else:
            subreddit_str = "all"

        logger.info(f"Searching r/{subreddit_str} for: {query}")

        try:
            subreddit = reddit.subreddit(subreddit_str)
            submissions = subreddit.search(
                query,
                sort=sort,
                time_filter=time_filter,
                limit=limit,
            )

            for submission in submissions:
                post = self._parse_submission(submission)
                if post:
                    collected += 1
                    yield post

        except Exception as e:
            logger.error(f"Search error: {e}")

        logger.info(f"Search complete. Total collected: {collected}")

    def stop(self) -> None:
        """Clean up Reddit client."""
        self._reddit = None
