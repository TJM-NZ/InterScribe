"use client";

import { useState } from "react";
import type { ReasonCategory } from "@/lib/api";

const REASON_LABELS: Record<ReasonCategory, string> = {
  model_error: "Model error",
  ambiguous_input: "Ambiguous input",
  edge_case: "Edge case",
  preference: "My preference",
};

interface Props {
  title: string;
  editMode: boolean;
  currentValue: string;
  onSubmit: (args: {
    correctedValue: string | null;
    reasonCategory: ReasonCategory;
    reasonNote: string;
  }) => Promise<void>;
  onClose: () => void;
}

export default function CorrectionModal({
  title,
  editMode,
  currentValue,
  onSubmit,
  onClose,
}: Props) {
  const [corrected, setCorrected] = useState(currentValue);
  const [reason, setReason] = useState<ReasonCategory>("model_error");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({
        correctedValue: editMode ? corrected : null,
        reasonCategory: reason,
        reasonNote: note,
      });
      onClose();
    } catch {
      setError("Failed to log correction.");
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6 space-y-4">
        <h3 className="text-base font-semibold">{title}</h3>

        {editMode && (
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Corrected value
            </label>
            <textarea
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm resize-none"
              rows={3}
              value={corrected}
              onChange={(e) => setCorrected(e.target.value)}
              data-testid="corrected-value-input"
            />
          </div>
        )}

        {!editMode && (
          <p className="text-sm text-gray-600">
            This will reject the item and log a correction record.
          </p>
        )}

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Reason <span className="text-red-500">*</span>
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

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Note (optional)
          </label>
          <input
            type="text"
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Additional context…"
          />
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="px-4 py-2 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-700 disabled:opacity-40"
            data-testid="correction-submit"
          >
            {submitting ? "Saving…" : editMode ? "Save correction" : "Reject"}
          </button>
        </div>
      </div>
    </div>
  );
}
