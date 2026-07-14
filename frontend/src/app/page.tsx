"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getVideo, type VideoSummary } from "@/lib/api";
import UploadForm from "@/components/UploadForm";
import VideoList from "@/components/VideoList";

const POLLING_INTERVAL_MS = 4000;
const IN_PROGRESS_STATUSES = new Set(["uploaded", "queued", "transcribing"]);

export default function HomePage() {
  const [videos, setVideos] = useState<VideoSummary[]>([]);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshVideo = useCallback(async (id: string) => {
    try {
      const updated = await getVideo(id);
      setVideos((prev) =>
        prev.map((v) => (v.id === id ? updated : v))
      );
      return updated;
    } catch {
      return null;
    }
  }, []);

  const startPolling = useCallback(
    (id: string) => {
      pollingRef.current = setInterval(async () => {
        const updated = await refreshVideo(id);
        if (updated && !IN_PROGRESS_STATUSES.has(updated.status)) {
          if (pollingRef.current) clearInterval(pollingRef.current);
        }
      }, POLLING_INTERVAL_MS);
    },
    [refreshVideo]
  );

  const handleUploaded = useCallback(
    async (id: string) => {
      const video = await getVideo(id);
      setVideos((prev) => [video, ...prev]);
      startPolling(id);
    },
    [startPolling]
  );

  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">Upload a file</h2>
      <UploadForm onUploaded={handleUploaded} />
      <h2 className="text-lg font-semibold mt-8 mb-2">Recent uploads</h2>
      <VideoList videos={videos} />
    </div>
  );
}
