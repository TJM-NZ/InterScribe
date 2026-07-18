const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type VideoStatus =
  | "uploaded"
  | "queued"
  | "transcribing"
  | "ready_for_review"
  | "reviewed"
  | "phase1_queued"
  | "phase1_processing"
  | "phase1_ready_for_review"
  | "phase1_reviewed"
  | "phase2_queued"
  | "phase2_processing"
  | "phase2_ready_for_review"
  | "phase2_reviewed"
  | "failed";

export interface VideoSummary {
  id: string;
  status: VideoStatus;
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
  repetition_flagged: boolean;
}

export interface SpeakerRoleEntry {
  id: string;
  video_id: string;
  speaker_label: string;
  role: "interviewer" | "interviewee" | "unknown";
}

export type SpeakerRole = "interviewer" | "interviewee" | "unknown";

export interface NarrativeCluster {
  id: string;
  video_id: string;
  representative_label: string;
  cluster_size: number;
  rank: number;
}

export interface NotableMoment {
  id: string;
  video_id: string;
  chunk_id: string;
  start_segment_id: number;
  end_segment_id: number;
  description: string;
  reviewed: boolean;
}

export type CorrectionEntityType = "narrative_cluster" | "notable_moment";

export type ReasonCategory =
  | "model_error"
  | "ambiguous_input"
  | "edge_case"
  | "preference";

export interface Phase1Narrative {
  clusters: NarrativeCluster[];
  notable_moments: NotableMoment[];
}

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

export async function getPhase1Narrative(id: string): Promise<Phase1Narrative> {
  const res = await fetch(`${API_BASE}/api/videos/${id}/phase1/narrative`);
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function logCorrection(
  videoId: string,
  payload: {
    entity_type: CorrectionEntityType;
    entity_id: string;
    field_name: string | null;
    original_value: Record<string, unknown> | null;
    corrected_value: Record<string, unknown> | null;
    reason_category: ReasonCategory;
    reason_note: string | null;
  }
): Promise<{ correction_id: string }> {
  const res = await fetch(`${API_BASE}/api/videos/${videoId}/phase1/corrections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function enqueuePhase1(id: string): Promise<{ video_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/api/videos/${id}/phase1/enqueue`, { method: "POST" });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function confirmPhase1Review(id: string): Promise<{ video_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/api/videos/${id}/phase1/confirm-review`, {
    method: "POST",
  });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function retryVideo(id: string): Promise<{ video_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/api/videos/${id}/retry`, { method: "POST" });
  if (!res.ok) throw await res.json();
  return res.json();
}
