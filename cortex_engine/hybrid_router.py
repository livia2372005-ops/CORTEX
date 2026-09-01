"""CORTEX Phase 14 Hybrid Retrieval Router."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .api import CortexAPI
from .indexer import CortexIndexer
from .models import Knowledge
from .retrieval_benchmark import (
    LEXICAL_SYNONYMS,
    BenchmarkQuery,
    SemanticVectorIndex,
    build_benchmark_dataset,
)
from .storage import CortexStorage


class RouterPolicy(str, Enum):
    POLICY_A_FTS_ONLY = "policy_a_fts_only"
    POLICY_B_ZERO_FALLBACK = "policy_b_zero_fallback"
    POLICY_C_WEAK_CONFIDENCE_FALLBACK = "policy_c_weak_confidence_fallback"
    POLICY_D_HYBRID_EXPAND_FALLBACK = "policy_d_hybrid_expand_fallback"


@dataclass
class RoutedSearchResult:
    id: str
    type: str
    title: str
    content: str
    status: Optional[str] = None
    supersedes: Optional[str] = None
    retrieval_source: Any = field(default_factory=list)  # str or List[str]
    provenance: Optional[Dict[str, Any]] = None
    backend_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HybridRetrievalRouter:
    """Deterministic Hybrid Retrieval Router coordinating FTS5, Lexical Expansion, and Embeddings."""

    def __init__(
        self,
        storage: CortexStorage,
        indexer: Optional[CortexIndexer] = None,
        vector_index: Optional[SemanticVectorIndex] = None,
    ):
        self.storage = storage
        self.indexer = indexer or CortexIndexer(storage=storage)
        self.vector_index = vector_index or SemanticVectorIndex(db_path=storage.indexes_dir / "vector.db")

    def _execute_fts(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Execute SQLite FTS5 search."""
        return self.indexer.search_knowledge(query=query, limit=limit)

    def _execute_lexical_expansion(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Execute FTS5 search with deterministic domain synonym expansion."""
        base_results = self.indexer.search_knowledge(query=query, limit=limit)
        words = re.findall(r"\b\w+\b", query.lower())
        synonym_queries: List[str] = []
        for w in words:
            if w in LEXICAL_SYNONYMS:
                synonym_queries.extend(LEXICAL_SYNONYMS[w])
            if w.endswith("s") and w[:-1] in LEXICAL_SYNONYMS:
                synonym_queries.extend(LEXICAL_SYNONYMS[w[:-1]])

        seen_ids = {r["id"] for r in base_results}
        merged_results = list(base_results)

        for syn in synonym_queries[:6]:
            if len(merged_results) >= limit:
                break
            syn_res = self.indexer.search_knowledge(query=syn, limit=limit)
            for r in syn_res:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    merged_results.append(r)
                    if len(merged_results) >= limit:
                        break

        return merged_results[:limit]

    def _execute_semantic(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Execute local dense n-gram embedding search."""
        return self.vector_index.search(query=query, limit=limit)

    def assess_lexical_confidence(self, query: str, fts_results: List[Dict[str, Any]]) -> str:
        """Deterministically assess whether lexical search results are strong or weak.
        
        Criteria for WEAK:
        1. 0 results returned.
        2. Fewer than 2 results for multi-word queries.
        3. Query terms do not match titles or content of top result (low term overlap).
        """
        if not fts_results:
            return "WEAK_EMPTY"

        q_words = set(re.findall(r"\b\w+\b", query.lower()))
        top_item = fts_results[0]
        top_text = f"{top_item.get('title', '')} {top_item.get('content', '')}".lower()
        top_words = set(re.findall(r"\b\w+\b", top_text))

        overlap = q_words.intersection(top_words)
        # If multi-word query has very low lexical overlap with top candidate
        if len(q_words) >= 3 and len(overlap) < 1:
            return "WEAK_LOW_OVERLAP"

        if len(fts_results) == 1 and len(q_words) >= 4 and len(overlap) < 2:
            return "WEAK_SPARSE"

        return "STRONG"

    def merge_candidates(
        self,
        primary_results: List[Dict[str, Any]],
        fallback_results: List[Dict[str, Any]],
        primary_source: str,
        fallback_source: str,
        limit: int = 10,
    ) -> List[RoutedSearchResult]:
        """Merge primary and fallback candidate records, deduplicating IDs while preserving dual provenance."""
        records_by_id: Dict[str, RoutedSearchResult] = {}

        # 1. Ingest primary results
        for idx, r in enumerate(primary_results):
            r_id = r["id"]
            records_by_id[r_id] = RoutedSearchResult(
                id=r_id,
                type=r.get("type", "knowledge"),
                title=r.get("title", ""),
                content=r.get("content", ""),
                status=r.get("status"),
                supersedes=r.get("supersedes"),
                retrieval_source=[primary_source],
                provenance=r.get("provenance"),
                backend_metadata={primary_source: {"rank": idx + 1}},
            )

        # 2. Ingest fallback results
        for idx, r in enumerate(fallback_results):
            r_id = r["id"]
            if r_id in records_by_id:
                # Merge provenance
                existing = records_by_id[r_id]
                if fallback_source not in existing.retrieval_source:
                    existing.retrieval_source.append(fallback_source)
                existing.backend_metadata[fallback_source] = {
                    "rank": idx + 1,
                    "similarity_score": r.get("similarity_score"),
                }
            else:
                records_by_id[r_id] = RoutedSearchResult(
                    id=r_id,
                    type=r.get("type", "knowledge"),
                    title=r.get("title", ""),
                    content=r.get("content", ""),
                    status=r.get("status"),
                    supersedes=r.get("supersedes"),
                    retrieval_source=[fallback_source],
                    provenance=r.get("provenance"),
                    backend_metadata={
                        fallback_source: {
                            "rank": idx + 1,
                            "similarity_score": r.get("similarity_score"),
                        }
                    },
                )

        merged_list = list(records_by_id.values())[:limit]
        # Normalize single retrieval sources to string for clean serialization if desired
        for item in merged_list:
            if isinstance(item.retrieval_source, list) and len(item.retrieval_source) == 1:
                item.retrieval_source = item.retrieval_source[0]

        return merged_list

    def search(
        self,
        query: str,
        policy: RouterPolicy = RouterPolicy.POLICY_D_HYBRID_EXPAND_FALLBACK,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Execute hybrid routed retrieval under the specified routing policy."""
        t0 = time.perf_counter()
        triggered_backends: List[str] = []
        routing_decision: str = "DIRECT"

        if policy == RouterPolicy.POLICY_A_FTS_ONLY:
            triggered_backends.append("fts")
            raw_fts = self._execute_fts(query, limit=limit)
            final_results = [
                RoutedSearchResult(
                    id=r["id"],
                    type=r.get("type", "knowledge"),
                    title=r.get("title", ""),
                    content=r.get("content", ""),
                    status=r.get("status"),
                    supersedes=r.get("supersedes"),
                    retrieval_source="fts",
                    provenance=r.get("provenance"),
                    backend_metadata={"fts": {"rank": idx + 1}},
                )
                for idx, r in enumerate(raw_fts)
            ]

        elif policy == RouterPolicy.POLICY_B_ZERO_FALLBACK:
            triggered_backends.append("fts")
            raw_fts = self._execute_fts(query, limit=limit)
            if len(raw_fts) == 0:
                routing_decision = "FALLBACK_ON_ZERO"
                triggered_backends.append("semantic")
                raw_semantic = self._execute_semantic(query, limit=limit)
                final_results = [
                    RoutedSearchResult(
                        id=r["id"],
                        type=r.get("type", "knowledge"),
                        title=r.get("title", ""),
                        content=r.get("content", ""),
                        status=r.get("status"),
                        supersedes=r.get("supersedes"),
                        retrieval_source="semantic",
                        provenance=r.get("provenance"),
                        backend_metadata={"semantic": {"rank": idx + 1, "similarity_score": r.get("similarity_score")}},
                    )
                    for idx, r in enumerate(raw_semantic)
                ]
            else:
                final_results = [
                    RoutedSearchResult(
                        id=r["id"],
                        type=r.get("type", "knowledge"),
                        title=r.get("title", ""),
                        content=r.get("content", ""),
                        status=r.get("status"),
                        supersedes=r.get("supersedes"),
                        retrieval_source="fts",
                        provenance=r.get("provenance"),
                        backend_metadata={"fts": {"rank": idx + 1}},
                    )
                    for idx, r in enumerate(raw_fts)
                ]

        elif policy == RouterPolicy.POLICY_C_WEAK_CONFIDENCE_FALLBACK:
            triggered_backends.append("fts")
            raw_fts = self._execute_fts(query, limit=limit)
            confidence = self.assess_lexical_confidence(query, raw_fts)

            if confidence != "STRONG":
                routing_decision = f"FALLBACK_ON_{confidence}"
                triggered_backends.append("semantic")
                raw_semantic = self._execute_semantic(query, limit=limit)
                final_results = self.merge_candidates(
                    primary_results=raw_fts,
                    fallback_results=raw_semantic,
                    primary_source="fts",
                    fallback_source="semantic",
                    limit=limit,
                )
            else:
                final_results = [
                    RoutedSearchResult(
                        id=r["id"],
                        type=r.get("type", "knowledge"),
                        title=r.get("title", ""),
                        content=r.get("content", ""),
                        status=r.get("status"),
                        supersedes=r.get("supersedes"),
                        retrieval_source="fts",
                        provenance=r.get("provenance"),
                        backend_metadata={"fts": {"rank": idx + 1}},
                    )
                    for idx, r in enumerate(raw_fts)
                ]

        elif policy == RouterPolicy.POLICY_D_HYBRID_EXPAND_FALLBACK:
            triggered_backends.append("lexical_expansion")
            raw_lex = self._execute_lexical_expansion(query, limit=limit)
            confidence = self.assess_lexical_confidence(query, raw_lex)

            if confidence != "STRONG":
                routing_decision = f"FALLBACK_ON_{confidence}"
                triggered_backends.append("semantic")
                raw_semantic = self._execute_semantic(query, limit=limit)
                final_results = self.merge_candidates(
                    primary_results=raw_lex,
                    fallback_results=raw_semantic,
                    primary_source="lexical_expansion",
                    fallback_source="semantic",
                    limit=limit,
                )
            else:
                final_results = [
                    RoutedSearchResult(
                        id=r["id"],
                        type=r.get("type", "knowledge"),
                        title=r.get("title", ""),
                        content=r.get("content", ""),
                        status=r.get("status"),
                        supersedes=r.get("supersedes"),
                        retrieval_source="lexical_expansion",
                        provenance=r.get("provenance"),
                        backend_metadata={"lexical_expansion": {"rank": idx + 1}},
                    )
                    for idx, r in enumerate(raw_lex)
                ]
        else:
            raise ValueError(f"Unknown router policy: {policy}")

        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        return {
            "query": query,
            "policy": policy.value,
            "routing_decision": routing_decision,
            "triggered_backends": triggered_backends,
            "latency_ms": latency_ms,
            "count": len(final_results),
            "results": [r.to_dict() for r in final_results],
        }
