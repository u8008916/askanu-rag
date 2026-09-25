# V7 Day 3 final retrieval baseline

- Benchmark: `v7-day3-six-domain-holdout-v1`
- Measured at: `2026-09-25T12:12:59.730114+00:00`
- Holdout SHA-256: `13b061af57a6c2730dc7434f325996f0e2ce536ceddf00281545a89f58bf65b6`
- Queries: 24
- Corpus: 29 canonical records, 29 retrieval units, 29 real Gemini vectors
- Storage: isolated in-memory benchmark repository; no production DB

## Frozen pipeline

BM25 Top20 + Gemini dense Top20 -> RRF k=60 fused max20 -> conclusive hard-filter guard -> Cohere rerank-v4.0-fast Top5

## Quality metrics

- Recall@1: 92.3611%
- Recall@3: 100.0000%
- Recall@5: 100.0000%
- Pre-rerank Recall@10: 100.0000%
- Selected-evidence completeness@5: 100.0000%
- Selected-evidence precision proxy: 51.7857%
- Provenance preservation: 100.0000%
- Hard-constraint preservation: 100.0000%

## Latency

Local benchmark wall time; provider-call timings include network and provider processing.

| Stage | Samples | p50 ms | p95 ms | mean ms |
|---|---:|---:|---:|---:|
| corpus_indexing_total | 1 | 2522.792 | 2522.792 | 2522.792 |
| gemini_document_embedding_provider_call | 1 | 2521.274 | 2521.274 | 2521.274 |
| sparse_local | 24 | 0.089 | 0.158 | 0.094 |
| dense_total | 24 | 999.916 | 1892.928 | 1109.237 |
| gemini_query_embedding_provider_call | 24 | 999.576 | 1892.485 | 1108.859 |
| dense_local_compute | 24 | 0.392 | 0.597 | 0.378 |
| fusion_local | 24 | 0.095 | 0.155 | 0.108 |
| cohere_rerank_provider_call | 24 | 390.701 | 623.405 | 419.660 |
| cohere_rate_limit_wait | 24 | 4702.614 | 4792.640 | 4371.524 |
| selection_local_overhead | 24 | 0.057 | 0.075 | 0.061 |
| total_retrieval | 24 | 1417.185 | 2241.689 | 1529.160 |

## Failure taxonomy

- DATA: 4
- NONE: 20

Provider errors: none.
