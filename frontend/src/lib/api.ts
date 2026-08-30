// Empty base = relative URLs, routed by nginx. Set NEXT_PUBLIC_API_URL for dev without Docker.
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  return fetch(url, init);
}

export function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function extractApiError(err: unknown, fallback: string): string {
  return (err as { detail?: { error?: string } })?.detail?.error ?? fallback;
}

export type VideoStatus =
  | "uploaded"
  | "queued"
  | "transcribing"
  | "ready_for_review"
  | "phase1_queued"
  | "phase1_processing"
  | "phase1_ready_for_review"
  | "phase1_reviewed"
  | "phase2_queued"
  | "phase2_processing"
  | "phase2_ready_for_review"
  | "phase2_reviewed"
  | "condensation_queued"
  | "condensation_processing"
  | "condensation_ready_for_review"
  | "condensation_reviewed"
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
  name: string | null;
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

export type CorrectionEntityType = "transcript_segment" | "narrative_cluster" | "notable_moment" | "quote" | "headline_condensation";

export type ReasonCategory =
  | "model_error"
  | "ambiguous_input"
  | "edge_case"
  | "preference";

export interface Phase1Narrative {
  clusters: NarrativeCluster[];
  notable_moments: NotableMoment[];
}

export type QuoteType = "headline" | "substantive";

export interface Quote {
  id: string;
  video_id: string;
  start_segment_id: number;
  end_segment_id: number;
  start_ts: number;
  end_ts: number;
  quote_text: string;
  headline_text: string | null;
  speaker_label: string;
  quote_type: QuoteType;
  narrative_alignment_score: number;
  is_notable_moment: boolean;
  notable_moment_id: string | null;
  source_candidate_ids: string[];
  reviewed: boolean;
}

export async function listVideos(): Promise<VideoSummary[]> {
  const res = await apiFetch(`${API_BASE}/api/videos`);
  if (!res.ok) throw await res.json();
  const data = await res.json();
  return data.videos;
}

export async function uploadVideo(file: File): Promise<{ id: string; status: string; original_filename: string; media_type: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await apiFetch(`${API_BASE}/api/videos`, { method: "POST", body: form });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function getVideo(id: string): Promise<VideoSummary> {
  const res = await apiFetch(`${API_BASE}/api/videos/${id}`);
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function getTranscript(id: string): Promise<{ segments: TranscriptSegment[] }> {
  const res = await apiFetch(`${API_BASE}/api/videos/${id}/transcript`);
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function assignSpeakers(
  id: string,
  assignments: { speaker_label: string; role: SpeakerRole; name?: string | null }[]
): Promise<{ video_id: string; speaker_role_map: SpeakerRoleEntry[] }> {
  const res = await apiFetch(`${API_BASE}/api/videos/${id}/speakers`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ assignments }),
  });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function confirmReview(id: string): Promise<{ video_id: string; status: string }> {
  const res = await apiFetch(`${API_BASE}/api/videos/${id}/confirm-review`, { method: "POST" });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function getPhase1Narrative(id: string): Promise<Phase1Narrative> {
  const res = await apiFetch(`${API_BASE}/api/videos/${id}/phase1/narrative`);
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function logTranscriptCorrection(
  videoId: string,
  payload: {
    segment_id: string;
    corrected_text: string;
    reason_category: ReasonCategory;
    reason_note: string | null;
  }
): Promise<{ correction_id: string }> {
  const res = await apiFetch(`${API_BASE}/api/videos/${videoId}/transcript/corrections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function logTranscriptSpeakerCorrection(
  videoId: string,
  payload: {
    segment_id: string;
    corrected_speaker_label: string;
    reason_category: ReasonCategory;
    reason_note: string | null;
  }
): Promise<{ correction_id: string }> {
  const res = await apiFetch(`${API_BASE}/api/videos/${videoId}/transcript/speaker-corrections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function mergeSegments(
  videoId: string,
  segmentId: string
): Promise<{ merged_segment: TranscriptSegment; removed_segment_id: string }> {
  const res = await apiFetch(`${API_BASE}/api/videos/${videoId}/transcript/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ segment_id: segmentId }),
  });
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
  const res = await apiFetch(`${API_BASE}/api/videos/${videoId}/phase1/corrections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function confirmPhase1Review(id: string): Promise<{ video_id: string; status: string }> {
  const res = await apiFetch(`${API_BASE}/api/videos/${id}/phase1/confirm-review`, {
    method: "POST",
  });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function retryVideo(id: string): Promise<{ video_id: string; status: string }> {
  const res = await apiFetch(`${API_BASE}/api/videos/${id}/retry`, { method: "POST" });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function rerunVideo(id: string): Promise<{ video_id: string; status: string }> {
  const res = await apiFetch(`${API_BASE}/api/videos/${id}/rerun`, { method: "POST" });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function rerunTranscript(id: string): Promise<{ video_id: string; status: string }> {
  const res = await apiFetch(`${API_BASE}/api/videos/${id}/rerun-transcript`, { method: "POST" });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function getPhase2Quotes(
  id: string,
  view: "notable" | "top",
  limit?: number,
  type?: QuoteType
): Promise<{ quotes: Quote[] }> {
  const params = new URLSearchParams({ view });
  if (limit !== undefined) params.set("limit", String(limit));
  if (type !== undefined) params.set("type", type);
  const res = await apiFetch(`${API_BASE}/api/videos/${id}/phase2/quotes?${params}`);
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function logPhase2Correction(
  videoId: string,
  payload: {
    entity_type: "quote";
    entity_id: string;
    field_name: string | null;
    original_value: Record<string, unknown> | null;
    corrected_value: Record<string, unknown> | null;
    reason_category: ReasonCategory;
    reason_note: string | null;
  }
): Promise<{ correction_id: string }> {
  const res = await apiFetch(`${API_BASE}/api/videos/${videoId}/phase2/corrections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function confirmPhase2Review(id: string): Promise<{ video_id: string; status: string }> {
  const res = await apiFetch(`${API_BASE}/api/videos/${id}/phase2/confirm-review`, {
    method: "POST",
  });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function getCondensationHeadlines(id: string): Promise<{ quotes: Quote[] }> {
  const res = await apiFetch(`${API_BASE}/api/videos/${id}/condensation/headlines`);
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function logCondensationCorrection(
  videoId: string,
  payload: {
    entity_type: "headline_condensation";
    entity_id: string;
    field_name: string | null;
    original_value: Record<string, unknown> | null;
    corrected_value: Record<string, unknown> | null;
    reason_category: ReasonCategory;
    reason_note: string | null;
  }
): Promise<{ correction_id: string }> {
  const res = await apiFetch(`${API_BASE}/api/videos/${videoId}/condensation/corrections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw await res.json();
  return res.json();
}

export async function confirmCondensationReview(id: string): Promise<{ video_id: string; status: string }> {
  const res = await apiFetch(`${API_BASE}/api/videos/${id}/condensation/confirm-review`, {
    method: "POST",
  });
  if (!res.ok) throw await res.json();
  return res.json();
}
