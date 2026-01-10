#!/usr/bin/env python3
"""
NeedScoop Analysis Script

Generates embeddings and clusters posts to discover patterns.
All processing is done locally without external APIs.

Usage:
    python scripts/analyze.py                    # Full analysis
    python scripts/analyze.py --embeddings-only  # Only generate embeddings
    python scripts/analyze.py --cluster-only     # Only run clustering
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from src.analysis.clustering import PostClusterer
from src.analysis.embeddings import EmbeddingGenerator
from src.db.chroma import PostStore

console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)
logger = logging.getLogger(__name__)


class Analyzer:
    """Main analyzer class that orchestrates embedding and clustering."""

    def __init__(self, data_dir: Path, source: str = "reddit"):
        """
        Initialize the analyzer.

        Args:
            data_dir: Directory for data storage.
            source: Data source to analyze (reddit, bluesky, etc.)
        """
        self.data_dir = data_dir
        self.source = source

        logger.info(f"Initializing post store for source: {source}...")
        self.store = PostStore(persist_directory=data_dir / "chroma", source=source)

    def generate_embeddings(self) -> int:
        """
        Generate embeddings for posts that don't have them.

        Returns:
            Number of embeddings generated.
        """
        # Get all posts
        posts = self.store.get_all()
        logger.info(f"Total posts: {len(posts)}")

        # Check which posts need embeddings
        existing_embeddings = self.store.get_embeddings()
        posts_needing_embeddings = [
            p for p in posts if p.id not in existing_embeddings
        ]

        if not posts_needing_embeddings:
            logger.info("All posts already have embeddings.")
            return 0

        logger.info(f"Generating embeddings for {len(posts_needing_embeddings)} posts...")

        # Initialize generator (local, no API)
        generator = EmbeddingGenerator()

        # Generate embeddings
        texts = [p.text for p in posts_needing_embeddings]
        embeddings_map = {}
        for idx, embedding in generator.generate_all(texts):
            post = posts_needing_embeddings[idx]
            embeddings_map[post.id] = embedding

        # Save to store (batch update)
        for post in posts_needing_embeddings:
            if post.id in embeddings_map:
                self.store.add(post, embedding=embeddings_map[post.id])

        logger.info(f"Generated {len(embeddings_map)} embeddings.")
        return len(embeddings_map)

    def run_clustering(self, min_cluster_size: int = 10) -> dict:
        """
        Run clustering on all posts with embeddings.

        Args:
            min_cluster_size: Minimum posts to form a cluster.

        Returns:
            Clustering results summary.
        """
        # Get all posts and embeddings
        posts = self.store.get_all()
        embeddings_dict = self.store.get_embeddings()

        # Filter to posts with embeddings
        posts_with_embeddings = [p for p in posts if p.id in embeddings_dict]

        if len(posts_with_embeddings) < min_cluster_size:
            logger.warning(
                f"Not enough posts with embeddings ({len(posts_with_embeddings)}) "
                f"for clustering (min: {min_cluster_size})"
            )
            return {"error": "Not enough data"}

        logger.info(f"Clustering {len(posts_with_embeddings)} posts...")

        # Prepare data
        post_ids = [p.id for p in posts_with_embeddings]
        texts = [p.text for p in posts_with_embeddings]
        embeddings = np.array([embeddings_dict[pid] for pid in post_ids])

        # Run clustering
        clusterer = PostClusterer(min_cluster_size=min_cluster_size)
        result = clusterer.fit(embeddings)

        # Update cluster assignments in store
        cluster_assignments = {
            post_ids[i]: int(result.labels[i]) for i in range(len(post_ids))
        }
        self.store.update_clusters(cluster_assignments)

        # Get cluster summaries
        summaries = clusterer.get_cluster_summary(result.labels, texts)

        # Save visualization data
        vis_data = {
            "post_ids": post_ids,
            "x": result.reduced_embeddings[:, 0].tolist(),
            "y": result.reduced_embeddings[:, 1].tolist(),
            "labels": result.labels.tolist(),
            "texts": texts,
        }
        vis_path = self.data_dir / "cluster_visualization.npz"
        np.savez(vis_path, **vis_data)
        logger.info(f"Saved visualization data to {vis_path}")

        return {
            "n_posts": len(posts_with_embeddings),
            "n_clusters": result.n_clusters,
            "n_noise": result.n_noise,
            "cluster_sizes": result.cluster_sizes,
            "summaries": summaries,
        }

    def show_results(self, results: dict) -> None:
        """Display clustering results."""
        if "error" in results:
            console.print(f"[red]Error: {results['error']}[/red]")
            return

        console.print(f"\n[bold]Clustering Results[/bold]")
        console.print(f"Total posts analyzed: {results['n_posts']}")
        console.print(f"Clusters found: {results['n_clusters']}")
        console.print(f"Noise points: {results['n_noise']}")

        # Cluster table
        table = Table(title="Clusters")
        table.add_column("Cluster", style="cyan")
        table.add_column("Size", style="green")
        table.add_column("Sample Text", style="white", max_width=60)

        # Sort by size (excluding noise)
        sorted_clusters = sorted(
            [(k, v) for k, v in results["cluster_sizes"].items() if k != -1],
            key=lambda x: -x[1],
        )

        for cluster_id, size in sorted_clusters[:15]:  # Top 15 clusters
            sample = ""
            if cluster_id in results.get("summaries", {}):
                samples = results["summaries"][cluster_id].get("sample_texts", [])
                if samples:
                    sample = samples[0][:57] + "..." if len(samples[0]) > 60 else samples[0]

            table.add_row(str(cluster_id), str(size), sample)

        console.print(table)

        if results["n_noise"] > 0:
            noise_pct = results["n_noise"] / results["n_posts"] * 100
            console.print(f"\n[dim]Noise: {results['n_noise']} posts ({noise_pct:.1f}%) didn't fit any cluster[/dim]")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze collected posts with embeddings and clustering (local processing)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--embeddings-only",
        action="store_true",
        help="Only generate embeddings, skip clustering",
    )
    parser.add_argument(
        "--cluster-only",
        action="store_true",
        help="Only run clustering (assumes embeddings exist)",
    )
    parser.add_argument(
        "--min-cluster-size",
        type=int,
        default=10,
        help="Minimum posts to form a cluster (default: 10)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).parent.parent / "data",
        help="Directory for data storage",
    )
    parser.add_argument(
        "--source",
        type=str,
        default="reddit",
        help="Data source to analyze (reddit, bluesky, etc.)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    analyzer = Analyzer(data_dir=args.data_dir, source=args.source)

    if args.cluster_only:
        results = analyzer.run_clustering(min_cluster_size=args.min_cluster_size)
        analyzer.show_results(results)
        return

    if args.embeddings_only:
        count = analyzer.generate_embeddings()
        console.print(f"\n[green]Generated {count} embeddings.[/green]")
        return

    # Full analysis
    console.print("[bold]Running full analysis (local processing)...[/bold]\n")

    # Step 1: Generate embeddings
    console.print("[cyan]Step 1: Generating embeddings[/cyan]")
    count = analyzer.generate_embeddings()

    # Step 2: Run clustering
    console.print("\n[cyan]Step 2: Running clustering[/cyan]")
    results = analyzer.run_clustering(min_cluster_size=args.min_cluster_size)
    analyzer.show_results(results)


if __name__ == "__main__":
    main()
