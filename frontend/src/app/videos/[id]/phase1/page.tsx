"use client";

import { use, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  confirmPhase1Review,
  getPhase1Narrative,
  getVideo,
  logCorrection,
  type NarrativeCluster,
  type NotableMoment,
  type Phase1Narrative,
  type ReasonCategory,
  type VideoSummary,
} from "@/lib/api";
import NarrativeClusterCard from "@/components/NarrativeClusterCard";
import NotableMomentCard from "@/components/NotableMomentCard";
import CorrectionModal from "@/components/CorrectionModal";

type ModalState =
  | { kind: "edit-cluster"; cluster: NarrativeCluster }
  | { kind: "reject-cluster"; cluster: NarrativeCluster }
  | { kind: "edit-moment"; moment: NotableMoment }
  | { kind: "reject-moment"; moment: NotableMoment }
  | null;

export default function Phase1ReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();

  const [video, setVideo] = useState<VideoSummary | null>(null);
  const [narrative, setNarrative] = useState<Phase1Narrative | null>(null);
  const [modal, setModal] = useState<ModalState>(null);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [v, n] = await Promise.all([getVideo(id), getPhase1Narrative(id)]);
        setVideo(v);
        setNarrative(n);
      } catch (err: unknown) {
        const detail = (err as { detail?: { error?: string } })?.detail;
        setError(detail?.error ?? "Failed to load Phase 1 review");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  const refreshNarrative = useCallback(async () => {
    const n = await getPhase1Narrative(id);
    setNarrative(n);
  }, [id]);

  const handleClusterEdit = async ({
    correctedValue,
    reasonCategory,
    reasonNote,
  }: {
    correctedValue: string | null;
    reasonCategory: ReasonCategory;
    reasonNote: string;
  }) => {
    if (modal?.kind !== "edit-cluster") return;
    const cluster = modal.cluster;
    await logCorrection(id, {
      entity_type: "narrative_cluster",
      entity_id: cluster.id,
      field_name: "representative_label",
      original_value: { representative_label: cluster.representative_label },
      corrected_value: correctedValue ? { representative_label: correctedValue } : null,
      reason_category: reasonCategory,
      reason_note: reasonNote || null,
    });
    await refreshNarrative();
  };

  const handleClusterReject = async ({
    reasonCategory,
    reasonNote,
  }: {
    correctedValue: string | null;
    reasonCategory: ReasonCategory;
    reasonNote: string;
  }) => {
    if (modal?.kind !== "reject-cluster") return;
    const cluster = modal.cluster;
    await logCorrection(id, {
      entity_type: "narrative_cluster",
      entity_id: cluster.id,
      field_name: null,
      original_value: { representative_label: cluster.representative_label },
      corrected_value: null,
      reason_category: reasonCategory,
      reason_note: reasonNote || null,
    });
  };

  const handleMomentEdit = async ({
    correctedValue,
    reasonCategory,
    reasonNote,
  }: {
    correctedValue: string | null;
    reasonCategory: ReasonCategory;
    reasonNote: string;
  }) => {
    if (modal?.kind !== "edit-moment") return;
    const moment = modal.moment;
    await logCorrection(id, {
      entity_type: "notable_moment",
      entity_id: moment.id,
      field_name: "description",
      original_value: { description: moment.description },
      corrected_value: correctedValue ? { description: correctedValue } : null,
      reason_category: reasonCategory,
      reason_note: reasonNote || null,
    });
    await refreshNarrative();
  };

  const handleMomentReject = async ({
    reasonCategory,
    reasonNote,
  }: {
    correctedValue: string | null;
    reasonCategory: ReasonCategory;
    reasonNote: string;
  }) => {
    if (modal?.kind !== "reject-moment") return;
    const moment = modal.moment;
    await logCorrection(id, {
      entity_type: "notable_moment",
      entity_id: moment.id,
      field_name: null,
      original_value: { description: moment.description },
      corrected_value: null,
      reason_category: reasonCategory,
      reason_note: reasonNote || null,
    });
    await refreshNarrative();
  };

  const handleConfirm = async () => {
    setConfirming(true);
    setError(null);
    try {
      await confirmPhase1Review(id);
      router.push("/");
    } catch (err: unknown) {
      const detail = (err as { detail?: { error?: string } })?.detail;
      setError(detail?.error ?? "Failed to confirm review");
      setConfirming(false);
    }
  };

  const isReviewed = video?.status === "phase1_reviewed";
  const canConfirm = video?.status === "phase1_ready_for_review";

  if (loading) return <p className="text-gray-400">Loading…</p>;
  if (error && !video) return <p className="text-red-600">{error}</p>;
  if (!video || !narrative) return null;

  return (
    <div className="space-y-10">
      <div>
        <h2 className="text-lg font-semibold">{video.original_filename}</h2>
        <p className="text-sm text-gray-500 mt-0.5">Phase 1 narrative review</p>
      </div>

      <section>
        <h3 className="text-base font-medium mb-3">
          Narrative clusters
          <span className="ml-2 text-xs font-normal text-gray-500">
            ranked by frequency — most dominant theme first
          </span>
        </h3>
        {narrative.clusters.length === 0 ? (
          <p className="text-sm text-gray-400">No clusters found.</p>
        ) : (
          <div className="space-y-3" data-testid="cluster-list">
            {narrative.clusters.map((cluster) => (
              <NarrativeClusterCard
                key={cluster.id}
                cluster={cluster}
                disabled={isReviewed}
                onEdit={(c) => setModal({ kind: "edit-cluster", cluster: c })}
                onReject={(c) => setModal({ kind: "reject-cluster", cluster: c })}
              />
            ))}
          </div>
        )}
      </section>

      <section>
        <h3 className="text-base font-medium mb-3">
          Notable moments
          <span className="ml-2 text-xs font-normal text-gray-500">
            chronological — all moments shown, amber = not yet reviewed
          </span>
        </h3>
        {narrative.notable_moments.length === 0 ? (
          <p className="text-sm text-gray-400">No notable moments found.</p>
        ) : (
          <div className="space-y-3" data-testid="moments-list">
            {narrative.notable_moments.map((moment) => (
              <NotableMomentCard
                key={moment.id}
                moment={moment}
                disabled={isReviewed}
                onEdit={(m) => setModal({ kind: "edit-moment", moment: m })}
                onReject={(m) => setModal({ kind: "reject-moment", moment: m })}
              />
            ))}
          </div>
        )}
      </section>

      <div className="border-t border-gray-200 pt-6">
        {error && <p className="mb-3 text-sm text-red-600">{error}</p>}
        <button
          onClick={handleConfirm}
          disabled={confirming || !canConfirm}
          className="px-5 py-2 bg-emerald-600 text-white text-sm rounded hover:bg-emerald-700 disabled:opacity-40"
          data-testid="confirm-phase1-review-button"
        >
          {isReviewed
            ? "Review complete"
            : confirming
            ? "Confirming…"
            : "Confirm Phase 1 review"}
        </button>
      </div>

      {modal && (
        <CorrectionModal
          title={
            modal.kind === "edit-cluster"
              ? "Edit narrative label"
              : modal.kind === "reject-cluster"
              ? "Reject narrative cluster"
              : modal.kind === "edit-moment"
              ? "Edit notable moment"
              : "Reject notable moment"
          }
          editMode={modal.kind === "edit-cluster" || modal.kind === "edit-moment"}
          currentValue={
            modal.kind === "edit-cluster"
              ? modal.cluster.representative_label
              : modal.kind === "edit-moment"
              ? modal.moment.description
              : ""
          }
          onSubmit={
            modal.kind === "edit-cluster"
              ? handleClusterEdit
              : modal.kind === "reject-cluster"
              ? handleClusterReject
              : modal.kind === "edit-moment"
              ? handleMomentEdit
              : handleMomentReject
          }
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}
