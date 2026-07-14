"use client";

import Link from "next/link";
import type { VideoSummary } from "@/lib/api";

const STATUS_LABELS: Record<VideoSummary["status"], string> = {
  uploaded: "Uploaded",
  queued: "Queued",
  transcribing: "Transcribing…",
  ready_for_review: "Ready for review",
  reviewed: "Reviewed",
  failed: "Failed",
};

const STATUS_COLORS: Record<VideoSummary["status"], string> = {
  uploaded: "bg-gray-100 text-gray-600",
  queued: "bg-yellow-100 text-yellow-700",
  transcribing: "bg-blue-100 text-blue-700",
  ready_for_review: "bg-green-100 text-green-700",
  reviewed: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
};

interface Props {
  videos: VideoSummary[];
}

export default function VideoList({ videos }: Props) {
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
            {(v.status === "ready_for_review" || v.status === "reviewed") && (
              <Link
                href={`/videos/${v.id}`}
                className="text-xs text-blue-600 hover:underline"
              >
                Review →
              </Link>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
