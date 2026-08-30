"use client";

import { useState } from "react";
import {
  formatTimestamp,
  logTranscriptCorrection,
  logTranscriptSpeakerCorrection,
  mergeSegments,
  type ReasonCategory,
  type TranscriptSegment,
} from "@/lib/api";
import CorrectionModal from "@/components/CorrectionModal";

const LOW_CONFIDENCE_THRESHOLD = 0.7;

interface Props {
  segments: TranscriptSegment[];
  speakerRoles?: Record<string, string>;
  speakerNames?: Record<string, string>;
  videoId?: string;
  speakerLabels?: string[];
}

type CorrectingMode = { seg: TranscriptSegment; mode: "text" } | { seg: TranscriptSegment; mode: "speaker" };

export default function TranscriptViewer({
  segments: initialSegments,
  speakerRoles = {},
  speakerNames = {},
  videoId,
  speakerLabels = [],
}: Props) {
  const [segments, setSegments] = useState(initialSegments);
  const [correcting, setCorrecting] = useState<CorrectingMode | null>(null);
  const [merging, setMerging] = useState<string | null>(null);

  if (segments.length === 0) {
    return <p className="text-gray-400 text-sm">No transcript segments found.</p>;
  }

  const handleTextCorrectionSubmit = async ({
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
      segment_id: correcting.seg.id,
      corrected_text: correctedValue,
      reason_category: reasonCategory,
      reason_note: reasonNote || null,
    });
    setSegments((prev) =>
      prev.map((s) => (s.id === correcting.seg.id ? { ...s, text: correctedValue } : s))
    );
  };

  const handleSpeakerCorrectionSubmit = async ({
    correctedValue,
    reasonCategory,
    reasonNote,
  }: {
    correctedValue: string | null;
    reasonCategory: ReasonCategory;
    reasonNote: string;
  }) => {
    if (!correcting || !videoId || correctedValue === null) return;
    await logTranscriptSpeakerCorrection(videoId, {
      segment_id: correcting.seg.id,
      corrected_speaker_label: correctedValue,
      reason_category: reasonCategory,
      reason_note: reasonNote || null,
    });
    setSegments((prev) =>
      prev.map((s) => (s.id === correcting.seg.id ? { ...s, speaker_label: correctedValue } : s))
    );
  };

  const handleMerge = async (seg: TranscriptSegment) => {
    if (!videoId || merging) return;
    setMerging(seg.id);
    try {
      const { merged_segment, removed_segment_id } = await mergeSegments(videoId, seg.id);
      setSegments((prev) =>
        prev
          .map((s) => (s.id === seg.id ? { ...s, ...merged_segment } : s))
          .filter((s) => s.id !== removed_segment_id)
      );
    } finally {
      setMerging(null);
    }
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
          const otherSpeakers = speakerLabels.filter((l) => l !== seg.speaker_label);
          const isLast = idx === segments.length - 1;
          const isMerging = merging === seg.id;

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
                  <span className="ml-auto flex gap-2">
                    {otherSpeakers.length > 0 && (
                      <button
                        onClick={() => setCorrecting({ seg, mode: "speaker" })}
                        className="text-xs text-gray-400 hover:text-indigo-600"
                        data-testid="correct-speaker-button"
                      >
                        Wrong speaker
                      </button>
                    )}
                    <button
                      onClick={() => setCorrecting({ seg, mode: "text" })}
                      className="text-xs text-gray-400 hover:text-indigo-600"
                      data-testid="correct-segment-button"
                    >
                      Correct
                    </button>
                    {!isLast && (
                      <button
                        onClick={() => handleMerge(seg)}
                        disabled={isMerging}
                        className="text-xs text-gray-400 hover:text-indigo-600 disabled:opacity-40"
                        data-testid="merge-segment-button"
                      >
                        {isMerging ? "Merging…" : "Merge ↓"}
                      </button>
                    )}
                  </span>
                )}
              </div>
              <p className="text-gray-800">{seg.text}</p>
            </div>
          );
        })}
      </div>

      {correcting?.mode === "text" && (
        <CorrectionModal
          title={`Correct transcript at ${formatTimestamp(correcting.seg.start_ts)}`}
          editMode={true}
          currentValue={correcting.seg.text}
          onSubmit={handleTextCorrectionSubmit}
          onClose={() => setCorrecting(null)}
        />
      )}

      {correcting?.mode === "speaker" && (
        <CorrectionModal
          title={`Correct speaker at ${formatTimestamp(correcting.seg.start_ts)}`}
          editMode={true}
          currentValue={speakerLabels.filter((l) => l !== correcting.seg.speaker_label)[0] ?? ""}
          selectOptions={speakerLabels.filter((l) => l !== correcting.seg.speaker_label)}
          onSubmit={handleSpeakerCorrectionSubmit}
          onClose={() => setCorrecting(null)}
        />
      )}
    </>
  );
}
