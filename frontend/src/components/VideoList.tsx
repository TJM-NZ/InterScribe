"use client";

import { useState } from "react";
import Link from "next/link";
import { enqueuePhase1, rerunTranscript, rerunVideo, retryVideo, type VideoStatus, type VideoSummary } from "@/lib/api";

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
  phase2_queued: "Quote extraction queued",
  phase2_processing: "Extracting quotes…",
  phase2_ready_for_review: "Ready for Phase 2 review",
  phase2_reviewed: "Complete",
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
  phase2_queued: "bg-yellow-100 text-yellow-700",
  phase2_processing: "bg-blue-100 text-blue-700",
  phase2_ready_for_review: "bg-violet-100 text-violet-700",
  phase2_reviewed: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
};

interface Props {
  videos: VideoSummary[];
  onRefreshVideo: (id: string) => Promise<void>;
}

const POST_TRANSCRIPT_STATUSES = new Set<VideoStatus>([
  "ready_for_review", "reviewed",
  "phase1_ready_for_review", "phase1_reviewed",
  "phase2_ready_for_review", "phase2_reviewed",
]);

function RerunTranscriptButton({ id, onRefreshVideo }: { id: string; onRefreshVideo: (id: string) => Promise<void> }) {
  const [loading, setLoading] = useState(false);
  return (
    <button
      onClick={async () => {
        setLoading(true);
        try {
          await rerunTranscript(id);
          await onRefreshVideo(id);
        } finally {
          setLoading(false);
        }
      }}
      disabled={loading}
      className="text-xs text-gray-400 hover:text-gray-600 hover:underline disabled:opacity-50"
    >
      {loading ? "Re-running…" : "Re-run transcript"}
    </button>
  );
}

function VideoActions({ v, onRefreshVideo }: { v: VideoSummary; onRefreshVideo: (id: string) => Promise<void> }) {
  const [loading, setLoading] = useState(false);

  const showRerunTranscript = POST_TRANSCRIPT_STATUSES.has(v.status);

  let primary: React.ReactNode = null;

  if (v.status === "ready_for_review") {
    primary = <Link href={`/videos/${v.id}`} className="text-xs text-blue-600 hover:underline">Review transcript →</Link>;
  } else if (v.status === "reviewed") {
    primary = (
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
  } else if (v.status === "phase1_ready_for_review") {
    primary = <Link href={`/videos/${v.id}/phase1`} className="text-xs text-purple-600 hover:underline">Review narrative →</Link>;
  } else if (v.status === "phase2_ready_for_review") {
    primary = <Link href={`/videos/${v.id}/phase2`} className="text-xs text-violet-600 hover:underline">Review quotes →</Link>;
  } else if (v.status === "phase1_reviewed") {
    primary = (
      <button
        onClick={async () => {
          setLoading(true);
          try {
            await rerunVideo(v.id);
            await onRefreshVideo(v.id);
          } finally {
            setLoading(false);
          }
        }}
        disabled={loading}
        className="text-xs text-purple-600 hover:underline disabled:opacity-50"
      >
        {loading ? "Re-running…" : "Re-run Phase 1 →"}
      </button>
    );
  } else if (v.status === "phase2_reviewed") {
    primary = (
      <button
        onClick={async () => {
          setLoading(true);
          try {
            await rerunVideo(v.id);
            await onRefreshVideo(v.id);
          } finally {
            setLoading(false);
          }
        }}
        disabled={loading}
        className="text-xs text-violet-600 hover:underline disabled:opacity-50"
      >
        {loading ? "Re-running…" : "Re-run Phase 2 →"}
      </button>
    );
  } else if (v.status === "failed") {
    primary = (
      <button
        onClick={async () => {
          setLoading(true);
          try {
            await retryVideo(v.id);
            await onRefreshVideo(v.id);
          } finally {
            setLoading(false);
          }
        }}
        disabled={loading}
        className="text-xs text-orange-600 hover:underline disabled:opacity-50"
      >
        {loading ? "Retrying…" : "Retry →"}
      </button>
    );
  }

  if (!primary && !showRerunTranscript) return null;

  return (
    <div className="flex items-center gap-3">
      {showRerunTranscript && <RerunTranscriptButton id={v.id} onRefreshVideo={onRefreshVideo} />}
      {primary}
    </div>
  );
}

export default function VideoList({ videos, onRefreshVideo }: Props) {
  if (videos.length === 0) {
    return <p className="text-gray-400 text-sm mt-6">No files uploaded yet.</p>;
  }

  return (
    <ul className="mt-6 space-y-2" data-testid="video-list">
      {videos.map((v) => (
        <li key={v.id} className="bg-white border border-gray-200 rounded-lg px-4 py-3 flex items-center justify-between">
          <div className="min-w-0">
            <p className="font-medium text-sm truncate" title={v.original_filename}>{v.original_filename}</p>
            <p className="text-xs text-gray-400 mt-0.5">
              {v.media_type} {v.duration_seconds ? `· ${Math.round(v.duration_seconds / 60)} min` : ""}
            </p>
            {v.status === "failed" && v.error_reason && (
              <p className="text-xs text-red-500 mt-0.5 truncate" title={v.error_reason}>
                {v.error_reason}
              </p>
            )}
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
