"use client";

import type { TranscriptSegment } from "@/lib/api";

const LOW_CONFIDENCE_THRESHOLD = 0.7;

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

interface Props {
  segments: TranscriptSegment[];
  speakerRoles?: Record<string, string>;
}

export default function TranscriptViewer({ segments, speakerRoles = {} }: Props) {
  if (segments.length === 0) {
    return <p className="text-gray-400 text-sm">No transcript segments found.</p>;
  }

  return (
    <div className="space-y-1" data-testid="transcript-viewer">
      {segments.map((seg) => {
        const isLowConfidence = seg.confidence < LOW_CONFIDENCE_THRESHOLD;
        const isRepetition = seg.repetition_flagged;
        const roleName = speakerRoles[seg.speaker_label];

        return (
          <div
            key={seg.id}
            data-testid="transcript-segment"
            className={`rounded px-3 py-2 text-sm ${
              isLowConfidence ? "bg-amber-50 border border-amber-200" : "bg-white border border-gray-100"
            }`}
          >
            <div className="flex items-baseline gap-2 mb-0.5">
              <span className="text-xs font-mono text-gray-400 shrink-0">
                {formatTime(seg.start_ts)}
              </span>
              <span className="text-xs font-medium text-gray-500">
                {seg.speaker_label}
                {roleName ? ` (${roleName})` : ""}
              </span>
              {isLowConfidence && (
                <span
                  className="text-xs text-amber-600 font-medium"
                  title={`Confidence: ${(seg.confidence * 100).toFixed(0)}%`}
                  data-testid="low-confidence-flag"
                >
                  low confidence
                </span>
              )}
              {isRepetition && (
                <span
                  className="text-xs text-red-600 font-medium"
                  data-testid="repetition-flag"
                >
                  repetition detected
                </span>
              )}
            </div>
            <p className="text-gray-800">{seg.text}</p>
          </div>
        );
      })}
    </div>
  );
}
