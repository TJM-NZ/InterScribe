"""MiniLM embedding + agglomerative clustering for ChunkTheme rows.

Implements NARRATIVE_CLUSTER anchor from SPEC-002:
- all-MiniLM-L6-v2 embeddings run on CPU (hard constraint)
- cosine-distance agglomerative clustering
- rank = cluster_size descending, ties broken by earliest chunk_index
- representative_label derived deterministically from member theme tags
"""
import logging
from collections import Counter

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering
from sqlalchemy.orm import Session

from app.config import settings
from app.models.phase1 import ChunkTheme, NarrativeCluster, TranscriptChunk

logger = logging.getLogger(__name__)


def load_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(
        "all-MiniLM-L6-v2",
        device="cpu",
        cache_folder=settings.hf_home,
    )


def _build_embedding_text(theme: ChunkTheme) -> str:
    tags = " ".join(theme.topic_tags) if theme.topic_tags else ""
    return f"{theme.topic_focus} {tags}"


def _representative_label(themes: list[ChunkTheme]) -> str:
    all_tags: list[str] = []
    for t in themes:
        all_tags.extend(t.topic_tags or [])
    top_tags = [tag for tag, _ in Counter(all_tags).most_common(5)]
    tag_str = ", ".join(top_tags) if top_tags else ""
    # Lead with a truncated focus from the first theme as the cluster headline
    focus = themes[0].topic_focus.split(".")[0] if themes else "unknown"
    return focus + (f": {tag_str}" if tag_str else "")


def cluster_themes(
    video_id,
    themes: list[ChunkTheme],
    chunk_map: dict,  # chunk_id -> TranscriptChunk
    model: SentenceTransformer,
    db: Session,
) -> None:
    """Embed themes, cluster, create NarrativeCluster rows, update cluster_id."""
    if not themes:
        return

    texts = [_build_embedding_text(t) for t in themes]
    embeddings: np.ndarray = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

    for theme, emb in zip(themes, embeddings):
        theme.theme_embedding = emb.tolist()

    if len(themes) == 1:
        labels = np.array([0])
    else:
        clf = AgglomerativeClustering(
            n_clusters=None,
            metric="cosine",
            linkage="average",
            distance_threshold=settings.narrative_cluster_threshold,
            compute_full_tree=True,
        )
        labels = clf.fit_predict(embeddings)

    clusters: dict[int, list[ChunkTheme]] = {}
    cluster_min_chunk: dict[int, int] = {}
    for theme, label in zip(themes, labels):
        label = int(label)
        clusters.setdefault(label, []).append(theme)
        chunk = chunk_map.get(str(theme.chunk_id))
        chunk_idx = chunk.chunk_index if chunk else 0
        cluster_min_chunk[label] = min(cluster_min_chunk.get(label, chunk_idx), chunk_idx)

    sorted_labels = sorted(
        clusters.keys(),
        key=lambda lbl: (-len(clusters[lbl]), cluster_min_chunk[lbl]),
    )

    for rank, label in enumerate(sorted_labels, start=1):
        members = clusters[label]
        cluster = NarrativeCluster(
            video_id=video_id,
            representative_label=_representative_label(members),
            cluster_size=len(members),
            rank=rank,
        )
        db.add(cluster)
        db.flush()
        for theme in members:
            theme.cluster_id = cluster.id

    db.flush()
