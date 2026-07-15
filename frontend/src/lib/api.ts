const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface VideoSummary {
  id: string;
  status: "uploaded" | "queued" | "transcribing" | "ready_for_review" | "reviewed" | "failed";
  original_filename: string;
  media_type: "video" | "audio";
  duration_seconds: number | null;
  error_reason: string | null;
  uploaded_at: string;
}

export interface TranscriptSegment {
  id: string;
  video_id: string;
  segment_id: number;
  start_ts: number;
  end_ts: number;
  text: string;
  speaker_label: string;
  confidence: number;
}

export interface SpeakerRoleEntry {
  id: string;
  video_id: string;
  speaker_label: string;
  role: "interviewer" | "interviewee" | "unknown";
}

export type SpeakerRole = "interviewer" | "interviewee" | "unknown";

export async function listVideos(): Promise<VideoSummary[]> {
  const res = await fetch(`${API_BASE}/api/videos`);
  if (!res.ok) throw await res.json();
  const data = await res.json();
  return data.videos;
}

export async function uploadVideo(file: File): Promise<{ id: string; status: string; original_filename: string; media_type: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/videos`, { method: "POST", body: form });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function getVideo(id: string): Promise<VideoSummary> {
  const res = await fetch(`${API_BASE}/api/videos/${id}`);
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function getTranscript(id: string): Promise<{ segments: TranscriptSegment[] }> {
  const res = await fetch(`${API_BASE}/api/videos/${id}/transcript`);
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function assignSpeakers(
  id: string,
  assignments: { speaker_label: string; role: SpeakerRole }[]
): Promise<{ video_id: string; speaker_role_map: SpeakerRoleEntry[] }> {
  const res = await fetch(`${API_BASE}/api/videos/${id}/speakers`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ assignments }),
  });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function confirmReview(id: string): Promise<{ video_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/api/videos/${id}/confirm-review`, { method: "POST" });
  if (!res.ok) throw await res.json();
  return res.json();
}
