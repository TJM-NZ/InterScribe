import { describe, it, expect, vi, beforeEach } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

import {
  getCondensationHeadlines,
  logCondensationCorrection,
  confirmCondensationReview,
  type QuoteType,
} from "../lib/api";

beforeEach(() => {
  mockFetch.mockReset();
});

const MOCK_HEADLINE_QUOTE = {
  id: "q1",
  video_id: "v1",
  start_segment_id: 2,
  end_segment_id: 5,
  start_ts: 12.5,
  end_ts: 28.0,
  quote_text: "We found that the AI approach scaled well beyond all of our initial expectations.",
  headline_text: "AI scales beyond expectations.",
  speaker_label: "SPEAKER_01",
  quote_type: "headline" as QuoteType,
  narrative_alignment_score: 0.87,
  is_notable_moment: false,
  notable_moment_id: null,
  source_candidate_ids: ["cand-1"],
  reviewed: false,
};

describe("getCondensationHeadlines", () => {
  it("fetches headline quotes and returns them", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ quotes: [MOCK_HEADLINE_QUOTE] }),
    });

    const result = await getCondensationHeadlines("v1");

    expect(result.quotes).toHaveLength(1);
    expect(result.quotes[0].quote_type).toBe("headline");
    expect(result.quotes[0].headline_text).toBe("AI scales beyond expectations.");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/videos/v1/condensation/headlines")
    );
  });

  it("returns headline_text field on each quote", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ quotes: [MOCK_HEADLINE_QUOTE] }),
    });

    const result = await getCondensationHeadlines("v1");

    expect("headline_text" in result.quotes[0]).toBe(true);
    expect(result.quotes[0].headline_text).not.toBeNull();
  });

  it("throws 409 when condensation not yet ready", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({
        detail: {
          error: "Condensation not yet available",
          code: "CONDENSATION_NOT_READY",
          trace_id: "t1",
        },
      }),
    });

    await expect(getCondensationHeadlines("v1")).rejects.toMatchObject({
      detail: { code: "CONDENSATION_NOT_READY" },
    });
  });

  it("throws 404 when video not found", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({
        detail: { error: "Video not found", code: "NOT_FOUND", trace_id: "t2" },
      }),
    });

    await expect(getCondensationHeadlines("bad-id")).rejects.toMatchObject({
      detail: { code: "NOT_FOUND" },
    });
  });
});

describe("logCondensationCorrection", () => {
  it("posts headline edit correction and returns correction_id", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ correction_id: "corr-1" }),
    });

    const result = await logCondensationCorrection("v1", {
      entity_type: "headline_condensation",
      entity_id: "q1",
      field_name: "headline_text",
      original_value: { headline_text: "AI scales beyond expectations." },
      corrected_value: { headline_text: "AI exceeds all expectations." },
      reason_category: "model_error",
      reason_note: "Better wording",
    });

    expect(result.correction_id).toBe("corr-1");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/videos/v1/condensation/corrections"),
      expect.objectContaining({ method: "POST" })
    );
  });

  it("sends correct entity_type in body", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ correction_id: "corr-2" }),
    });

    await logCondensationCorrection("v1", {
      entity_type: "headline_condensation",
      entity_id: "q1",
      field_name: "headline_text",
      original_value: null,
      corrected_value: { headline_text: "Updated." },
      reason_category: "preference",
      reason_note: null,
    });

    const call = mockFetch.mock.calls[0];
    const body = JSON.parse(call[1].body);
    expect(body.entity_type).toBe("headline_condensation");
    expect(body.field_name).toBe("headline_text");
    expect(body.reason_category).toBe("preference");
  });

  it("posts quote_type downgrade with correct field", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ correction_id: "corr-3" }),
    });

    await logCondensationCorrection("v1", {
      entity_type: "headline_condensation",
      entity_id: "q1",
      field_name: "quote_type",
      original_value: { quote_type: "headline" },
      corrected_value: { quote_type: "substantive" },
      reason_category: "model_error",
      reason_note: null,
    });

    const call = mockFetch.mock.calls[0];
    const body = JSON.parse(call[1].body);
    expect(body.field_name).toBe("quote_type");
    expect(body.corrected_value).toEqual({ quote_type: "substantive" });
  });

  it("throws 409 when condensation already reviewed", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({
        detail: {
          error: "Condensation review already confirmed",
          code: "CONDENSATION_ALREADY_REVIEWED",
          trace_id: "t3",
        },
      }),
    });

    await expect(
      logCondensationCorrection("v1", {
        entity_type: "headline_condensation",
        entity_id: "q1",
        field_name: "headline_text",
        original_value: null,
        corrected_value: { headline_text: "text" },
        reason_category: "preference",
        reason_note: null,
      })
    ).rejects.toMatchObject({ detail: { code: "CONDENSATION_ALREADY_REVIEWED" } });
  });

  it("throws 400 when entity does not belong to this video or is not headline", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({
        detail: {
          error: "entity_id does not belong to this video or is not a headline quote",
          code: "INVALID_ENTITY",
          trace_id: "t4",
        },
      }),
    });

    await expect(
      logCondensationCorrection("v1", {
        entity_type: "headline_condensation",
        entity_id: "other-video-quote",
        field_name: "headline_text",
        original_value: null,
        corrected_value: { headline_text: "text" },
        reason_category: "model_error",
        reason_note: null,
      })
    ).rejects.toMatchObject({ detail: { code: "INVALID_ENTITY" } });
  });
});

describe("confirmCondensationReview", () => {
  it("posts and returns condensation_reviewed status", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ video_id: "v1", status: "condensation_reviewed" }),
    });

    const result = await confirmCondensationReview("v1");

    expect(result.status).toBe("condensation_reviewed");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/videos/v1/condensation/confirm-review"),
      expect.objectContaining({ method: "POST" })
    );
  });

  it("throws 409 when status is not condensation_ready_for_review", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({
        detail: {
          error: "Video not at condensation_ready_for_review",
          code: "CONDENSATION_NOT_READY",
          trace_id: "t5",
        },
      }),
    });

    await expect(confirmCondensationReview("v1")).rejects.toMatchObject({
      detail: { code: "CONDENSATION_NOT_READY" },
    });
  });

  it("throws 404 when video not found", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({
        detail: { error: "Video not found", code: "NOT_FOUND", trace_id: "t6" },
      }),
    });

    await expect(confirmCondensationReview("bad-id")).rejects.toMatchObject({
      detail: { code: "NOT_FOUND" },
    });
  });
});

describe("Quote type includes headline_text (SPEC-004)", () => {
  it("Quote shape includes headline_text field", async () => {
    const quoteWithNull = { ...MOCK_HEADLINE_QUOTE, headline_text: null };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ quotes: [quoteWithNull] }),
    });

    const result = await getCondensationHeadlines("v1");

    expect("headline_text" in result.quotes[0]).toBe(true);
    expect(result.quotes[0].headline_text).toBeNull();
  });

  it("headline_text can be a string", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ quotes: [MOCK_HEADLINE_QUOTE] }),
    });

    const result = await getCondensationHeadlines("v1");

    expect(typeof result.quotes[0].headline_text).toBe("string");
  });
});
