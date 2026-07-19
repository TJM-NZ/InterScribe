"use client";

import { use, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  confirmPhase2Review,
  extractApiError,
  formatTimestamp,
  getPhase1Narrative,
  getPhase2Quotes,
  logPhase2Correction,
  type NotableMoment,
  type Quote,
  type ReasonCategory,
  type VideoStatus,
  type VideoSummary,
  getVideo,
} from "@/lib/api";
import CorrectionModal from "@/components/CorrectionModal";

type ModalState =
  | { kind: "reject-quote"; quote: Quote }
  | null;

function ScoreBar({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-violet-500 rounded-full"
          style={{ width: `${Math.round(score * 100)}%` }}
        />
      </div>
      <span className="text-xs text-gray-500 tabular-nums w-8 text-right">
        {Math.round(score * 100)}%
      </span>
    </div>
  );
}

interface QuoteCardProps {
  quote: Quote;
  notableMoment: NotableMoment | null;
  disabled: boolean;
  onReject: (q: Quote) => void;
}

function QuoteCard({ quote, notableMoment, disabled, onReject }: QuoteCardProps) {
  return (
    <div
      className={`border rounded-lg p-4 space-y-2 ${
        quote.reviewed ? "border-gray-200 bg-gray-50" : "border-gray-200 bg-white"
      }`}
      data-testid="quote-card"
    >
      <p className="text-sm text-gray-800 leading-relaxed">{quote.quote_text}</p>
      <div className="flex items-center gap-3 text-xs text-gray-500">
        <span>{quote.speaker_label}</span>
        <span>·</span>
        <span>{formatTimestamp(quote.start_ts)} – {formatTimestamp(quote.end_ts)}</span>
        {quote.is_notable_moment && (
          <>
            <span>·</span>
            <span className="text-violet-600 font-medium">Notable</span>
          </>
        )}
        {quote.reviewed && (
          <>
            <span>·</span>
            <span className="text-emerald-600 font-medium">Reviewed</span>
          </>
        )}
      </div>
      <ScoreBar score={quote.narrative_alignment_score} />
      {notableMoment && (
        <p className="text-xs text-violet-600 bg-violet-50 rounded px-2 py-1 border border-violet-100">
          Linked moment: {notableMoment.description}
        </p>
      )}
      {!disabled && (
        <div className="flex gap-2 pt-1">
          <button
            onClick={() => onReject(quote)}
            className="text-xs text-red-600 hover:underline"
            data-testid="reject-quote-button"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  );
}

const PAST_PHASE2 = new Set<VideoStatus>(["phase2_reviewed"]);

export default function Phase2ReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();

  const [video, setVideo] = useState<VideoSummary | null>(null);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [notableMoments, setNotableMoments] = useState<NotableMoment[]>([]);
  const [modal, setModal] = useState<ModalState>(null);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [v, quotesData, narrativeData] = await Promise.all([
          getVideo(id),
          getPhase2Quotes(id, "top"),
          getPhase1Narrative(id),
        ]);
        setVideo(v);
        setQuotes(quotesData.quotes);
        setNotableMoments(narrativeData.notable_moments);
      } catch (err: unknown) {
        setError(extractApiError(err, "Failed to load Phase 2 review"));
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  const refreshQuotes = useCallback(async () => {
    const data = await getPhase2Quotes(id, "top");
    setQuotes(data.quotes);
  }, [id]);

  const handleQuoteReject = async ({
    reasonCategory,
    reasonNote,
  }: {
    correctedValue: string | null;
    reasonCategory: ReasonCategory;
    reasonNote: string;
  }) => {
    if (modal?.kind !== "reject-quote") return;
    const quote = modal.quote;
    await logPhase2Correction(id, {
      entity_type: "quote",
      entity_id: quote.id,
      field_name: null,
      original_value: { quote_text: quote.quote_text },
      corrected_value: null,
      reason_category: reasonCategory,
      reason_note: reasonNote || null,
    });
    await refreshQuotes();
  };

  const handleConfirm = async () => {
    setConfirming(true);
    setError(null);
    try {
      await confirmPhase2Review(id);
      router.push("/");
    } catch (err: unknown) {
      setError(extractApiError(err, "Failed to confirm review"));
      setConfirming(false);
    }
  };

  const isReviewed = video != null && PAST_PHASE2.has(video.status);
  const canConfirm = video?.status === "phase2_ready_for_review";

  const notableMomentMap = new Map(notableMoments.map((m) => [m.id, m]));
  const notableQuotes = quotes.filter((q) => q.is_notable_moment);

  if (loading) return <p className="text-gray-400">Loading…</p>;
  if (error && !video) return <p className="text-red-600">{error}</p>;
  if (!video) return null;

  return (
    <div className="space-y-10">
      <div>
        <h2 className="text-lg font-semibold break-all">{video.original_filename}</h2>
        <p className="text-sm text-gray-500 mt-0.5">Phase 2 quote review</p>
      </div>

      {notableQuotes.length > 0 && (
        <section>
          <h3 className="text-base font-medium mb-3">
            Notable moment quotes
            <span className="ml-2 text-xs font-normal text-gray-500">
              quotes overlapping Phase 1 notable moments
            </span>
          </h3>
          <div className="space-y-3" data-testid="notable-quotes-list">
            {notableQuotes.map((quote) => (
              <QuoteCard
                key={quote.id}
                quote={quote}
                notableMoment={quote.notable_moment_id ? (notableMomentMap.get(quote.notable_moment_id) ?? null) : null}
                disabled={isReviewed}
                onReject={(q) => setModal({ kind: "reject-quote", quote: q })}
              />
            ))}
          </div>
        </section>
      )}

      <section>
        <h3 className="text-base font-medium mb-3">
          Top quotes by narrative alignment
          <span className="ml-2 text-xs font-normal text-gray-500">
            highest alignment score first
          </span>
        </h3>
        {quotes.length === 0 ? (
          <p className="text-sm text-gray-400">No quotes found.</p>
        ) : (
          <div className="space-y-3" data-testid="top-quotes-list">
            {quotes.map((quote) => (
              <QuoteCard
                key={quote.id}
                quote={quote}
                notableMoment={quote.notable_moment_id ? (notableMomentMap.get(quote.notable_moment_id) ?? null) : null}
                disabled={isReviewed}
                onReject={(q) => setModal({ kind: "reject-quote", quote: q })}
              />
            ))}
          </div>
        )}
      </section>

      {notableMoments.length > 0 && (
        <section>
          <h3 className="text-base font-medium mb-3">
            Phase 1 notable moments
            <span className="ml-2 text-xs font-normal text-gray-500">
              reference — from Phase 1 analysis
            </span>
          </h3>
          <div className="space-y-2" data-testid="phase1-moments-list">
            {notableMoments.map((m) => (
              <div
                key={m.id}
                className="border border-gray-100 rounded-lg px-4 py-2 bg-gray-50 text-sm text-gray-600"
              >
                {m.description}
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="border-t border-gray-200 pt-6">
        {error && <p className="mb-3 text-sm text-red-600">{error}</p>}
        <button
          onClick={handleConfirm}
          disabled={confirming || !canConfirm}
          className="px-5 py-2 bg-emerald-600 text-white text-sm rounded hover:bg-emerald-700 disabled:opacity-40"
          data-testid="confirm-phase2-review-button"
        >
          {isReviewed
            ? "Review complete"
            : confirming
            ? "Confirming…"
            : "Confirm Phase 2 review"}
        </button>
      </div>

      {modal && (
        <CorrectionModal
          title="Reject quote"
          editMode={false}
          currentValue=""
          onSubmit={handleQuoteReject}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}
