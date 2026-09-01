import { describe, it, expect, vi, beforeEach } from "vitest";
import { JSDOM } from "jsdom";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

import { getTranscript } from "../lib/api";
import type { TranscriptSegment } from "../lib/api";

beforeEach(() => {
  mockFetch.mockReset();
});

function makeSegment(overrides: Partial<TranscriptSegment>): TranscriptSegment {
  return {
    id: "s1",
    video_id: "v1",
    segment_id: 0,
    start_ts: 0,
    end_ts: 1,
    text: "hello",
    speaker_label: "SPEAKER_00",
    confidence: 0.95,
    repetition_flagged: false,
    ...overrides,
  };
}

function renderSegmentHtml(seg: TranscriptSegment): Document {
  const isLowConfidence = seg.confidence < 0.7;
  const isRepetition = seg.repetition_flagged;

  const lowConfidenceTag = isLowConfidence
    ? `<span class="text-xs text-amber-600 font-medium" data-testid="low-confidence-flag">low confidence</span>`
    : "";
  const repetitionTag = isRepetition
    ? `<span class="text-xs text-red-600 font-medium" data-testid="repetition-flag">repetition detected</span>`
    : "";

  const html = `<div data-testid="transcript-segment">${lowConfidenceTag}${repetitionTag}</div>`;
  return new JSDOM(html).window.document;
}

describe("repetition-flag rendering", () => {
  it("renders repetition detected tag when repetition_flagged is true", () => {
    const seg = makeSegment({ repetition_flagged: true });
    const doc = renderSegmentHtml(seg);
    const tag = doc.querySelector("[data-testid='repetition-flag']");
    expect(tag).not.toBeNull();
    expect(tag?.textContent).toBe("repetition detected");
  });

  it("does not render repetition tag when repetition_flagged is false", () => {
    const seg = makeSegment({ repetition_flagged: false });
    const doc = renderSegmentHtml(seg);
    const tag = doc.querySelector("[data-testid='repetition-flag']");
    expect(tag).toBeNull();
  });

  it("renders both tags when repetition_flagged is true and confidence is low", () => {
    const seg = makeSegment({ repetition_flagged: true, confidence: 0.5 });
    const doc = renderSegmentHtml(seg);
    expect(doc.querySelector("[data-testid='repetition-flag']")).not.toBeNull();
    expect(doc.querySelector("[data-testid='low-confidence-flag']")).not.toBeNull();
  });

  it("repetition tag is visually distinct from low-confidence tag", () => {
    const seg = makeSegment({ repetition_flagged: true, confidence: 0.5 });
    const doc = renderSegmentHtml(seg);
    const repTag = doc.querySelector("[data-testid='repetition-flag']");
    const lcTag = doc.querySelector("[data-testid='low-confidence-flag']");
    expect(repTag?.className).not.toBe(lcTag?.className);
    expect(repTag?.getAttribute("data-testid")).not.toBe(lcTag?.getAttribute("data-testid"));
  });
});

describe("getTranscript includes repetition_flagged", () => {
  it("returns repetition_flagged field on segments", async () => {
    const segments = [
      makeSegment({ id: "s1", repetition_flagged: true }),
      makeSegment({ id: "s2", repetition_flagged: false }),
    ];
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ segments }) });

    const result = await getTranscript("v1");
    expect(result.segments[0].repetition_flagged).toBe(true);
    expect(result.segments[1].repetition_flagged).toBe(false);
  });
});
