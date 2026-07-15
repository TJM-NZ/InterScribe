"use client";

import type { NotableMoment } from "@/lib/api";

interface Props {
  moment: NotableMoment;
  onEdit: (moment: NotableMoment) => void;
  onReject: (moment: NotableMoment) => void;
  disabled?: boolean;
}

export default function NotableMomentCard({ moment, onEdit, onReject, disabled }: Props) {
  return (
    <div
      className={`border rounded-lg p-4 space-y-1 ${
        moment.reviewed ? "border-gray-200 bg-gray-50" : "border-amber-200 bg-amber-50"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-xs text-gray-500 mb-1">
            Segments {moment.start_segment_id}–{moment.end_segment_id}
            {moment.reviewed && (
              <span className="ml-2 text-green-600">✓ reviewed</span>
            )}
          </p>
          <p
            className="text-sm text-gray-800"
            data-testid={`moment-desc-${moment.id}`}
          >
            {moment.description}
          </p>
        </div>
        {!disabled && (
          <div className="flex gap-1 shrink-0">
            <button
              onClick={() => onEdit(moment)}
              className="px-2 py-1 text-xs text-indigo-600 border border-indigo-200 rounded hover:bg-indigo-50"
              data-testid={`edit-moment-${moment.id}`}
            >
              Edit
            </button>
            <button
              onClick={() => onReject(moment)}
              className="px-2 py-1 text-xs text-red-500 border border-red-200 rounded hover:bg-red-50"
              data-testid={`reject-moment-${moment.id}`}
            >
              Reject
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
