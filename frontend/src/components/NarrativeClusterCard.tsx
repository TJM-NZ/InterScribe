"use client";

import type { NarrativeCluster } from "@/lib/api";

interface Props {
  cluster: NarrativeCluster;
  onEdit: (cluster: NarrativeCluster) => void;
  onReject: (cluster: NarrativeCluster) => void;
  disabled?: boolean;
}

export default function NarrativeClusterCard({ cluster, onEdit, onReject, disabled }: Props) {
  return (
    <div className="border border-gray-200 rounded-lg p-4 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded">
              #{cluster.rank}
            </span>
            <span className="text-xs text-gray-500">
              {cluster.cluster_size} chunk{cluster.cluster_size !== 1 ? "s" : ""}
            </span>
          </div>
          <p
            className="mt-1 text-sm font-medium text-gray-900 break-words"
            data-testid={`cluster-label-${cluster.id}`}
          >
            {cluster.representative_label}
          </p>
        </div>
        {!disabled && (
          <div className="flex gap-1 shrink-0">
            <button
              onClick={() => onEdit(cluster)}
              className="px-2 py-1 text-xs text-indigo-600 border border-indigo-200 rounded hover:bg-indigo-50"
              data-testid={`edit-cluster-${cluster.id}`}
            >
              Edit
            </button>
            <button
              onClick={() => onReject(cluster)}
              className="px-2 py-1 text-xs text-red-500 border border-red-200 rounded hover:bg-red-50"
              data-testid={`reject-cluster-${cluster.id}`}
            >
              Reject
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
