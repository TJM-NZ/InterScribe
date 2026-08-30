"use client";

import { useRef, useState } from "react";
import {
  cutSegment,
  formatTimestamp,
  logTranscriptCorrection,
  logTranscriptSpeakerCorrection,
  mergeSegments,
  type ReasonCategory,
  type TranscriptSegment,
} from "@/lib/api";

const REASON_LABELS: Record<ReasonCategory, string> = {
  model_error: "Model error",
  ambiguous_input: "Ambiguous input",
  edge_case: "Edge case",
  preference: "My preference",
};

interface Props {
  seg: TranscriptSegment;
  prevSeg: TranscriptSegment | null;
  nextSeg: TranscriptSegment | null;
  videoId: string;
  speakerLabels: string[];
  speakerNames: Record<string, string>;
  onClose: () => void;
  onSaved: (updatedSeg: TranscriptSegment) => void;
  onCut: (leftSeg: TranscriptSegment, rightSeg: TranscriptSegment, originalSegId: string) => void;
  onMerge: (mergedSeg: TranscriptSegment, removedSegId: string) => void;
}

export default function SegmentEditModal({
  seg,
  prevSeg,
  nextSeg,
  videoId,
  speakerLabels,
  speakerNames,
  onClose,
  onSaved,
  onCut,
  onMerge,
}: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [text, setText] = useState(seg.text);
  const [speakerLabel, setSpeakerLabel] = useState(seg.speaker_label);
  const [cursorPos, setCursorPos] = useState<number | null>(null);
  const [reason, setReason] = useState<ReasonCategory>("model_error");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const textChanged = text !== seg.text;
  const speakerChanged = speakerLabel !== seg.speaker_label;
  const hasChanges = textChanged || speakerChanged;

  const validCutPos = cursorPos !== null && cursorPos > 0 && cursorPos < text.length;
  const cutPreview = validCutPos
    ? { left: text.slice(0, cursorPos).trimEnd(), right: text.slice(cursorPos).trimStart() }
    : null;
  const canCut = !!(cutPreview?.left && cutPreview?.right);

  const updateCursor = () => {
    const el = textareaRef.current;
    if (el) setCursorPos(el.selectionStart);
  };

  const handleSave = async () => {
    setBusy(true);
    setError(null);
    try {
      if (textChanged) {
        await logTranscriptCorrection(videoId, {
          segment_id: seg.id,
          corrected_text: text,
          reason_category: reason,
          reason_note: null,
        });
      }
      if (speakerChanged) {
        await logTranscriptSpeakerCorrection(videoId, {
          segment_id: seg.id,
          corrected_speaker_label: speakerLabel,
          reason_category: "preference",
          reason_note: null,
        });
      }
      onSaved({ ...seg, text, speaker_label: speakerLabel });
      onClose();
    } catch {
      setError("Failed to save changes.");
      setBusy(false);
    }
  };

  const handleCut = async () => {
    if (!canCut || cursorPos === null) return;
    setBusy(true);
    setError(null);
    try {
      if (speakerChanged) {
        await logTranscriptSpeakerCorrection(videoId, {
          segment_id: seg.id,
          corrected_speaker_label: speakerLabel,
          reason_category: "preference",
          reason_note: null,
        });
      }
      const result = await cutSegment(videoId, seg.id, cursorPos, textChanged ? text : undefined);
      onCut(result.left_segment, result.right_segment, seg.id);
      onClose();
    } catch {
      setError("Failed to cut segment.");
      setBusy(false);
    }
  };

  const handleMergeDown = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await mergeSegments(videoId, seg.id);
      onMerge(result.merged_segment, result.removed_segment_id);
      onClose();
    } catch {
      setError("Failed to merge.");
      setBusy(false);
    }
  };

  const handleMergeUp = async () => {
    if (!prevSeg) return;
    setBusy(true);
    setError(null);
    try {
      const result = await mergeSegments(videoId, prevSeg.id);
      onMerge(result.merged_segment, result.removed_segment_id);
      onClose();
    } catch {
      setError("Failed to merge.");
      setBusy(false);
    }
  };

  const displaySpeaker = (label: string) => speakerNames[label] || label;

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold">
            Edit segment — {formatTimestamp(seg.start_ts)}
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none"
            aria-label="Close"
            data-testid="modal-close"
          >
            ×
          </button>
        </div>

        {speakerLabels.length > 1 && (
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Speaker</label>
            <select
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
              value={speakerLabel}
              onChange={(e) => setSpeakerLabel(e.target.value)}
              data-testid="speaker-select"
            >
              {speakerLabels.map((l) => (
                <option key={l} value={l}>{displaySpeaker(l)}</option>
              ))}
            </select>
          </div>
        )}

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Text
            <span className="ml-1 text-gray-400 font-normal">— click to position the cut point</span>
          </label>
          <textarea
            ref={textareaRef}
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm resize-none font-mono"
            rows={4}
            value={text}
            onChange={(e) => { setText(e.target.value); setCursorPos(null); }}
            onSelect={updateCursor}
            onClick={updateCursor}
            onKeyUp={updateCursor}
            data-testid="segment-text-input"
          />
        </div>

        {cutPreview && (
          <div className="rounded border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs space-y-1" data-testid="cut-preview">
            <p className="font-medium text-indigo-700">Cut preview</p>
            <p className="text-gray-700"><span className="font-medium">↑ </span>"{cutPreview.left}"</p>
            <p className="text-gray-700"><span className="font-medium">↓ </span>"{cutPreview.right}"</p>
          </div>
        )}

        <div className="flex gap-2">
          <button
            onClick={handleMergeUp}
            disabled={busy || !prevSeg || hasChanges}
            title={
              hasChanges
                ? "Save or cancel changes first"
                : prevSeg
                ? "Merge with previous segment"
                : "No previous segment"
            }
            className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            data-testid="merge-up-button"
          >
            Merge ↑
          </button>
          <button
            onClick={handleCut}
            disabled={busy || !canCut}
            title={canCut ? "Cut at cursor position" : "Click in the text to position the cut point"}
            className="flex-1 px-3 py-2 text-sm bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed"
            data-testid="cut-button"
          >
            {busy ? "Working…" : "Cut here"}
          </button>
          <button
            onClick={handleMergeDown}
            disabled={busy || !nextSeg || hasChanges}
            title={
              hasChanges
                ? "Save or cancel changes first"
                : nextSeg
                ? "Merge with next segment"
                : "No next segment"
            }
            className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            data-testid="merge-down-button"
          >
            Merge ↓
          </button>
        </div>

        {hasChanges && (
          <p className="text-xs text-amber-600">
            Merge is disabled while there are unsaved changes — save or cancel first.
          </p>
        )}

        {textChanged && (
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Reason for text change <span className="text-red-500">*</span>
            </label>
            <div className="grid grid-cols-2 gap-2">
              {(Object.keys(REASON_LABELS) as ReasonCategory[]).map((r) => (
                <label key={r} className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="radio"
                    name="reason"
                    value={r}
                    checked={reason === r}
                    onChange={() => setReason(r)}
                    data-testid={`reason-${r}`}
                  />
                  {REASON_LABELS[r]}
                </label>
              ))}
            </div>
          </div>
        )}

        {error && <p className="text-sm text-red-600" data-testid="modal-error">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={onClose}
            disabled={busy}
            className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={busy || !hasChanges}
            className="px-4 py-2 bg-emerald-600 text-white text-sm rounded hover:bg-emerald-700 disabled:opacity-40"
            data-testid="save-button"
          >
            {busy ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
