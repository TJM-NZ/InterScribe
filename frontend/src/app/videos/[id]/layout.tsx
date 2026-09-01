"use client";

import { use, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { getVideo, type VideoStatus, type VideoSummary } from "@/lib/api";

const STATUS_ORDER: VideoStatus[] = [
  "uploaded", "queued", "transcribing",
  "ready_for_review",
  "phase1_queued", "phase1_processing", "phase1_ready_for_review", "phase1_reviewed",
  "phase2_queued", "phase2_processing", "phase2_ready_for_review", "phase2_reviewed",
  "condensation_queued", "condensation_processing",
  "condensation_ready_for_review", "condensation_reviewed",
];

function phaseTabsFor(status: VideoStatus) {
  const idx = STATUS_ORDER.indexOf(status);
  const at = (s: VideoStatus) => idx >= STATUS_ORDER.indexOf(s);
  return {
    transcript: at("ready_for_review"),
    narrative: at("phase1_ready_for_review"),
    quotes: at("phase2_ready_for_review"),
    condensation: at("condensation_ready_for_review"),
  };
}

function TabLink({
  href,
  active,
  enabled,
  children,
}: {
  href: string;
  active: boolean;
  enabled: boolean;
  children: React.ReactNode;
}) {
  const base = "px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap";
  if (!enabled) {
    return (
      <span className={`${base} border-transparent text-gray-300 cursor-not-allowed select-none`}>
        {children}
      </span>
    );
  }
  return (
    <Link
      href={href}
      className={`${base} ${
        active
          ? "border-blue-600 text-blue-600"
          : "border-transparent text-gray-500 hover:text-gray-900 hover:border-gray-300"
      }`}
    >
      {children}
    </Link>
  );
}

export default function VideoLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const pathname = usePathname();
  const [video, setVideo] = useState<VideoSummary | null>(null);

  useEffect(() => {
    getVideo(id).then(setVideo).catch(() => {});
  }, [id]);

  const tabs = video
    ? phaseTabsFor(video.status)
    : { transcript: false, narrative: false, quotes: false, condensation: false };

  const isTranscript = pathname === `/videos/${id}`;
  const isPhase1 = pathname === `/videos/${id}/phase1`;
  const isPhase2 = pathname === `/videos/${id}/phase2`;
  const isCondensation = pathname === `/videos/${id}/condensation`;

  return (
    <div>
      <div className="mb-5">
        <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">
          ← All files
        </Link>
      </div>

      {video && (
        <div className="mb-4">
          <h2 className="text-lg font-semibold break-all">{video.original_filename}</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            {video.media_type}
            {video.duration_seconds ? ` · ${Math.round(video.duration_seconds / 60)} min` : ""}
          </p>
        </div>
      )}

      <div className="border-b border-gray-200 mb-6">
        <nav className="flex">
          <TabLink href={`/videos/${id}`} active={isTranscript} enabled={tabs.transcript}>
            Transcript
          </TabLink>
          <TabLink href={`/videos/${id}/phase1`} active={isPhase1} enabled={tabs.narrative}>
            Narrative
          </TabLink>
          <TabLink href={`/videos/${id}/phase2`} active={isPhase2} enabled={tabs.quotes}>
            Quotes
          </TabLink>
          <TabLink href={`/videos/${id}/condensation`} active={isCondensation} enabled={tabs.condensation}>
            Headlines
          </TabLink>
        </nav>
      </div>

      {children}
    </div>
  );
}
