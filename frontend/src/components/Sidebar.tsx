"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { getVideo, type VideoStatus, type VideoSummary } from "@/lib/api";

const CURRENT_VERSION = "1.0.0";
const RELEASES_API = "https://api.github.com/repos/TJM-NZ/InterScribe/releases/latest";
const RELEASES_PAGE = "https://github.com/TJM-NZ/InterScribe/releases/latest";

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

function NavItem({
  href,
  active,
  disabled,
  children,
}: {
  href: string;
  active: boolean;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  const base = "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors w-full text-left";
  if (disabled) {
    return (
      <span className={`${base} text-gray-300 cursor-not-allowed select-none`}>
        {children}
      </span>
    );
  }
  return (
    <Link
      href={href}
      className={`${base} ${
        active
          ? "bg-gray-100 text-gray-900"
          : "text-gray-500 hover:bg-gray-50 hover:text-gray-900"
      }`}
    >
      {children}
    </Link>
  );
}

function UpdateBanner({ latestVersion }: { latestVersion: string }) {
  const [updating, setUpdating] = useState(false);

  async function handleClick() {
    setUpdating(true);
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);
      const res = await fetch("http://localhost:8003/trigger-update", {
        method: "POST",
        signal: controller.signal,
      });
      clearTimeout(timeout);
      const data = await res.json();
      if (!res.ok || data.fallback) throw new Error("fallback");
      // Tray app is handling the silent install — stay in updating state.
    } catch {
      // Tray not running or no asset — open releases page.
      window.open(RELEASES_PAGE, "_blank", "noreferrer");
      setUpdating(false);
    }
  }

  return (
    <button
      onClick={handleClick}
      disabled={updating}
      className="block mx-3 mb-3 p-3 rounded-lg bg-blue-50 border border-blue-100 hover:bg-blue-100 transition-colors group w-[calc(100%-1.5rem)] text-left disabled:opacity-70 disabled:cursor-wait"
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-blue-700">
          {updating ? "Installing…" : "Update available"}
        </span>
        {!updating && (
          <svg className="w-3.5 h-3.5 text-blue-500 group-hover:translate-x-0.5 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        )}
      </div>
      <p className="text-xs text-blue-600 mt-0.5">
        {updating ? "Starting installer…" : `v${latestVersion} is ready`}
      </p>
    </button>
  );
}

export default function Sidebar() {
  const pathname = usePathname();
  const [video, setVideo] = useState<VideoSummary | null>(null);
  const [latestVersion, setLatestVersion] = useState<string | null>(null);

  // Extract video ID from pathname /videos/[id]/...
  const videoMatch = pathname.match(/^\/videos\/([^/]+)/);
  const videoId = videoMatch?.[1] ?? null;

  useEffect(() => {
    if (!videoId) {
      setVideo(null);
      return;
    }
    getVideo(videoId).then(setVideo).catch(() => {});
  }, [videoId]);

  useEffect(() => {
    fetch(RELEASES_API, { headers: { Accept: "application/vnd.github+json" } })
      .then((r) => r.json())
      .then((data) => {
        const tag: string = data?.tag_name ?? "";
        const match = tag.match(/^v?(\d+\.\d+\.\d+)/);
        if (!match) return;
        const latest = match[1];
        const [lMaj, lMin, lPat] = latest.split(".").map(Number);
        const [cMaj, cMin, cPat] = CURRENT_VERSION.split(".").map(Number);
        const isNewer =
          lMaj > cMaj ||
          (lMaj === cMaj && lMin > cMin) ||
          (lMaj === cMaj && lMin === cMin && lPat > cPat);
        if (isNewer) setLatestVersion(latest);
      })
      .catch(() => {});
  }, []);

  const tabs = video ? phaseTabsFor(video.status) : null;

  const isHome = pathname === "/";
  const isTranscript = videoId ? pathname === `/videos/${videoId}` : false;
  const isPhase1 = videoId ? pathname === `/videos/${videoId}/phase1` : false;
  const isPhase2 = videoId ? pathname === `/videos/${videoId}/phase2` : false;
  const isCondensation = videoId ? pathname === `/videos/${videoId}/condensation` : false;

  return (
    <aside className="flex flex-col w-60 shrink-0 h-screen sticky top-0 bg-white border-r border-gray-200">
      {/* Logo */}
      <div className="px-4 py-4 border-b border-gray-100">
        <Link href="/" className="flex items-center gap-2 group">
          <div className="w-7 h-7 rounded-md bg-blue-600 flex items-center justify-center shrink-0">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
            </svg>
          </div>
          <span className="text-sm font-semibold text-gray-900 group-hover:text-blue-600 transition-colors">
            InterScribe
          </span>
        </Link>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-0.5">
        <NavItem href="/" active={isHome}>
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
          </svg>
          Library
        </NavItem>

        {/* Video sub-nav */}
        {videoId && (
          <div className="pt-3">
            <div className="px-3 pb-1.5">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider truncate">
                {video?.original_filename ?? "Loading…"}
              </p>
              {video && (
                <p className="text-xs text-gray-400 mt-0.5">
                  {video.media_type}
                  {video.duration_seconds ? ` · ${Math.round(video.duration_seconds / 60)} min` : ""}
                </p>
              )}
            </div>
            <div className="space-y-0.5">
              <NavItem href={`/videos/${videoId}`} active={isTranscript} disabled={!tabs?.transcript}>
                <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                Transcript
              </NavItem>
              <NavItem href={`/videos/${videoId}/phase1`} active={isPhase1} disabled={!tabs?.narrative}>
                <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
                </svg>
                Narrative
              </NavItem>
              <NavItem href={`/videos/${videoId}/phase2`} active={isPhase2} disabled={!tabs?.quotes}>
                <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-3 3v-3z" />
                </svg>
                Quotes
              </NavItem>
              <NavItem href={`/videos/${videoId}/condensation`} active={isCondensation} disabled={!tabs?.condensation}>
                <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z" />
                </svg>
                Headlines
              </NavItem>
            </div>
          </div>
        )}
      </nav>

      {/* Update banner */}
      {latestVersion && <UpdateBanner latestVersion={latestVersion} />}

      {/* Version footer */}
      <div className="px-4 py-2.5 border-t border-gray-100">
        <p className="text-xs text-gray-300">v{CURRENT_VERSION}</p>
      </div>
    </aside>
  );
}
