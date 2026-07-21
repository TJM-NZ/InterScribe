"use client";

import { use, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  confirmCondensationReview,
  extractApiError,
  formatTimestamp,
  getCondensationHeadlines,
  getTranscript,
  getVideo,
  logCondensationCorrection,
  type Quote,
  type ReasonCategory,
  type TranscriptSegment,
  type VideoStatus,
  type VideoSummary,
} from "@/lib/api";
import CorrectionModal from "@/components/CorrectionModal";
import QuoteSegmentContext from "@/components/QuoteSegmentContext";

type ModalState =
  | { kind: "edit-headline"; quote: Quote }
  | { kind: "downgrade"; quote: Quote }
  | null;

function WordCount({ text }: { text: string }) {
  const count = text.trim() ? text.trim().split(/\s+/).length : 0;
  const over = count > 20;
  return (
    <span className={`text-xs tabular-nums ${over ? "text-red-500" : "text-gray-400"}`}>
      {count}/20 words
    </span>
  );
}

interface HeadlineCardProps {
  quote: Quote;
  disabled: boolean;
  onEdit: (q: Quote) => void;
  onDowngrade: (q: Quote) => void;
  segments: TranscriptSegment[];
}

function HeadlineCard({ quote, disabled, onEdit, onDowngrade, segments }: HeadlineCardProps) {
  return (
    <div
      className="border border-gray-200 rounded-lg p-4 space-y-3 bg-white"
      data-testid="headline-card"
    >
      <div className="space-y-1">
        <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">Headline</p>
        <div className="flex items-start gap-2">
          <p
            className="text-base font-medium text-gray-900 flex-1"
            data-testid="headline-text"
          >
            {quote.headline_text ?? (
              <span className="text-gray-300 italic">Not yet condensed</span>
            )}
          </p>
          {quote.headline_text && <WordCount text={quote.headline_text} />}
        </div>
      </div>

      <div className="space-y-1">
        <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">Verbatim quote</p>
        <p className="text-sm text-gray-600 leading-relaxed" data-testid="verbatim-text">
          {quote.quote_text}
        </p>
        <QuoteSegmentContext
          segments={segments}
          startSegmentId={quote.start_segment_id}
          endSegmentId={quote.end_segment_id}
        />
      </div>

      <div className="flex items-center gap-3 text-xs text-gray-400">
        <span>{quote.speaker_label}</span>
        <span>·</span>
        <span>{formatTimestamp(quote.start_ts)} – {formatTimestamp(quote.end_ts)}</span>
      </div>

      {!disabled && (
        <div className="flex gap-3 pt-1">
          <button
            onClick={() => onEdit(quote)}
            className="text-xs text-indigo-600 hover:underline"
            data-testid="edit-headline-button"
          >
            Edit headline
          </button>
          <button
            onClick={() => onDowngrade(quote)}
            className="text-xs text-red-600 hover:underline"
            data-testid="downgrade-button"
          >
            Downgrade to substantive
          </button>
        </div>
      )}
    </div>
  );
}

const PAST_CONDENSATION = new Set<VideoStatus>(["condensation_reviewed"]);

export default function CondensationReviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  const [video, setVideo] = useState<VideoSummary | null>(null);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [modal, setModal] = useState<ModalState>(null);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [v, headlinesData, transcriptData] = await Promise.all([
          getVideo(id),
          getCondensationHeadlines(id),
          getTranscript(id),
        ]);
        setVideo(v);
        setQuotes(headlinesData.quotes);
        setSegments(transcriptData.segments);
      } catch (err: unknown) {
        setError(extractApiError(err, "Failed to load headline review"));
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  const refreshQuotes = useCallback(async () => {
    const data = await getCondensationHeadlines(id);
    setQuotes(data.quotes);
  }, [id]);

  const handleHeadlineEdit = async ({
    correctedValue,
    reasonCategory,
    reasonNote,
  }: {
    correctedValue: string | null;
    reasonCategory: ReasonCategory;
    reasonNote: string;
  }) => {
    if (modal?.kind !== "edit-headline") return;
    const quote = modal.quote;
    await logCondensationCorrection(id, {
      entity_type: "headline_condensation",
      entity_id: quote.id,
      field_name: "headline_text",
      original_value: { headline_text: quote.headline_text },
      corrected_value: { headline_text: correctedValue },
      reason_category: reasonCategory,
      reason_note: reasonNote || null,
    });
    await refreshQuotes();
  };

  const handleDowngrade = async ({
    reasonCategory,
    reasonNote,
  }: {
    correctedValue: string | null;
    reasonCategory: ReasonCategory;
    reasonNote: string;
  }) => {
    if (modal?.kind !== "downgrade") return;
    const quote = modal.quote;
    await logCondensationCorrection(id, {
      entity_type: "headline_condensation",
      entity_id: quote.id,
      field_name: "quote_type",
      original_value: { quote_type: "headline" },
      corrected_value: { quote_type: "substantive" },
      reason_category: reasonCategory,
      reason_note: reasonNote || null,
    });
    await refreshQuotes();
  };

  const handleConfirm = async () => {
    setConfirming(true);
    setError(null);
    try {
      await confirmCondensationReview(id);
      router.push("/");
    } catch (err: unknown) {
      setError(extractApiError(err, "Failed to confirm headline review"));
      setConfirming(false);
    }
  };

  const isReviewed = video != null && PAST_CONDENSATION.has(video.status);
  const canConfirm = video?.status === "condensation_ready_for_review";

  if (loading) return <p className="text-gray-400">Loading…</p>;
  if (error && !video) return <p className="text-red-600">{error}</p>;
  if (!video) return null;

  return (
    <div className="space-y-8">
      <section>
        <h3 className="text-base font-medium mb-1">Headline condensation</h3>
        <p className="text-sm text-gray-500 mb-4">
          Review Qwen-condensed headlines. Edit inline or downgrade to substantive if the
          classification is wrong.
        </p>

        {quotes.length === 0 ? (
          <p className="text-sm text-gray-400">No headline quotes found.</p>
        ) : (
          <div className="space-y-4" data-testid="headline-list">
            {quotes.map((quote) => (
              <HeadlineCard
                key={quote.id}
                quote={quote}
                disabled={isReviewed}
                onEdit={(q) => setModal({ kind: "edit-headline", quote: q })}
                onDowngrade={(q) => setModal({ kind: "downgrade", quote: q })}
                segments={segments}
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
          data-testid="confirm-condensation-review-button"
        >
          {isReviewed
            ? "Review complete"
            : confirming
            ? "Confirming…"
            : "Confirm headline review"}
        </button>
      </div>

      {modal?.kind === "edit-headline" && (
        <CorrectionModal
          title="Edit headline"
          editMode={true}
          currentValue={modal.quote.headline_text ?? ""}
          onSubmit={handleHeadlineEdit}
          onClose={() => setModal(null)}
        />
      )}

      {modal?.kind === "downgrade" && (
        <CorrectionModal
          title="Downgrade to substantive"
          editMode={false}
          currentValue=""
          onSubmit={handleDowngrade}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}
