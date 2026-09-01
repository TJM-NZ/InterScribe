import { describe, it, expect, vi, beforeEach } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

import { uploadVideo } from "../lib/api";

beforeEach(() => {
  mockFetch.mockReset();
});

describe("uploadVideo", () => {
  it("posts file as multipart and returns upload response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        id: "abc-123",
        status: "queued",
        original_filename: "interview.wav",
        media_type: "audio",
      }),
    });

    const file = new File(["audio-data"], "interview.wav", { type: "audio/wav" });
    const result = await uploadVideo(file);

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/videos"),
      expect.objectContaining({ method: "POST" })
    );
    expect(result.status).toBe("queued");
    expect(result.id).toBe("abc-123");
    expect(result.media_type).toBe("audio");
  });

  it("throws on 400 unsupported type", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: { error: "Unsupported file type", code: "UNSUPPORTED_MEDIA_TYPE", trace_id: "trace-1" } }),
    });

    const file = new File(["data"], "doc.pdf", { type: "application/pdf" });
    await expect(uploadVideo(file)).rejects.toMatchObject({
      detail: { code: "UNSUPPORTED_MEDIA_TYPE" },
    });
  });

  it("throws on 413 oversized", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: { error: "File exceeds limit", code: "FILE_TOO_LARGE", trace_id: "trace-2" } }),
    });

    const file = new File(["big-data"], "big.mp4", { type: "video/mp4" });
    await expect(uploadVideo(file)).rejects.toMatchObject({
      detail: { code: "FILE_TOO_LARGE" },
    });
  });
});
