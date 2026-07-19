"use client";

import { use, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  confirmReview,
  extractApiError,
  getTranscript,
  getVideo,
  type SpeakerRole,
  type TranscriptSegment,
  type VideoSummary,
} from "@/lib/api";
import TranscriptViewer from "@/components/TranscriptViewer";
import SpeakerRoleForm from "@/components/SpeakerRoleForm";

export default function ReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();

  const [video, setVideo] = useState<VideoSummary | null>(null);
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [speakerRoles, setSpeakerRoles] = useState<Record<string, SpeakerRole>>({});
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [v, t] = await Promise.all([getVideo(id), getTranscript(id)]);
        setVideo(v);
        setSegments(t.segments);
      } catch (err: unknown) {
        setError(extractApiError(err, "Failed to load review"));
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  const distinctSpeakers = [...new Set(segments.map((s) => s.speaker_label))].sort();

  const handleConfirm = async () => {
    setConfirming(true);
    setError(null);
    try {
      await confirmReview(id);
      router.push("/");
    } catch (err: unknown) {
      setError(extractApiError(err, "Failed to confirm review"));
      setConfirming(false);
    }
  };

  if (loading) return <p className="text-gray-400">Loading…</p>;
  if (error && !video) return <p className="text-red-600">{error}</p>;
  if (!video) return null;

  const allMapped = distinctSpeakers.every((label) => !!speakerRoles[label]);

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-lg font-semibold break-all">{video.original_filename}</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          {video.media_type} · {video.duration_seconds ? `${Math.round(video.duration_seconds / 60)} min` : "unknown duration"}
        </p>
      </div>

      <section>
        <h3 className="text-base font-medium mb-3">Speaker roles</h3>
        <SpeakerRoleForm
          videoId={id}
          speakerLabels={distinctSpeakers}
          initialRoles={speakerRoles}
          onSaved={(roles) => setSpeakerRoles(roles)}
        />
      </section>

      <section>
        <h3 className="text-base font-medium mb-3">
          Transcript
          <span className="ml-2 text-xs font-normal text-amber-600">
            Segments highlighted in amber have low transcription confidence (&lt;70%)
          </span>
        </h3>
        <TranscriptViewer segments={segments} speakerRoles={speakerRoles} />
      </section>

      <div className="border-t border-gray-200 pt-6">
        {error && <p className="mb-3 text-sm text-red-600">{error}</p>}
        <button
          onClick={handleConfirm}
          disabled={confirming || !allMapped || video.status !== "ready_for_review"}
          className="px-5 py-2 bg-emerald-600 text-white text-sm rounded hover:bg-emerald-700 disabled:opacity-40"
          data-testid="confirm-review-button"
        >
          {video.status !== "ready_for_review"
            ? "Review complete"
            : confirming
            ? "Confirming…"
            : "Confirm review"}
        </button>
        {!allMapped && (
          <p className="mt-2 text-xs text-gray-500">
            Assign a role to all speakers before confirming.
          </p>
        )}
      </div>
    </div>
  );
}
