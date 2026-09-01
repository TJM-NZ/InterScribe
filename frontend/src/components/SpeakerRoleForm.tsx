<<<<<<< Updated upstream
"use client";

import { useState } from "react";
import { assignSpeakers, extractApiError, type SpeakerRole } from "@/lib/api";

const ROLES: { value: SpeakerRole; label: string }[] = [
  { value: "interviewer", label: "Interviewer" },
  { value: "interviewee", label: "Interviewee" },
  { value: "unknown", label: "Unknown" },
];

interface Props {
  videoId: string;
  speakerLabels: string[];
  initialRoles?: Record<string, SpeakerRole>;
  initialNames?: Record<string, string>;
  onSaved: (roles: Record<string, SpeakerRole>, names: Record<string, string>) => void;
}

export default function SpeakerRoleForm({ videoId, speakerLabels, initialRoles = {}, initialNames = {}, onSaved }: Props) {
  const [roles, setRoles] = useState<Record<string, SpeakerRole>>(() => {
    const init: Record<string, SpeakerRole> = {};
    for (const label of speakerLabels) {
      init[label] = initialRoles[label] ?? "unknown";
    }
    return init;
  });
  const [names, setNames] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const label of speakerLabels) {
      init[label] = initialNames[label] ?? "";
    }
    return init;
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await assignSpeakers(
        videoId,
        speakerLabels.map((label) => ({
          speaker_label: label,
          role: roles[label],
          name: names[label] || null,
        }))
      );
      onSaved(roles, names);
    } catch (err: unknown) {
      setError(extractApiError(err, "Failed to save roles"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} data-testid="speaker-role-form">
      <div className="space-y-3">
        {speakerLabels.map((label) => (
          <div key={label} className="flex items-center gap-3">
            <span className="text-sm font-medium w-32 shrink-0">{label}</span>
            <input
              type="text"
              value={names[label]}
              onChange={(e) => setNames((n) => ({ ...n, [label]: e.target.value }))}
              placeholder="Name (optional)"
              className="border border-gray-300 rounded px-2 py-1 text-sm w-40"
              data-testid={`name-input-${label}`}
            />
            <select
              value={roles[label]}
              onChange={(e) => setRoles((r) => ({ ...r, [label]: e.target.value as SpeakerRole }))}
              className="border border-gray-300 rounded px-2 py-1 text-sm"
              data-testid={`role-select-${label}`}
            >
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </div>
        ))}
      </div>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      <button
        type="submit"
        disabled={saving}
        className="mt-4 px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50"
        data-testid="save-roles-button"
      >
        {saving ? "Saving…" : "Save speaker roles"}
      </button>
    </form>
  );
}
=======
"use client";

import { useState } from "react";
import { assignSpeakers, extractApiError, type SpeakerRole } from "@/lib/api";

const ROLES: { value: SpeakerRole; label: string }[] = [
  { value: "interviewer", label: "Interviewer" },
  { value: "interviewee", label: "Interviewee" },
  { value: "unknown", label: "Unknown" },
];

interface Props {
  videoId: string;
  speakerLabels: string[];
  initialRoles?: Record<string, SpeakerRole>;
  onSaved: (roles: Record<string, SpeakerRole>) => void;
}

export default function SpeakerRoleForm({ videoId, speakerLabels, initialRoles = {}, onSaved }: Props) {
  const [roles, setRoles] = useState<Record<string, SpeakerRole>>(
    () => {
      const init: Record<string, SpeakerRole> = {};
      for (const label of speakerLabels) {
        init[label] = initialRoles[label] ?? "unknown";
      }
      return init;
    }
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await assignSpeakers(
        videoId,
        speakerLabels.map((label) => ({ speaker_label: label, role: roles[label] }))
      );
      onSaved(roles);
    } catch (err: unknown) {
      setError(extractApiError(err, "Failed to save roles"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} data-testid="speaker-role-form">
      <div className="space-y-3">
        {speakerLabels.map((label) => (
          <div key={label} className="flex items-center gap-3">
            <span className="text-sm font-medium w-32 shrink-0">{label}</span>
            <select
              value={roles[label]}
              onChange={(e) => setRoles((r) => ({ ...r, [label]: e.target.value as SpeakerRole }))}
              className="border border-gray-300 rounded px-2 py-1 text-sm"
              data-testid={`role-select-${label}`}
            >
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </div>
        ))}
      </div>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      <button
        type="submit"
        disabled={saving}
        className="mt-4 px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50"
        data-testid="save-roles-button"
      >
        {saving ? "Saving…" : "Save speaker roles"}
      </button>
    </form>
  );
}
>>>>>>> Stashed changes
