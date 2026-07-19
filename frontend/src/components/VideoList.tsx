"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { rerunTranscript, rerunVideo, retryVideo, type VideoStatus, type VideoSummary } from "@/lib/api";

const STATUS_LABELS: Record<VideoStatus, string> = {
  uploaded: "Uploaded",
  queued: "Queued",
  transcribing: "Transcribing…",
  ready_for_review: "Ready for review",
  phase1_queued: "Analysis queued",
  phase1_processing: "Analysing…",
  phase1_ready_for_review: "Ready for Phase 1 review",
  phase1_reviewed: "Phase 1 complete",
  phase2_queued: "Quote extraction queued",
  phase2_processing: "Extracting quotes…",
  phase2_ready_for_review: "Ready for Phase 2 review",
  phase2_reviewed: "Phase 2 complete",
  condensation_queued: "Condensation queued",
  condensation_processing: "Condensing headlines…",
  condensation_ready_for_review: "Ready for headline review",
  condensation_reviewed: "Complete",
  failed: "Failed",
};

const STATUS_COLORS: Record<VideoStatus, string> = {
  uploaded: "bg-gray-100 text-gray-600",
  queued: "bg-yellow-100 text-yellow-700",
  transcribing: "bg-blue-100 text-blue-700",
  ready_for_review: "bg-green-100 text-green-700",
  phase1_queued: "bg-yellow-100 text-yellow-700",
  phase1_processing: "bg-blue-100 text-blue-700",
  phase1_ready_for_review: "bg-purple-100 text-purple-700",
  phase1_reviewed: "bg-emerald-100 text-emerald-700",
  phase2_queued: "bg-yellow-100 text-yellow-700",
  phase2_processing: "bg-blue-100 text-blue-700",
  phase2_ready_for_review: "bg-violet-100 text-violet-700",
  phase2_reviewed: "bg-emerald-100 text-emerald-700",
  condensation_queued: "bg-yellow-100 text-yellow-700",
  condensation_processing: "bg-blue-100 text-blue-700",
  condensation_ready_for_review: "bg-orange-100 text-orange-700",
  condensation_reviewed: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
};

interface Props {
  videos: VideoSummary[];
  onRefreshVideo: (id: string) => Promise<void>;
}

function getDetailPath(videoId: string, status: VideoStatus): string | null {
  if (status === "condensation_ready_for_review" || status === "condensation_reviewed") {
    return `/videos/${videoId}/condensation`;
  }
  if (
    status === "phase2_ready_for_review" ||
    status === "phase2_reviewed" ||
    status === "condensation_queued" ||
    status === "condensation_processing"
  ) {
    return `/videos/${videoId}/phase2`;
  }
  if (
    status === "phase1_ready_for_review" ||
    status === "phase1_reviewed" ||
    status === "phase2_queued" ||
    status === "phase2_processing"
  ) {
    return `/videos/${videoId}/phase1`;
  }
  if (
    status === "ready_for_review" ||
    status === "phase1_queued" ||
    status === "phase1_processing"
  ) {
    return `/videos/${videoId}`;
  }
  return null;
}

interface DropdownAction {
  label: string;
  href?: string;
  onClick?: () => Promise<void>;
  style: "primary" | "secondary" | "danger";
}

function VideoActionsDropdown({
  v,
  onRefreshVideo,
}: {
  v: VideoSummary;
  onRefreshVideo: (id: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const actions: DropdownAction[] = [];

  if (v.status === "ready_for_review") {
    actions.push({ label: "Review transcript", href: `/videos/${v.id}`, style: "primary" });
  } else if (v.status === "phase1_queued" || v.status === "phase1_processing") {
    actions.push({ label: "View transcript", href: `/videos/${v.id}`, style: "secondary" });
  } else if (v.status === "phase1_ready_for_review") {
    actions.push({ label: "Review narrative", href: `/videos/${v.id}/phase1`, style: "primary" });
    actions.push({ label: "View transcript", href: `/videos/${v.id}`, style: "secondary" });
  } else if (v.status === "phase1_reviewed") {
    actions.push({ label: "View narrative", href: `/videos/${v.id}/phase1`, style: "secondary" });
    actions.push({ label: "View transcript", href: `/videos/${v.id}`, style: "secondary" });
    actions.push({
      label: "Re-run Phase 1",
      onClick: async () => { await rerunVideo(v.id); await onRefreshVideo(v.id); },
      style: "danger",
    });
  } else if (v.status === "phase2_queued" || v.status === "phase2_processing") {
    actions.push({ label: "View narrative", href: `/videos/${v.id}/phase1`, style: "secondary" });
    actions.push({ label: "View transcript", href: `/videos/${v.id}`, style: "secondary" });
  } else if (v.status === "phase2_ready_for_review") {
    actions.push({ label: "Review quotes", href: `/videos/${v.id}/phase2`, style: "primary" });
    actions.push({ label: "View narrative", href: `/videos/${v.id}/phase1`, style: "secondary" });
    actions.push({ label: "View transcript", href: `/videos/${v.id}`, style: "secondary" });
  } else if (v.status === "phase2_reviewed") {
    actions.push({ label: "View quotes", href: `/videos/${v.id}/phase2`, style: "secondary" });
    actions.push({ label: "View narrative", href: `/videos/${v.id}/phase1`, style: "secondary" });
    actions.push({ label: "View transcript", href: `/videos/${v.id}`, style: "secondary" });
    actions.push({
      label: "Re-run Phase 2",
      onClick: async () => { await rerunVideo(v.id); await onRefreshVideo(v.id); },
      style: "danger",
    });
  } else if (v.status === "condensation_queued" || v.status === "condensation_processing") {
    actions.push({ label: "View quotes", href: `/videos/${v.id}/phase2`, style: "secondary" });
    actions.push({ label: "View narrative", href: `/videos/${v.id}/phase1`, style: "secondary" });
    actions.push({ label: "View transcript", href: `/videos/${v.id}`, style: "secondary" });
  } else if (v.status === "condensation_ready_for_review") {
    actions.push({ label: "Review headlines", href: `/videos/${v.id}/condensation`, style: "primary" });
    actions.push({ label: "View quotes", href: `/videos/${v.id}/phase2`, style: "secondary" });
    actions.push({ label: "View narrative", href: `/videos/${v.id}/phase1`, style: "secondary" });
    actions.push({ label: "View transcript", href: `/videos/${v.id}`, style: "secondary" });
  } else if (v.status === "condensation_reviewed") {
    actions.push({ label: "View headlines", href: `/videos/${v.id}/condensation`, style: "secondary" });
    actions.push({ label: "View quotes", href: `/videos/${v.id}/phase2`, style: "secondary" });
    actions.push({ label: "View narrative", href: `/videos/${v.id}/phase1`, style: "secondary" });
    actions.push({ label: "View transcript", href: `/videos/${v.id}`, style: "secondary" });
  } else if (v.status === "failed") {
    actions.push({
      label: "Retry",
      onClick: async () => { await retryVideo(v.id); await onRefreshVideo(v.id); },
      style: "primary",
    });
  }

  const postTranscriptStatuses: VideoStatus[] = [
    "ready_for_review",
    "phase1_ready_for_review", "phase1_reviewed",
    "phase2_ready_for_review", "phase2_reviewed",
    "condensation_ready_for_review", "condensation_reviewed",
  ];
  if (postTranscriptStatuses.includes(v.status)) {
    actions.push({
      label: "Re-run transcript",
      onClick: async () => { await rerunTranscript(v.id); await onRefreshVideo(v.id); },
      style: "danger",
    });
  }

  if (actions.length === 0) return null;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="text-gray-400 hover:text-gray-600 px-2 py-1 rounded hover:bg-gray-100 text-base leading-none"
        title="Actions"
        aria-label="Actions"
      >
        ···
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 z-10 bg-white border border-gray-200 rounded-lg shadow-lg py-1 min-w-[190px]">
          {actions.map((action) => {
            const colorClass =
              action.style === "primary"
                ? "text-blue-600 font-medium"
                : action.style === "danger"
                ? "text-red-500"
                : "text-gray-700";

            if (action.href) {
              return (
                <Link
                  key={action.label}
                  href={action.href}
                  className={`block w-full text-left px-4 py-2 text-sm hover:bg-gray-50 ${colorClass}`}
                  onClick={() => setOpen(false)}
                >
                  {action.label}
                </Link>
              );
            }

            return (
              <button
                key={action.label}
                disabled={loading === action.label}
                onClick={async () => {
                  setLoading(action.label);
                  try {
                    await action.onClick!();
                  } finally {
                    setLoading(null);
                    setOpen(false);
                  }
                }}
                className={`w-full text-left px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-50 ${colorClass}`}
              >
                {loading === action.label ? "…" : action.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function VideoList({ videos, onRefreshVideo }: Props) {
  if (videos.length === 0) {
    return <p className="text-gray-400 text-sm mt-6">No files uploaded yet.</p>;
  }

  return (
    <ul className="mt-6 space-y-2" data-testid="video-list">
      {videos.map((v) => {
        const detailPath = getDetailPath(v.id, v.status);
        return (
          <li
            key={v.id}
            className="bg-white border border-gray-200 rounded-lg px-4 py-3 flex items-center justify-between"
          >
            <div className="min-w-0 flex-1">
              {detailPath ? (
                <Link href={detailPath} className="group">
                  <p
                    className="font-medium text-sm truncate group-hover:text-blue-600 group-hover:underline"
                    title={v.original_filename}
                  >
                    {v.original_filename}
                  </p>
                </Link>
              ) : (
                <p className="font-medium text-sm truncate" title={v.original_filename}>
                  {v.original_filename}
                </p>
              )}
              <p className="text-xs text-gray-400 mt-0.5">
                {v.media_type}
                {v.duration_seconds ? ` · ${Math.round(v.duration_seconds / 60)} min` : ""}
              </p>
              {v.status === "failed" && v.error_reason && (
                <p className="text-xs text-red-500 mt-0.5 truncate" title={v.error_reason}>
                  {v.error_reason}
                </p>
              )}
            </div>
            <div className="flex items-center gap-3 ml-4">
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[v.status]}`}>
                {STATUS_LABELS[v.status]}
              </span>
              <VideoActionsDropdown v={v} onRefreshVideo={onRefreshVideo} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
