"use client";

import { useState } from "react";
import { formatTimestamp, logTranscriptCorrection, type ReasonCategory, type TranscriptSegment } from "@/lib/api";
import CorrectionModal from "@/components/CorrectionModal";

const LOW_CONFIDENCE_THRESHOLD = 0.7;

interface Props {
  segments: TranscriptSegment[];
  speakerRoles?: Record<string, string>;
  speakerNames?: Record<string, string>;
  videoId?: string;
}

export default function TranscriptViewer({ segments: initialSegments, speakerRoles = {}, speakerNames = {}, videoId }: Props) {
  const [segments, setSegments] = useState(initialSegments);
  const [correcting, setCorrecting] = useState<TranscriptSegment | null>(null);

  if (segments.length === 0) {
    return <p className="text-gray-400 text-sm">No transcript segments found.</p>;
  }

  const handleCorrectionSubmit = async ({
    correctedValue,
    reasonCategory,
    reasonNote,
  }: {
    correctedValue: string | null;
    reasonCategory: ReasonCategory;
    reasonNote: string;
  }) => {
    if (!correcting || !videoId || correctedValue === null) return;
    await logTranscriptCorrection(videoId, {
      segment_id: correcting.id,
      corrected_text: correctedValue,
      reason_category: reasonCategory,
      reason_note: reasonNote || null,
    });
    setSegments((prev) =>
      prev.map((s) => (s.id === correcting.id ? { ...s, text: correctedValue } : s))
    );
  };

  return (
    <>
      <div className="space-y-1" data-testid="transcript-viewer">
        {segments.map((seg) => {
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
                isLowConfidence ? "bg-amber-50 border border-amber-200" : "bg-white border border-gray-100"
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
                    onClick={() => setCorrecting(seg)}
                    className="ml-auto text-xs text-gray-400 hover:text-indigo-600"
                    data-testid="correct-segment-button"
                  >
                    Correct
                  </button>
                )}
              </div>
              <p className="text-gray-800">{seg.text}</p>
            </div>
          );
        })}
      </div>

      {correcting && (
        <CorrectionModal
          title={`Correct segment at ${formatTimestamp(correcting.start_ts)}`}
          editMode={true}
          currentValue={correcting.text}
          onSubmit={handleCorrectionSubmit}
          onClose={() => setCorrecting(null)}
        />
      )}
    </>
  );
}
