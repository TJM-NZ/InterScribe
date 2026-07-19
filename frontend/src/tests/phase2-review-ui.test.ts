import { describe, it, expect, vi, beforeEach } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

import {
  getPhase2Quotes,
  logPhase2Correction,
  confirmPhase2Review,
  type QuoteType,
} from "../lib/api";

beforeEach(() => {
  mockFetch.mockReset();
});

const MOCK_QUOTE = {
  id: "q1",
  video_id: "v1",
  start_segment_id: 2,
  end_segment_id: 5,
  start_ts: 12.5,
  end_ts: 28.0,
  quote_text: "We found that the approach scaled well beyond expectations.",
  speaker_label: "SPEAKER_01",
  quote_type: "substantive" as QuoteType,
  narrative_alignment_score: 0.87,
  is_notable_moment: false,
  notable_moment_id: null,
  source_candidate_ids: ["cand-1"],
  reviewed: false,
};

const MOCK_NOTABLE_QUOTE = {
  ...MOCK_QUOTE,
  id: "q2",
  is_notable_moment: true,
  notable_moment_id: "m1",
  narrative_alignment_score: 0.92,
};

describe("getPhase2Quotes", () => {
  it("fetches top quotes and returns them sorted by score", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ quotes: [MOCK_NOTABLE_QUOTE, MOCK_QUOTE] }),
    });

    const result = await getPhase2Quotes("v1", "top");

    expect(result.quotes).toHaveLength(2);
    expect(result.quotes[0].id).toBe("q2");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/videos/v1/phase2/quotes?view=top")
    );
  });

  it("fetches notable quotes with view=notable param", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ quotes: [MOCK_NOTABLE_QUOTE] }),
    });

    const result = await getPhase2Quotes("v1", "notable");

    expect(result.quotes).toHaveLength(1);
    expect(result.quotes[0].is_notable_moment).toBe(true);
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("view=notable")
    );
  });

  it("appends limit param when provided", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ quotes: [MOCK_QUOTE] }),
    });

    await getPhase2Quotes("v1", "top", 5);

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("limit=5")
    );
  });

  it("throws 409 when phase2 not yet ready", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({
        detail: { error: "Phase 2 quotes not yet available", code: "PHASE2_NOT_READY", trace_id: "t1" },
      }),
    });

    await expect(getPhase2Quotes("v1", "top")).rejects.toMatchObject({
      detail: { code: "PHASE2_NOT_READY" },
    });
  });

  it("throws 400 when view param is invalid", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({
        detail: { error: "view must be 'notable' or 'top'", code: "INVALID_VIEW", trace_id: "t2" },
      }),
    });

    await expect(getPhase2Quotes("v1", "top")).rejects.toMatchObject({
      detail: { code: "INVALID_VIEW" },
    });
  });

  it("throws 404 when video not found", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({
        detail: { error: "Video not found", code: "NOT_FOUND", trace_id: "t3" },
      }),
    });

    await expect(getPhase2Quotes("bad-id", "top")).rejects.toMatchObject({
      detail: { code: "NOT_FOUND" },
    });
  });
});

describe("logPhase2Correction", () => {
  it("posts quote rejection and returns correction_id", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ correction_id: "corr-1" }),
    });

    const result = await logPhase2Correction("v1", {
      entity_type: "quote",
      entity_id: "q1",
      field_name: null,
      original_value: { quote_text: "We found that the approach scaled well." },
      corrected_value: null,
      reason_category: "model_error",
      reason_note: "Quote is out of context",
    });

    expect(result.correction_id).toBe("corr-1");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/videos/v1/phase2/corrections"),
      expect.objectContaining({ method: "POST" })
    );
  });

  it("sends the correct entity_type in the body", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ correction_id: "corr-2" }),
    });

    await logPhase2Correction("v1", {
      entity_type: "quote",
      entity_id: "q1",
      field_name: null,
      original_value: null,
      corrected_value: null,
      reason_category: "preference",
      reason_note: null,
    });

    const call = mockFetch.mock.calls[0];
    const body = JSON.parse(call[1].body);
    expect(body.entity_type).toBe("quote");
    expect(body.reason_category).toBe("preference");
  });

  it("throws 409 when phase2 already reviewed", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({
        detail: { error: "Phase 2 review already confirmed", code: "PHASE2_ALREADY_REVIEWED", trace_id: "t4" },
      }),
    });

    await expect(
      logPhase2Correction("v1", {
        entity_type: "quote",
        entity_id: "q1",
        field_name: null,
        original_value: null,
        corrected_value: null,
        reason_category: "preference",
        reason_note: null,
      })
    ).rejects.toMatchObject({ detail: { code: "PHASE2_ALREADY_REVIEWED" } });
  });

  it("throws 400 when entity does not belong to this video", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({
        detail: { error: "entity_id does not belong to this video", code: "INVALID_ENTITY", trace_id: "t5" },
      }),
    });

    await expect(
      logPhase2Correction("v1", {
        entity_type: "quote",
        entity_id: "other-video-quote",
        field_name: null,
        original_value: null,
        corrected_value: null,
        reason_category: "model_error",
        reason_note: null,
      })
    ).rejects.toMatchObject({ detail: { code: "INVALID_ENTITY" } });
  });
});

describe("quote_type field (SPEC-003-FIX-001)", () => {
  it("quote shape includes quote_type as 'headline' or 'substantive'", async () => {
    const headlineQuote = { ...MOCK_QUOTE, id: "q-hl", quote_type: "headline" as QuoteType };
    const substantiveQuote = { ...MOCK_QUOTE, id: "q-sub", quote_type: "substantive" as QuoteType };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ quotes: [headlineQuote, substantiveQuote] }),
    });

    const result = await getPhase2Quotes("v1", "top");

    expect(result.quotes[0].quote_type).toBe("headline");
    expect(result.quotes[1].quote_type).toBe("substantive");
  });

  it("appends type param to request URL when provided", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ quotes: [{ ...MOCK_QUOTE, quote_type: "headline" as QuoteType }] }),
    });

    await getPhase2Quotes("v1", "top", undefined, "headline");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("type=headline")
    );
  });

  it("does not append type param to URL when not provided", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ quotes: [MOCK_QUOTE] }),
    });

    await getPhase2Quotes("v1", "top");

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).not.toContain("type=");
  });

  it("appends both limit and type params when both provided", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ quotes: [] }),
    });

    await getPhase2Quotes("v1", "top", 5, "substantive");

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("limit=5");
    expect(calledUrl).toContain("type=substantive");
  });
});

describe("confirmPhase2Review", () => {
  it("posts and returns phase2_reviewed status", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ video_id: "v1", status: "phase2_reviewed" }),
    });

    const result = await confirmPhase2Review("v1");

    expect(result.status).toBe("phase2_reviewed");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/videos/v1/phase2/confirm-review"),
      expect.objectContaining({ method: "POST" })
    );
  });

  it("throws 409 when status is not phase2_ready_for_review", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({
        detail: { error: "Video not at phase2_ready_for_review", code: "PHASE2_NOT_READY", trace_id: "t6" },
      }),
    });

    await expect(confirmPhase2Review("v1")).rejects.toMatchObject({
      detail: { code: "PHASE2_NOT_READY" },
    });
  });

  it("throws 404 when video not found", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({
        detail: { error: "Video not found", code: "NOT_FOUND", trace_id: "t7" },
      }),
    });

    await expect(confirmPhase2Review("bad-id")).rejects.toMatchObject({
      detail: { code: "NOT_FOUND" },
    });
  });
});
