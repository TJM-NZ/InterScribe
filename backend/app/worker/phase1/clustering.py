"""MiniLM embedding + agglomerative clustering for ChunkNarrative rows.

Implements NARRATIVE_CLUSTER anchor from SPEC-002:
- all-MiniLM-L6-v2 embeddings run on CPU (hard constraint)
- cosine-distance agglomerative clustering
- rank = cluster_size descending, ties broken by earliest chunk_index
- representative_label derived deterministically from member domains/tones/tags
"""
import logging
import uuid
from collections import Counter

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering
from sqlalchemy.orm import Session

from app.config import settings
from app.models.phase1 import ChunkNarrative, NarrativeCluster, TranscriptChunk

logger = logging.getLogger(__name__)


def load_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(
        "all-MiniLM-L6-v2",
        device="cpu",
        cache_folder=settings.hf_home,
    )


def _build_embedding_text(narrative: ChunkNarrative) -> str:
    tags = " ".join(narrative.topic_tags) if narrative.topic_tags else ""
    return f"{narrative.domain} {narrative.tone} {tags}"


def _representative_label(narratives: list[ChunkNarrative]) -> str:
    domain = Counter(n.domain for n in narratives).most_common(1)[0][0]
    tone = Counter(n.tone for n in narratives).most_common(1)[0][0]
    all_tags: list[str] = []
    for n in narratives:
        all_tags.extend(n.topic_tags or [])
    top_tags = [t for t, _ in Counter(all_tags).most_common(5)]
    tag_str = ", ".join(top_tags) if top_tags else ""
    return f"{domain} / {tone}" + (f": {tag_str}" if tag_str else "")


def cluster_narratives(
    video_id,
    narratives: list[ChunkNarrative],
    chunk_map: dict,  # chunk_id -> TranscriptChunk
    model: SentenceTransformer,
    db: Session,
) -> None:
    """Embed narratives, cluster, create NarrativeCluster rows, update cluster_id."""
    if not narratives:
        return

    texts = [_build_embedding_text(n) for n in narratives]
    embeddings: np.ndarray = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

    # Persist embeddings
    for narrative, emb in zip(narratives, embeddings):
        narrative.narrative_embedding = emb.tolist()

    if len(narratives) == 1:
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

    # Group by label; track earliest chunk_index per cluster
    clusters: dict[int, list[ChunkNarrative]] = {}
    cluster_min_chunk: dict[int, int] = {}
    for narrative, label in zip(narratives, labels):
        label = int(label)
        clusters.setdefault(label, []).append(narrative)
        chunk = chunk_map.get(str(narrative.chunk_id))
        chunk_idx = chunk.chunk_index if chunk else 0
        cluster_min_chunk[label] = min(cluster_min_chunk.get(label, chunk_idx), chunk_idx)

    # Sort: cluster_size desc, then min_chunk_index asc
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
        for narrative in members:
            narrative.cluster_id = cluster.id

    db.flush()
