import { describe, it, expect, vi, beforeEach } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

import { assignSpeakers, confirmReview, cutSegment, getTranscript } from "../lib/api";

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
      json: async () => ({ video_id: "v1", status: "phase1_queued" }),
    });

    const result = await confirmReview("v1");
    expect(result.status).toBe("phase1_queued");
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

describe("cutSegment", () => {
  const leftSeg = { id: "s1", video_id: "v1", segment_id: 0, start_ts: 0, end_ts: 5.5, text: "Hello world", speaker_label: "SPEAKER_00", confidence: 0.9, repetition_flagged: false };
  const rightSeg = { id: "s2", video_id: "v1", segment_id: 1, start_ts: 5.5, end_ts: 10, text: "goodbye world", speaker_label: "SPEAKER_00", confidence: 0.9, repetition_flagged: false };

  it("posts cut and returns left and right segments", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ left_segment: leftSeg, right_segment: rightSeg }),
    });

    const result = await cutSegment("v1", "s1", 11);
    expect(result.left_segment.text).toBe("Hello world");
    expect(result.right_segment.text).toBe("goodbye world");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/videos/v1/transcript/cut"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("sends text param when provided", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ left_segment: leftSeg, right_segment: rightSeg }) });

    await cutSegment("v1", "s1", 5, "Hello world");
    const body = JSON.parse((mockFetch.mock.calls[0][1] as RequestInit).body as string);
    expect(body.text).toBe("Hello world");
    expect(body.cut_at_char).toBe(5);
  });

  it("omits text param when not provided", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ left_segment: leftSeg, right_segment: rightSeg }) });

    await cutSegment("v1", "s1", 5);
    const body = JSON.parse((mockFetch.mock.calls[0][1] as RequestInit).body as string);
    expect(body.text).toBeNull();
  });

  it("throws 409 when not ready for review", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: { error: "Cut only allowed during Gate 1 review", code: "NOT_READY_FOR_REVIEW", trace_id: "t1" } }),
    });
    await expect(cutSegment("v1", "s1", 5)).rejects.toMatchObject({
      detail: { code: "NOT_READY_FOR_REVIEW" },
    });
  });

  it("throws 400 on invalid cut position", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: { error: "cut_at_char out of range", code: "CUT_POSITION_INVALID", trace_id: "t2" } }),
    });
    await expect(cutSegment("v1", "s1", 0)).rejects.toMatchObject({
      detail: { code: "CUT_POSITION_INVALID" },
    });
  });
});
