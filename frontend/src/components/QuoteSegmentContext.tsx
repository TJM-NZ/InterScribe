import { formatTimestamp, type TranscriptSegment } from "@/lib/api";

const CONTEXT_SIZE = 2;

interface QuoteSegmentContextProps {
  segments: TranscriptSegment[];
  startSegmentId: number;
  endSegmentId: number;
}

export default function QuoteSegmentContext({
  segments,
  startSegmentId,
  endSegmentId,
}: QuoteSegmentContextProps) {
  const windowStart = startSegmentId - CONTEXT_SIZE;
  const windowEnd = endSegmentId + CONTEXT_SIZE;

  const visible = segments.filter(
    (s) => s.segment_id >= windowStart && s.segment_id <= windowEnd
  );

  if (visible.length === 0) return null;

  return (
    <div
      className="mt-3 rounded-md border border-gray-100 overflow-hidden text-xs"
      data-testid="segment-context"
    >
      <div className="bg-gray-50 px-3 py-1 border-b border-gray-100 text-gray-400 font-medium uppercase tracking-wide">
        Transcript
      </div>
      <div className="divide-y divide-gray-50">
        {visible.map((seg) => {
          const isQuoted =
            seg.segment_id >= startSegmentId && seg.segment_id <= endSegmentId;
          return (
            <div
              key={seg.segment_id}
              className={`flex gap-3 px-3 py-1.5 items-start leading-relaxed ${
                isQuoted
                  ? "bg-amber-50 border-l-2 border-amber-400"
                  : "bg-white"
              }`}
              data-testid={isQuoted ? "quoted-segment" : "context-segment"}
            >
              <span className="tabular-nums text-gray-400 shrink-0 w-10">
                {formatTimestamp(seg.start_ts)}
              </span>
              <span className="text-gray-400 shrink-0 w-16 truncate">
                {seg.speaker_label}
              </span>
              <span className={isQuoted ? "text-gray-900" : "text-gray-400"}>
                {seg.text}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
