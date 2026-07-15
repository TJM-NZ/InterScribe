"use client";

import { useState } from "react";
import Link from "next/link";
import { enqueuePhase1, type VideoStatus, type VideoSummary } from "@/lib/api";

const STATUS_LABELS: Record<VideoStatus, string> = {
  uploaded: "Uploaded",
  queued: "Queued",
  transcribing: "Transcribing…",
  ready_for_review: "Ready for review",
  reviewed: "Reviewed",
  phase1_queued: "Analysis queued",
  phase1_processing: "Analysing…",
  phase1_ready_for_review: "Ready for Phase 1 review",
  phase1_reviewed: "Phase 1 complete",
  failed: "Failed",
};

const STATUS_COLORS: Record<VideoStatus, string> = {
  uploaded: "bg-gray-100 text-gray-600",
  queued: "bg-yellow-100 text-yellow-700",
  transcribing: "bg-blue-100 text-blue-700",
  ready_for_review: "bg-green-100 text-green-700",
  reviewed: "bg-emerald-100 text-emerald-700",
  phase1_queued: "bg-yellow-100 text-yellow-700",
  phase1_processing: "bg-blue-100 text-blue-700",
  phase1_ready_for_review: "bg-purple-100 text-purple-700",
  phase1_reviewed: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
};

interface Props {
  videos: VideoSummary[];
  onRefreshVideo: (id: string) => Promise<void>;
}

function VideoActions({ v, onRefreshVideo }: { v: VideoSummary; onRefreshVideo: (id: string) => Promise<void> }) {
  const [loading, setLoading] = useState(false);

  if (v.status === "ready_for_review") {
    return <Link href={`/videos/${v.id}`} className="text-xs text-blue-600 hover:underline">Review transcript →</Link>;
  }
  if (v.status === "reviewed") {
    return (
      <button
        onClick={async () => {
          setLoading(true);
          try {
            await enqueuePhase1(v.id);
            await onRefreshVideo(v.id);
          } finally {
            setLoading(false);
          }
        }}
        disabled={loading}
        className="text-xs text-emerald-600 hover:underline disabled:opacity-50"
      >
        {loading ? "Queuing…" : "Start analysis →"}
      </button>
    );
  }
  if (v.status === "phase1_ready_for_review") {
    return <Link href={`/videos/${v.id}/phase1`} className="text-xs text-purple-600 hover:underline">Review narrative →</Link>;
  }
  return null;
}

export default function VideoList({ videos, onRefreshVideo }: Props) {
  if (videos.length === 0) {
    return <p className="text-gray-400 text-sm mt-6">No files uploaded yet.</p>;
  }

  return (
    <ul className="mt-6 space-y-2" data-testid="video-list">
      {videos.map((v) => (
        <li key={v.id} className="bg-white border border-gray-200 rounded-lg px-4 py-3 flex items-center justify-between">
          <div>
            <p className="font-medium text-sm">{v.original_filename}</p>
            <p className="text-xs text-gray-400 mt-0.5">
              {v.media_type} {v.duration_seconds ? `· ${Math.round(v.duration_seconds / 60)} min` : ""}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[v.status]}`}>
              {STATUS_LABELS[v.status]}
            </span>
            <VideoActions v={v} onRefreshVideo={onRefreshVideo} />
          </div>
        </li>
      ))}
    </ul>
  );
}
