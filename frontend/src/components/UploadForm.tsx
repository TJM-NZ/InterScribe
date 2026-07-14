"use client";

import { useCallback, useRef, useState } from "react";
import { uploadVideo } from "@/lib/api";

interface Props {
  onUploaded: (id: string) => void;
}

export default function UploadForm({ onUploaded }: Props) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(async (file: File) => {
    setError(null);
    setUploading(true);
    try {
      const result = await uploadVideo(file);
      onUploaded(result.id);
    } catch (err: unknown) {
      const detail = (err as { detail?: { error?: string } })?.detail;
      setError(detail?.error ?? "Upload failed");
    } finally {
      setUploading(false);
    }
  }, [onUploaded]);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  return (
    <div
      data-testid="upload-form"
      className={`border-2 border-dashed rounded-lg p-10 text-center transition-colors ${
        dragging ? "border-blue-500 bg-blue-50" : "border-gray-300 bg-white"
      }`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        accept="audio/*,video/*"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
        data-testid="file-input"
      />
      {uploading ? (
        <p className="text-gray-500">Uploading…</p>
      ) : (
        <>
          <p className="text-gray-600 mb-3">
            Drag and drop an audio or video file, or{" "}
            <button
              className="text-blue-600 underline"
              onClick={() => inputRef.current?.click()}
            >
              browse
            </button>
          </p>
          <p className="text-xs text-gray-400">
            Supported: mp3, wav, m4a, ogg, flac, mp4, mov, mkv, webm — up to 2 GB / 3 hours
          </p>
        </>
      )}
      {error && (
        <p className="mt-3 text-sm text-red-600" data-testid="upload-error">{error}</p>
      )}
    </div>
  );
}
