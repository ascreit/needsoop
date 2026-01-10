#!/usr/bin/env python3
"""
Reddit Collection Script (No API Key Required)

Collects posts from Reddit using public JSON endpoints.

Usage:
    python scripts/collect_reddit.py --limit 50
    python scripts/collect_reddit.py --subreddits indiehackers SaaS --limit 100
    python scripts/collect_reddit.py --search "frustrated with" --limit 50
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.collectors.reddit_simple import RedditSimpleCollector, DEFAULT_SUBREDDITS
from src.db.chroma import PostStore

console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)
logger = logging.getLogger(__name__)


def display_posts(posts: list, max_display: int = 20) -> None:
    """Display collected posts."""
    table = Table(title=f"Collected Posts ({len(posts)} total)")
    table.add_column("Subreddit", style="cyan", width=12)
    table.add_column("Score", style="green", width=6)
    table.add_column("Text", width=70)

    for post in posts[:max_display]:
        subreddit = post.metadata.get("subreddit", "?")
        score = str(post.likes)
        text = post.text[:100].replace("\n", " ") + "..."
        table.add_row(subreddit, score, text)

    console.print(table)

    if len(posts) > max_display:
        console.print(f"[dim]... and {len(posts) - max_display} more[/dim]")


def display_stats(posts: list) -> None:
    """Display statistics."""
    if not posts:
        console.print("[yellow]No posts collected.[/yellow]")
        return

    subreddit_counts = {}
    for post in posts:
        sr = post.metadata.get("subreddit", "unknown")
        subreddit_counts[sr] = subreddit_counts.get(sr, 0) + 1

    console.print("\n[bold]Statistics[/bold]")
    console.print(f"Total: {len(posts)}")

    console.print("\nBy subreddit:")
    for sr, count in sorted(subreddit_counts.items(), key=lambda x: -x[1]):
        console.print(f"  r/{sr}: {count}")


def main():
    parser = argparse.ArgumentParser(description="Collect posts from Reddit")

    parser.add_argument(
        "--subreddits", nargs="+", default=None,
        help=f"Subreddits (default: {', '.join(DEFAULT_SUBREDDITS[:3])}...)",
    )
    parser.add_argument(
        "--search", type=str, default=None,
        help="Search query",
    )
    parser.add_argument(
        "--limit", type=int, default=50,
        help="Max posts per subreddit (default: 50)",
    )
    parser.add_argument(
        "--sort", choices=["hot", "new", "top", "rising"], default="hot",
        help="Sort method (default: hot)",
    )
    parser.add_argument(
        "--min-score", type=int, default=1,
        help="Minimum score (default: 1)",
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="Don't save to database",
    )
    parser.add_argument(
        "--data-dir", type=Path,
        default=Path(__file__).parent.parent / "data",
        help="Data directory",
    )
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    collector = RedditSimpleCollector(
        subreddits=args.subreddits,
        min_score=args.min_score,
    )

    store = None
    if not args.no_save:
        store = PostStore(persist_directory=args.data_dir / "chroma", source="reddit")

    posts = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Collecting...", total=None)

        if args.search:
            iterator = collector.search(query=args.search, limit=args.limit, sort=args.sort)
        else:
            iterator = collector.collect(limit=args.limit, sort=args.sort)

        for post in iterator:
            posts.append(post)
            if store:
                store.add(post)
            progress.update(task, description=f"Collected {len(posts)} posts")

    display_posts(posts)
    display_stats(posts)

    if store:
        console.print(f"\n[green]Saved to {args.data_dir / 'chroma'}[/green]")


if __name__ == "__main__":
    main()
