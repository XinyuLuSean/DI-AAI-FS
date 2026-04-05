"use client";

import { useRef, useState } from "react";
import { uploadDocument } from "@/lib/api";
import type { DocumentResponse } from "@/lib/types";

interface Props {
  onUploaded: (doc: DocumentResponse) => void;
  onError: (msg: string) => void;
  disabled?: boolean;
}

export function UploadPanel({ onUploaded, onError, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);

  const handleFile = async (file: File) => {
    setUploading(true);
    try {
      const doc = await uploadDocument(file);
      if (inputRef.current) inputRef.current.value = "";
      onUploaded(doc);
    } catch (e: unknown) {
      if (inputRef.current) inputRef.current.value = "";
      onError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={onDrop}
      className={`rounded-xl border-2 border-dashed p-8 text-center transition ${
        dragActive
          ? "border-blue-400 bg-blue-50"
          : "border-gray-300 bg-white hover:border-gray-400"
      }`}
    >
      <p className="mb-4 text-gray-600">
        Drag and drop a PDF or text file here, or
      </p>
      <button
        onClick={() => inputRef.current?.click()}
        disabled={disabled || uploading}
        className="rounded-lg bg-gray-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-gray-800 disabled:opacity-50"
      >
        {uploading ? "Uploading…" : "Choose File"}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.txt,.md,.text"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
        }}
      />
      <p className="mt-3 text-xs text-gray-400">
        Supported: PDF, TXT, MD — max 10 MB (local dev)
      </p>
    </div>
  );
}
