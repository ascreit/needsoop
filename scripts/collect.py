#!/usr/bin/env python3
"""
NeedScoop Collection Script

Collects posts from Bluesky Firehose with minimal exclusion filtering
and stores them in ChromaDB.

Usage:
    python scripts/collect.py --limit 100
    python scripts/collect.py --duration 60
    python scripts/collect.py --stream
"""

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from src.collectors.bluesky import BlueskyCollector
from src.collectors.base import Post
from src.db.chroma import PostStore

console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)
logger = logging.getLogger(__name__)


class Collector:
    """Main collector class that orchestrates the collection process."""

    def __init__(
        self,
        data_dir: Path,
        min_length: int = 50,
        max_length: int = 1000,
        japanese_only: bool = False,
    ):
        """
        Initialize the collector.

        Args:
            data_dir: Directory for data storage.
            min_length: Minimum post length.
            max_length: Maximum post length.
            japanese_only: If True, only collect Japanese posts.
        """
        self.data_dir = data_dir

        logger.info("Initializing post store...")
        self.store = PostStore(persist_directory=data_dir / "chroma", source="bluesky")

        logger.info("Initializing Bluesky collector...")
        self.bluesky = BlueskyCollector(
            min_length=min_length,
            max_length=max_length,
            japanese_only=japanese_only,
        )

        self._running = False
        self._collected_count = 0

    def collect_batch(self, limit: int) -> int:
        """
        Collect a batch of posts up to the specified limit.

        Args:
            limit: Maximum number of posts to collect.

        Returns:
            Number of posts collected.
        """
        logger.info(f"Starting batch collection (limit: {limit})...")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Collecting posts...", total=limit)

            collected = 0
            for post in self.bluesky.collect(limit=limit):
                self.store.add(post)
                collected += 1
                progress.update(task, advance=1)

                if collected % 10 == 0:
                    progress.update(
                        task,
                        description=f"Collected {collected} posts",
                    )

        logger.info(f"Batch collection complete. Collected {collected} posts.")
        return collected

    def collect_duration(self, duration_seconds: int) -> int:
        """
        Collect posts for a specified duration.

        Args:
            duration_seconds: How long to collect in seconds.

        Returns:
            Number of posts collected.
        """
        logger.info(f"Starting timed collection ({duration_seconds}s)...")

        self._running = True
        self._collected_count = 0
        start_time = time.time()

        def on_post(post: Post) -> None:
            if not self._running:
                return

            self.store.add(post)
            self._collected_count += 1

            if self._collected_count % 10 == 0:
                elapsed = time.time() - start_time
                rate = self._collected_count / elapsed if elapsed > 0 else 0
                console.print(
                    f"[green]Collected {self._collected_count} posts "
                    f"({rate:.1f}/s)[/green]"
                )

            # Check if duration exceeded
            if time.time() - start_time >= duration_seconds:
                self._running = False
                self.bluesky.stop()

        # Start streaming with timeout
        try:
            self.bluesky.start_streaming(on_post)
        except Exception as e:
            if self._running:
                logger.error(f"Collection error: {e}")

        logger.info(f"Timed collection complete. Collected {self._collected_count} posts.")
        return self._collected_count

    def collect_stream(self) -> None:
        """
        Start continuous streaming collection.

        Runs until interrupted (Ctrl+C).
        """
        logger.info("Starting continuous stream collection...")
        logger.info("Press Ctrl+C to stop.")

        self._running = True
        self._collected_count = 0
        start_time = time.time()

        def on_post(post: Post) -> None:
            if not self._running:
                return

            self.store.add(post)
            self._collected_count += 1

            if self._collected_count % 10 == 0:
                elapsed = time.time() - start_time
                rate = self._collected_count / elapsed if elapsed > 0 else 0
                console.print(
                    f"[green]Collected {self._collected_count} posts "
                    f"({rate:.1f}/s) - {post.text[:50]}...[/green]"
                )

        def signal_handler(signum, frame):
            console.print("\n[yellow]Stopping collection...[/yellow]")
            self._running = False
            self.bluesky.stop()

        # Set up signal handler for graceful shutdown
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            self.bluesky.start_streaming(on_post)
        except Exception as e:
            if self._running:
                logger.error(f"Collection error: {e}")

        logger.info(f"Stream collection stopped. Total collected: {self._collected_count}")

    def show_stats(self) -> None:
        """Display collection statistics."""
        total = self.store.count()
        by_type = self.store.count_by_signal_type()

        console.print("\n[bold]Collection Statistics[/bold]")
        console.print(f"Total posts: {total}")
        console.print("\nBy signal type:")
        for signal_type, count in sorted(by_type.items(), key=lambda x: -x[1]):
            console.print(f"  {signal_type}: {count}")


def main():
    parser = argparse.ArgumentParser(
        description="Collect posts from Bluesky Firehose",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Collect up to this many posts, then stop",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Collect for this many seconds, then stop",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Run continuously until interrupted",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).parent.parent / "data",
        help="Directory for data storage",
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=50,
        help="Minimum post length (default: 50)",
    )
    parser.add_argument(
        "--japanese-only",
        action="store_true",
        help="Only collect Japanese posts",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show collection statistics and exit",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Initialize collector
    collector = Collector(
        data_dir=args.data_dir,
        min_length=args.min_length,
        japanese_only=args.japanese_only,
    )

    if args.stats:
        collector.show_stats()
        return

    # Determine collection mode
    if args.stream:
        collector.collect_stream()
    elif args.duration:
        collector.collect_duration(args.duration)
    elif args.limit:
        collector.collect_batch(args.limit)
    else:
        # Default: collect 100 posts
        console.print("[yellow]No mode specified. Collecting 100 posts...[/yellow]")
        collector.collect_batch(100)

    collector.show_stats()


if __name__ == "__main__":
    main()
