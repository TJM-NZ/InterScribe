"use client";

import { useState } from "react";
import { formatTimestamp, type TranscriptSegment } from "@/lib/api";
import SegmentEditModal from "@/components/SegmentEditModal";

const LOW_CONFIDENCE_THRESHOLD = 0.7;

interface Props {
  segments: TranscriptSegment[];
  speakerRoles?: Record<string, string>;
  speakerNames?: Record<string, string>;
  videoId?: string;
  speakerLabels?: string[];
}

export default function TranscriptViewer({
  segments: initialSegments,
  speakerRoles = {},
  speakerNames = {},
  videoId,
  speakerLabels = [],
}: Props) {
  const [segments, setSegments] = useState(initialSegments);
  const [editing, setEditing] = useState<TranscriptSegment | null>(null);

  if (segments.length === 0) {
    return <p className="text-gray-400 text-sm">No transcript segments found.</p>;
  }

  const handleSaved = (updatedSeg: TranscriptSegment) => {
    setSegments((prev) => prev.map((s) => (s.id === updatedSeg.id ? updatedSeg : s)));
  };

  const handleCut = (
    leftSeg: TranscriptSegment,
    rightSeg: TranscriptSegment,
    originalSegId: string,
  ) => {
    setSegments((prev) => {
      const idx = prev.findIndex((s) => s.id === originalSegId);
      if (idx === -1) return prev;
      return [...prev.slice(0, idx), leftSeg, rightSeg, ...prev.slice(idx + 1)];
    });
  };

  const handleMerge = (mergedSeg: TranscriptSegment, removedSegId: string) => {
    setSegments((prev) =>
      prev.map((s) => (s.id === mergedSeg.id ? mergedSeg : s)).filter((s) => s.id !== removedSegId)
    );
  };

  return (
    <>
      <div className="space-y-1" data-testid="transcript-viewer">
        {segments.map((seg, idx) => {
          const isLowConfidence = seg.confidence < LOW_CONFIDENCE_THRESHOLD;
          const isRepetition = seg.repetition_flagged;
          const roleName = speakerRoles[seg.speaker_label];
          const speakerName = speakerNames[seg.speaker_label];
          const displayLabel = speakerName || seg.speaker_label;

          return (
            <div
              key={seg.id}
              data-testid="transcript-segment"
              className={`rounded px-3 py-2 text-sm ${
                isLowConfidence
                  ? "bg-amber-50 border border-amber-200"
                  : "bg-white border border-gray-100"
              }`}
            >
              <div className="flex items-baseline gap-2 mb-0.5">
                <span className="text-xs font-mono text-gray-400 shrink-0">
                  {formatTimestamp(seg.start_ts)}
                </span>
                <span className="text-xs font-medium text-gray-500">
                  {displayLabel}
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
                {videoId && (
                  <button
                    onClick={() => setEditing(seg)}
                    className="ml-auto text-xs text-gray-400 hover:text-indigo-600"
                    data-testid="edit-segment-button"
                  >
                    Edit
                  </button>
                )}
              </div>
              <p className="text-gray-800">{seg.text}</p>
            </div>
          );
        })}
      </div>

      {editing && videoId && (
        <SegmentEditModal
          seg={editing}
          prevSeg={segments[segments.findIndex((s) => s.id === editing.id) - 1] ?? null}
          nextSeg={segments[segments.findIndex((s) => s.id === editing.id) + 1] ?? null}
          videoId={videoId}
          speakerLabels={speakerLabels}
          speakerNames={speakerNames}
          onClose={() => setEditing(null)}
          onSaved={handleSaved}
          onCut={handleCut}
          onMerge={handleMerge}
        />
      )}
    </>
  );
}
