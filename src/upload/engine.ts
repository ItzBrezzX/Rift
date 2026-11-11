/**
 * Upload engine using GitHub Git Data API.
 *
 * Flow:
 * 1. Resolve branch tip (commit + tree SHA)
 * 2. Create blobs for each file (batched concurrency)
 * 3. Create one tree with base_tree (preserves unrelated files)
 * 4. Create one commit
 * 5. Fast-forward the branch ref
 *
 * Progress callbacks report real stages only — no simulated percentages.
 */

import {
  createBlob,
  createCommit,
  createTree,
  getBranch,
  putFileContents,
  updateRef,
  type TreeEntry,
} from "../github/client";
import { joinDest, toBase64, type ExtractedFile } from "../zip/extract";

export type UploadStage =
  | "idle"
  | "resolving_branch"
  | "creating_blobs"
  | "creating_tree"
  | "creating_commit"
  | "updating_ref"
  | "done"
  | "error";

export type UploadProgress = {
  stage: UploadStage;
  processedFiles: number;
  totalFiles: number;
  uploadedBytes: number;
  totalBytes: number;
  currentFile?: string;
  message: string;
  commitSha?: string;
  commitUrl?: string;
  error?: string;
};

export type UploadOptions = {
  token: string;
  owner: string;
  repo: string;
  branch: string;
  /** Destination directory inside the repo (no leading/trailing slash) */
  destDir: string;
  files: ExtractedFile[];
  commitMessage: string;
  /** Concurrent blob uploads */
  concurrency?: number;
  onProgress?: (p: UploadProgress) => void;
  signal?: AbortSignal;
};

const DEFAULT_CONCURRENCY = 4;

function assertNotAborted(signal?: AbortSignal) {
  if (signal?.aborted) {
    throw new DOMException("Upload cancelled", "AbortError");
  }
}

async function mapPool<T, R>(
  items: T[],
  concurrency: number,
  fn: (item: T, index: number) => Promise<R>,
  signal?: AbortSignal,
): Promise<R[]> {
  const results: R[] = new Array(items.length);
  let next = 0;

  async function worker() {
    while (next < items.length) {
      assertNotAborted(signal);
      const i = next++;
      results[i] = await fn(items[i], i);
    }
  }

  const workers = Array.from({ length: Math.min(concurrency, items.length) }, () => worker());
  await Promise.all(workers);
  return results;
}

export async function uploadProject(opts: UploadOptions): Promise<UploadProgress> {
  const {
    token,
    owner,
    repo,
    branch,
    destDir,
    files,
    commitMessage,
    concurrency = DEFAULT_CONCURRENCY,
    onProgress,
    signal,
  } = opts;

  const totalBytes = files.reduce((s, f) => s + f.size, 0);
  let uploadedBytes = 0;

  const emit = (partial: Partial<UploadProgress> & { stage: UploadStage; message: string }) => {
    const p: UploadProgress = {
      processedFiles: partial.processedFiles ?? 0,
      totalFiles: files.length,
      uploadedBytes: partial.uploadedBytes ?? uploadedBytes,
      totalBytes,
      currentFile: partial.currentFile,
      commitSha: partial.commitSha,
      commitUrl: partial.commitUrl,
      error: partial.error,
      stage: partial.stage,
      message: partial.message,
    };
    onProgress?.(p);
    return p;
  };

  try {
    assertNotAborted(signal);
    emit({ stage: "resolving_branch", message: `Reading branch ${branch}…`, processedFiles: 0 });

    let parentSha: string | undefined;
    let baseTree: string | undefined;
    let emptyRepo = false;

    try {
      const tip = await getBranch(token, owner, repo, branch);
      parentSha = tip.commit.sha;
      baseTree = tip.commit.commit.tree.sha;
    } catch (err) {
      // 404 → empty repo or missing branch
      emptyRepo = true;
      emit({
        stage: "resolving_branch",
        message: "Repository has no commits yet — will initialize then push the tree.",
        processedFiles: 0,
      });
    }

    // Seed empty repo so Git Data API works
    if (emptyRepo && files.length > 0) {
      assertNotAborted(signal);
      const seed = files[0];
      const seedPath = joinDest(destDir, seed.path);
      const put = await putFileContents(
        token,
        owner,
        repo,
        seedPath,
        toBase64(seed.data),
        `${commitMessage} (initialize)`,
        branch,
      );
      parentSha = put.commit.sha;
      // Re-read tree
      const tip = await getBranch(token, owner, repo, branch);
      parentSha = tip.commit.sha;
      baseTree = tip.commit.commit.tree.sha;
      // Remove seed from list if we'll re-upload it in the full tree
      // (tree with base_tree will overwrite same path — fine)
    }

    emit({
      stage: "creating_blobs",
      message: `Uploading ${files.length} blobs…`,
      processedFiles: 0,
      uploadedBytes: 0,
    });

    let processed = 0;
    const treeEntries: TreeEntry[] = await mapPool(
      files,
      concurrency,
      async (file) => {
        assertNotAborted(signal);
        const path = joinDest(destDir, file.path);
        const { sha } = await createBlob(token, owner, repo, toBase64(file.data));
        uploadedBytes += file.size;
        processed += 1;
        emit({
          stage: "creating_blobs",
          message: `Blob ${processed}/${files.length}`,
          processedFiles: processed,
          uploadedBytes,
          currentFile: path,
        });
        return {
          path,
          mode: "100644" as const,
          type: "blob" as const,
          sha,
        };
      },
      signal,
    );

    assertNotAborted(signal);
    emit({
      stage: "creating_tree",
      message: "Creating Git tree (base_tree preserves unrelated files)…",
      processedFiles: files.length,
      uploadedBytes,
    });

    const tree = await createTree(token, owner, repo, treeEntries, baseTree);

    assertNotAborted(signal);
    emit({
      stage: "creating_commit",
      message: "Creating commit…",
      processedFiles: files.length,
      uploadedBytes,
    });

    const commit = await createCommit(token, owner, repo, commitMessage, tree.sha, parentSha);

    assertNotAborted(signal);
    emit({
      stage: "updating_ref",
      message: `Updating refs/heads/${branch}…`,
      processedFiles: files.length,
      uploadedBytes,
      commitSha: commit.sha,
    });

    await updateRef(token, owner, repo, branch, commit.sha, false);

    const commitUrl = `https://github.com/${owner}/${repo}/commit/${commit.sha}`;
    return emit({
      stage: "done",
      message: "Upload complete.",
      processedFiles: files.length,
      uploadedBytes,
      commitSha: commit.sha,
      commitUrl,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      return emit({
        stage: "error",
        message: "Cancelled.",
        error: "Upload cancelled.",
        processedFiles: 0,
      });
    }
    const message = err instanceof Error ? err.message : String(err);
    return emit({
      stage: "error",
      message: "Upload failed.",
      error: message,
      processedFiles: 0,
    });
  }
}

export function progressPercent(p: UploadProgress): number {
  if (p.stage === "done") return 100;
  if (p.stage === "idle" || p.stage === "error") return 0;
  if (p.stage === "resolving_branch") return 2;
  if (p.stage === "creating_blobs") {
    if (p.totalFiles === 0) return 5;
    return 5 + Math.floor((p.processedFiles / p.totalFiles) * 80);
  }
  if (p.stage === "creating_tree") return 88;
  if (p.stage === "creating_commit") return 93;
  if (p.stage === "updating_ref") return 97;
  return 0;
}
