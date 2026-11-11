/**
 * Client-side ZIP extraction with path-traversal defense.
 * Uploads individual files — never the raw archive as a single blob.
 */

import JSZip from "jszip";

export type ExtractedFile = {
  path: string;
  size: number;
  /** Raw bytes for Git blob upload */
  data: Uint8Array;
};

export class ZipSecurityError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ZipSecurityError";
  }
}

const MAX_ENTRIES = 20_000;
const MAX_TOTAL_UNCOMPRESSED = 500 * 1024 * 1024; // 500 MiB browser soft limit
const MAX_SINGLE_FILE = 95 * 1024 * 1024; // under GitHub blob ~100MB

export function validatePath(raw: string): string {
  if (!raw || raw.includes("\0")) {
    throw new ZipSecurityError(`Invalid path: ${raw}`);
  }
  let name = raw.replace(/\\/g, "/");
  // strip leading ./
  while (name.startsWith("./")) name = name.slice(2);
  if (name.startsWith("/") || /^[a-zA-Z]:/.test(name)) {
    throw new ZipSecurityError(`Absolute path rejected: ${raw}`);
  }
  const parts = name.split("/").filter((p) => p && p !== ".");
  if (parts.some((p) => p === "..")) {
    throw new ZipSecurityError(`Path traversal rejected: ${raw}`);
  }
  if (parts.length > 32) {
    throw new ZipSecurityError(`Path too deep: ${raw}`);
  }
  const clean = parts.join("/");
  if (!clean || clean.length > 500) {
    throw new ZipSecurityError(`Invalid path length: ${raw}`);
  }
  return clean;
}

function uint8ToBase64(bytes: Uint8Array): string {
  // Chunked to avoid call-stack / argument limits on large files
  const chunk = 0x8000;
  let binary = "";
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

export async function extractZip(
  file: File,
  onProgress?: (processed: number, total: number) => void,
): Promise<{ files: ExtractedFile[]; totalBytes: number }> {
  if (!file.name.toLowerCase().endsWith(".zip") && file.type !== "application/zip") {
    // Still try — some Android pickers omit extension
  }

  const zip = await JSZip.loadAsync(file);
  const entries = Object.values(zip.files).filter((e) => !e.dir);
  if (entries.length === 0) {
    throw new ZipSecurityError("ZIP contains no files.");
  }
  if (entries.length > MAX_ENTRIES) {
    throw new ZipSecurityError(`Too many files (${entries.length}). Limit is ${MAX_ENTRIES}.`);
  }

  const files: ExtractedFile[] = [];
  let totalBytes = 0;

  for (let i = 0; i < entries.length; i++) {
    const entry = entries[i];
    const path = validatePath(entry.name);
    const data = await entry.async("uint8array");
    if (data.byteLength > MAX_SINGLE_FILE) {
      throw new ZipSecurityError(
        `File too large for GitHub blob API (${path}, ${(data.byteLength / 1024 / 1024).toFixed(1)} MiB).`,
      );
    }
    totalBytes += data.byteLength;
    if (totalBytes > MAX_TOTAL_UNCOMPRESSED) {
      throw new ZipSecurityError("Uncompressed size exceeds browser safety limit (500 MiB).");
    }
    files.push({ path, size: data.byteLength, data });
    onProgress?.(i + 1, entries.length);
  }

  // Stable order for reproducible trees
  files.sort((a, b) => a.path.localeCompare(b.path));
  return { files, totalBytes };
}

export function toBase64(data: Uint8Array): string {
  return uint8ToBase64(data);
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

/** Join destination prefix with relative path. */
export function joinDest(destDir: string, relativePath: string): string {
  const prefix = destDir
    .replace(/\\/g, "/")
    .replace(/^\/+|\/+$/g, "")
    .split("/")
    .filter((p) => p && p !== "." && p !== "..")
    .join("/");
  const rel = relativePath.replace(/^\/+/, "");
  return prefix ? `${prefix}/${rel}` : rel;
}

/**
 * Strip a common root folder if every path shares the same top-level directory
 * (typical when zipping a project folder).
 */
export function stripCommonRoot(files: ExtractedFile[]): ExtractedFile[] {
  if (files.length === 0) return files;
  const first = files[0].path.split("/")[0];
  if (!first) return files;
  const allShare = files.every((f) => f.path === first || f.path.startsWith(first + "/"));
  if (!allShare) return files;
  // Don't strip if any file is at the root of the zip
  if (files.some((f) => !f.path.includes("/"))) return files;
  return files.map((f) => ({
    ...f,
    path: f.path.slice(first.length + 1),
  }));
}
