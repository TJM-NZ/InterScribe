import { describe, it, expect, vi, beforeEach } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

import {
  getPhase1Narrative,
  logCorrection,
  confirmPhase1Review,
} from "../lib/api";

beforeEach(() => {
  mockFetch.mockReset();
});

const MOCK_NARRATIVE = {
  clusters: [
    { id: "c1", video_id: "v1", representative_label: "AI research / technical: ml, data", cluster_size: 3, rank: 1 },
    { id: "c2", video_id: "v1", representative_label: "Healthcare / formal: policy", cluster_size: 1, rank: 2 },
  ],
  notable_moments: [
    { id: "m1", video_id: "v1", chunk_id: "ch1", start_segment_id: 2, end_segment_id: 5, description: "Key insight about scaling", reviewed: false },
  ],
};

describe("getPhase1Narrative", () => {
  it("returns clusters ordered by rank and all notable moments", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => MOCK_NARRATIVE });

    const result = await getPhase1Narrative("v1");

    expect(result.clusters).toHaveLength(2);
    expect(result.clusters[0].rank).toBe(1);
    expect(result.clusters[1].rank).toBe(2);
    expect(result.notable_moments).toHaveLength(1);
    expect(result.notable_moments[0].reviewed).toBe(false);
    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining("/api/videos/v1/phase1/narrative"));
  });

  it("throws 409 when phase1 not ready", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: { error: "Phase 1 narrative not yet available", code: "PHASE1_NOT_READY", trace_id: "t1" } }),
    });

    await expect(getPhase1Narrative("v1")).rejects.toMatchObject({
      detail: { code: "PHASE1_NOT_READY" },
    });
  });
});

describe("logCorrection", () => {
  it("posts correction with all fields and returns correction_id", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ correction_id: "corr-1" }) });

    const result = await logCorrection("v1", {
      entity_type: "narrative_cluster",
      entity_id: "c1",
      field_name: "representative_label",
      original_value: { representative_label: "old" },
      corrected_value: { representative_label: "new" },
      reason_category: "model_error",
      reason_note: "The label was wrong",
    });

    expect(result.correction_id).toBe("corr-1");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/videos/v1/phase1/corrections"),
      expect.objectContaining({ method: "POST" })
    );
  });

  it("supports rejection (null corrected_value and field_name)", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ correction_id: "corr-2" }) });

    const result = await logCorrection("v1", {
      entity_type: "notable_moment",
      entity_id: "m1",
      field_name: null,
      original_value: { description: "A key insight" },
      corrected_value: null,
      reason_category: "edge_case",
      reason_note: null,
    });

    expect(result.correction_id).toBe("corr-2");
  });

  it("throws 400 when entity does not belong to video", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: { error: "entity_id does not belong to this video", code: "INVALID_ENTITY", trace_id: "t2" } }),
    });

    await expect(
      logCorrection("v1", {
        entity_type: "narrative_cluster",
        entity_id: "other-video-cluster",
        field_name: "representative_label",
        original_value: { representative_label: "x" },
        corrected_value: { representative_label: "y" },
        reason_category: "preference",
        reason_note: null,
      })
    ).rejects.toMatchObject({ detail: { code: "INVALID_ENTITY" } });
  });

  it("throws 409 when phase1 already reviewed", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: { error: "Phase 1 review already confirmed", code: "PHASE1_ALREADY_REVIEWED", trace_id: "t3" } }),
    });

    await expect(
      logCorrection("v1", {
        entity_type: "narrative_cluster",
        entity_id: "c1",
        field_name: null,
        original_value: null,
        corrected_value: null,
        reason_category: "preference",
        reason_note: null,
      })
    ).rejects.toMatchObject({ detail: { code: "PHASE1_ALREADY_REVIEWED" } });
  });
});

describe("confirmPhase1Review", () => {
  it("posts and returns phase1_reviewed status", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ video_id: "v1", status: "phase1_reviewed" }),
    });

    const result = await confirmPhase1Review("v1");

    expect(result.status).toBe("phase1_reviewed");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/videos/v1/phase1/confirm-review"),
      expect.objectContaining({ method: "POST" })
    );
  });

  it("throws 409 when status is not phase1_ready_for_review", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: { error: "not ready", code: "PHASE1_NOT_READY", trace_id: "t4" } }),
    });

    await expect(confirmPhase1Review("v1")).rejects.toMatchObject({
      detail: { code: "PHASE1_NOT_READY" },
    });
  });

  it("throws 404 when video not found", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: { error: "Video not found", code: "NOT_FOUND", trace_id: "t5" } }),
    });

    await expect(confirmPhase1Review("bad-id")).rejects.toMatchObject({
      detail: { code: "NOT_FOUND" },
    });
  });
});
