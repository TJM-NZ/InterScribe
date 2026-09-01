# ADR-001 — Quote Type Classification: Headline vs. Substantive

**Status:** Accepted
**Date:** 2026-07-19
**Amends:** SPEC-003 (Phase 2 quote extraction)
**Implemented by:** SPEC-003-FIX-001

---

## Context

SPEC-003 produces `Quote` rows from transcript segments, scored by narrative alignment and filtered to interviewee-only content. The quote text is a flat concatenation of segments — there is no distinction in kind between quotes.

In practice, not all quotable passages serve the same editorial purpose. A short, punchy statement can stand alone on a front cover or social post. A longer passage that traces an argument or tells a story is valuable for embedding in a video or article body, but needs surrounding context to land. Treating both as interchangeable in the review UI discards editorial signal that the downstream editor will have to reconstruct manually.

The required distinction:

| Type | Definition | Typical use |
|---|---|---|
| **Headline** | Self-contained, punchy, ≤ ~25 words. Communicates a complete idea without surrounding context. | Front cover, pull quote, social card, chapter title |
| **Substantive** | Longer, contextually rich. Requires the surrounding narrative to land fully. | Article body, video overlay, in-depth feature |

---

## Decision

Classify each quote candidate as `headline` or `substantive` **at Qwen extraction time**, by adding a `"type"` field to the existing per-candidate JSON output.

The classification is performed in the same Qwen call that identifies the segment ID range. No second model call is introduced.

---

## Rationale

### Why at extraction time, not post-hoc

Headline vs. substantive is a semantic judgment about a passage's **relationship to its context** — whether it is self-contained or context-dependent. That judgment requires:

1. The passage itself
2. The surrounding exchange (what the interviewer asked, what came before and after)
3. The dominant narrative themes the passage is being evaluated against

All three are present in the extraction prompt. They are not recoverable from the assembled `quote_text` alone.

A post-hoc rule applied after grounding (after the quote is assembled from raw segment text) can only see the text. It cannot know whether that text is preceded by a question that makes it coherent, or whether it stands alone.

### Why Qwen, not a word-count rule

The simplest alternative would be: `len(quote_text.split()) <= 25 → headline`. This is rejected because:

- **Length ≠ punchy.** A 12-word fragment can be deeply context-dependent ("Yeah, exactly what he said the week before."). A 40-word sentence can be a complete, standalone claim.
- **The threshold is arbitrary.** Any fixed word count would require tuning per interview style and domain.
- **It encodes the wrong thing.** The goal is editorial usefulness, not string length.

Word count is included in the headline definition in the Qwen prompt as a heuristic signal (*"typically ≤ ~25 words"*) — not as a classification rule. The model uses it alongside semantic judgment.

### Why not a second Qwen call (post-grounding classifier)

A second call — after quote text is assembled — would classify on the text alone without conversational framing. It would also double the Qwen calls per video, add latency to an already-sequential batch job, and complicate the pipeline without proportionate benefit over the single-call approach.

### Why the "no quote text from Qwen" constraint is not violated

SPEC-003's hard constraint is: *"Qwen never outputs quote text or timestamps directly — it references TranscriptTurn/segment ID ranges only."*

This constraint exists to prevent model hallucination of content: Qwen might confabulate plausible-sounding text that does not match the actual transcript, producing a quote that is subtly wrong and hard to catch. Text must be assembled deterministically from stored `TranscriptSegment` rows.

A `"type": "headline"` label is not quote content. It is a semantic category about the candidate's editorial role. Outputting it does not risk confabulation of transcript text. The constraint is not violated.

---

## Alternatives Considered

### A. Rule-based (word count threshold)

- **Rejected.** Does not capture editorial usefulness. A short quote is not automatically headline-worthy; a long quote is not automatically substantive.

### B. Post-hoc second Qwen call (classify assembled text)

- **Rejected.** Loses conversational context. Doubles Qwen calls. Higher latency with no material accuracy gain.

### C. Post-hoc MiniLM similarity to predefined headline/substantive embeddings

- **Rejected.** Would require curating labelled examples per domain and per interview style. Adds a classification model to the pipeline. Overkill for what is already a good fit for the extraction-time Qwen call.

### D. User assigns type manually in review UI (no automatic classification)

- **Rejected for the default path.** Adds friction to review without a clear win. The model's classification is useful as a default; the review UI already supports corrections via the Correction table — a user who disagrees can log a correction. Manual-only classification would be appropriate as a fallback if Qwen's accuracy proves poor over time.

---

## Consequences

### What changes

- `QuoteCandidate` and `Quote` gain a `quote_type VARCHAR NOT NULL DEFAULT 'substantive'` column (migration 007).
- Qwen extraction prompt updated to require `"type": "headline" | "substantive"` in each candidate object.
- `_validate_candidates` parses `quote_type`; defaults to `"substantive"` if absent or unrecognised.
- Dedup promotion: canonical candidate's `quote_type` copied to the promoted `Quote` row.
- GET /api/videos/{id}/phase2/quotes gains an optional `type` query param filter.
- Phase 2 review UI: QuoteCard gains a type badge; a type filter is available.

### What does not change

- The grounding validity checks (interviewee-only, single-speaker range) are unchanged.
- `narrative_alignment_score` and `is_notable_moment` fields are unchanged.
- No new model is introduced. No GPU allocation changes.
- The dedup merge logic (segment overlap ratio + text similarity) is unchanged.
- Existing `Quote` and `QuoteCandidate` rows backfill to `'substantive'` — no re-extraction needed.

### Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Qwen misclassifies a substantive quote as headline | Medium | Default to "substantive" on missing/invalid output; users can log corrections via existing Correction flow |
| Headline threshold ("~25 words") feels too rigid in practice | Low | It is a heuristic in the prompt, not a hard rule — Qwen weighs semantic context, not just word count |
| Review UI type filter adds complexity without editorial payoff | Low | Filter is additive and optional; existing view= param behaviour unchanged |

---

## Review Notes

- This decision supersedes any implicit assumption in SPEC-003 that all quotes are editorially equivalent.
- If Qwen's headline/substantive accuracy proves systematically poor on a specific interview style, the prompt definition (in `_USER_TEMPLATE`) is the first thing to tune — not the model or the pipeline.
- Spec 4's correction-learning loop will eventually have access to `Correction` rows with `entity_type = "quote"` and `field_name = "quote_type"` — this is the natural feedback signal for improving classification over time.
