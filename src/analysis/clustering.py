"""
Clustering analysis using UMAP and HDBSCAN.

Reduces embedding dimensions with UMAP and clusters similar posts with HDBSCAN.
"""

import logging
from dataclasses import dataclass

import hdbscan
import numpy as np
import umap

logger = logging.getLogger(__name__)


@dataclass
class ClusterResult:
    """Result of clustering analysis."""

    labels: np.ndarray  # Cluster labels (-1 = noise)
    reduced_embeddings: np.ndarray  # 2D embeddings for visualization
    n_clusters: int  # Number of clusters (excluding noise)
    n_noise: int  # Number of noise points
    cluster_sizes: dict[int, int]  # Cluster ID -> count


class PostClusterer:
    """
    Clusters posts based on their embeddings.

    Uses UMAP for dimension reduction and HDBSCAN for density-based clustering.
    """

    def __init__(
        self,
        # UMAP parameters
        umap_n_components: int = 50,
        umap_n_neighbors: int = 15,
        umap_min_dist: float = 0.1,
        umap_metric: str = "cosine",
        # HDBSCAN parameters
        min_cluster_size: int = 10,
        min_samples: int = 5,
        cluster_selection_epsilon: float = 0.5,
        # Visualization
        vis_n_components: int = 2,
    ):
        """
        Initialize the clusterer.

        Args:
            umap_n_components: Target dimensions for UMAP reduction.
            umap_n_neighbors: UMAP neighborhood size.
            umap_min_dist: UMAP minimum distance between points.
            umap_metric: Distance metric for UMAP.
            min_cluster_size: Minimum points to form a cluster.
            min_samples: HDBSCAN core point threshold.
            cluster_selection_epsilon: HDBSCAN cluster selection threshold.
            vis_n_components: Dimensions for visualization (usually 2).
        """
        self.umap_n_components = umap_n_components
        self.umap_n_neighbors = umap_n_neighbors
        self.umap_min_dist = umap_min_dist
        self.umap_metric = umap_metric
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.cluster_selection_epsilon = cluster_selection_epsilon
        self.vis_n_components = vis_n_components

        self._umap_reducer: umap.UMAP | None = None
        self._umap_vis: umap.UMAP | None = None
        self._clusterer: hdbscan.HDBSCAN | None = None

    def fit(self, embeddings: np.ndarray) -> ClusterResult:
        """
        Fit the clusterer and return results.

        Args:
            embeddings: Array of shape (n_samples, n_features).

        Returns:
            ClusterResult with labels and reduced embeddings.
        """
        n_samples = len(embeddings)
        logger.info(f"Clustering {n_samples} embeddings...")

        # Adjust parameters for small datasets
        effective_n_neighbors = min(self.umap_n_neighbors, n_samples - 1)
        effective_min_cluster_size = min(self.min_cluster_size, max(2, n_samples // 10))
        effective_min_samples = min(self.min_samples, effective_min_cluster_size - 1)

        # Step 1: Reduce dimensions with UMAP (for clustering)
        logger.info(f"UMAP reduction: {embeddings.shape[1]}D -> {self.umap_n_components}D")
        self._umap_reducer = umap.UMAP(
            n_components=min(self.umap_n_components, n_samples - 2),
            n_neighbors=effective_n_neighbors,
            min_dist=self.umap_min_dist,
            metric=self.umap_metric,
            random_state=42,
        )
        reduced = self._umap_reducer.fit_transform(embeddings)

        # Step 2: Cluster with HDBSCAN
        logger.info(
            f"HDBSCAN clustering (min_cluster_size={effective_min_cluster_size}, "
            f"min_samples={effective_min_samples})"
        )
        self._clusterer = hdbscan.HDBSCAN(
            min_cluster_size=effective_min_cluster_size,
            min_samples=effective_min_samples,
            cluster_selection_epsilon=self.cluster_selection_epsilon,
            metric="euclidean",
        )
        labels = self._clusterer.fit_predict(reduced)

        # Step 3: Create 2D embeddings for visualization
        logger.info(f"UMAP reduction for visualization: -> {self.vis_n_components}D")
        self._umap_vis = umap.UMAP(
            n_components=self.vis_n_components,
            n_neighbors=effective_n_neighbors,
            min_dist=self.umap_min_dist,
            metric=self.umap_metric,
            random_state=42,
        )
        vis_embeddings = self._umap_vis.fit_transform(embeddings)

        # Calculate statistics
        unique_labels = set(labels)
        n_clusters = len(unique_labels - {-1})
        n_noise = np.sum(labels == -1)

        cluster_sizes = {}
        for label in unique_labels:
            cluster_sizes[int(label)] = int(np.sum(labels == label))

        logger.info(f"Found {n_clusters} clusters, {n_noise} noise points")

        return ClusterResult(
            labels=labels,
            reduced_embeddings=vis_embeddings,
            n_clusters=n_clusters,
            n_noise=n_noise,
            cluster_sizes=cluster_sizes,
        )

    def get_cluster_summary(
        self,
        labels: np.ndarray,
        texts: list[str],
        top_n: int = 5,
    ) -> dict[int, dict]:
        """
        Get summary information for each cluster.

        Args:
            labels: Cluster labels from fit().
            texts: Original texts corresponding to labels.
            top_n: Number of sample texts per cluster.

        Returns:
            Dictionary mapping cluster ID to summary info.
        """
        summaries = {}

        for cluster_id in set(labels):
            if cluster_id == -1:
                continue  # Skip noise

            mask = labels == cluster_id
            cluster_texts = [t for t, m in zip(texts, mask) if m]

            # Get sample texts (shortest ones are often most focused)
            sorted_texts = sorted(cluster_texts, key=len)
            samples = sorted_texts[:top_n]

            summaries[int(cluster_id)] = {
                "size": len(cluster_texts),
                "sample_texts": samples,
            }

        return summaries
