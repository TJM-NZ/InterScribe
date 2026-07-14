import { describe, it, expect, vi, beforeEach } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

import { assignSpeakers, confirmReview, getTranscript } from "../lib/api";

beforeEach(() => {
  mockFetch.mockReset();
});

describe("getTranscript", () => {
  it("returns ordered segments", async () => {
    const segments = [
      { id: "s1", video_id: "v1", segment_id: 0, start_ts: 0, end_ts: 1, text: "Hello", speaker_label: "SPEAKER_00", confidence: 0.95 },
      { id: "s2", video_id: "v1", segment_id: 1, start_ts: 1, end_ts: 2, text: "World", speaker_label: "SPEAKER_01", confidence: 0.60 },
    ];
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ segments }) });

    const result = await getTranscript("v1");
    expect(result.segments).toHaveLength(2);
    expect(result.segments[1].confidence).toBe(0.60);
  });

  it("throws 409 when transcript not ready", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: { error: "Transcript not yet available", code: "TRANSCRIPT_NOT_READY", trace_id: "t1" } }),
    });

    await expect(getTranscript("v1")).rejects.toMatchObject({
      detail: { code: "TRANSCRIPT_NOT_READY" },
    });
  });
});

describe("assignSpeakers", () => {
  it("sends assignments and returns updated map", async () => {
    const responseMap = [
      { id: "m1", video_id: "v1", speaker_label: "SPEAKER_00", role: "interviewer" },
      { id: "m2", video_id: "v1", speaker_label: "SPEAKER_01", role: "interviewee" },
    ];
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ video_id: "v1", speaker_role_map: responseMap }),
    });

    const result = await assignSpeakers("v1", [
      { speaker_label: "SPEAKER_00", role: "interviewer" },
      { speaker_label: "SPEAKER_01", role: "interviewee" },
    ]);

    expect(result.speaker_role_map).toHaveLength(2);
    expect(result.speaker_role_map[0].role).toBe("interviewer");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/videos/v1/speakers"),
      expect.objectContaining({ method: "PATCH" })
    );
  });

  it("throws 400 on unknown speaker label", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: { error: "Unknown speaker_label: SPEAKER_99", code: "UNKNOWN_SPEAKER_LABEL", trace_id: "t2" } }),
    });

    await expect(
      assignSpeakers("v1", [{ speaker_label: "SPEAKER_99", role: "interviewer" }])
    ).rejects.toMatchObject({ detail: { code: "UNKNOWN_SPEAKER_LABEL" } });
  });
});

describe("confirmReview", () => {
  it("posts and returns reviewed status", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ video_id: "v1", status: "reviewed" }),
    });

    const result = await confirmReview("v1");
    expect(result.status).toBe("reviewed");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/videos/v1/confirm-review"),
      expect.objectContaining({ method: "POST" })
    );
  });

  it("throws 409 when speakers unmapped", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: { error: "Not all speakers have been assigned", code: "SPEAKERS_UNMAPPED", trace_id: "t3" } }),
    });

    await expect(confirmReview("v1")).rejects.toMatchObject({
      detail: { code: "SPEAKERS_UNMAPPED" },
    });
  });

  it("throws 404 when video not found", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: { error: "Video not found", code: "NOT_FOUND", trace_id: "t4" } }),
    });

    await expect(confirmReview("bad-id")).rejects.toMatchObject({
      detail: { code: "NOT_FOUND" },
    });
  });
});
