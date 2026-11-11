import { useMemo, useRef, useState } from "react";
import { getAuthenticatedUser, listBranches, GitHubError } from "./github/client";
import {
  extractZip,
  formatBytes,
  stripCommonRoot,
  type ExtractedFile,
} from "./zip/extract";
import {
  progressPercent,
  uploadProject,
  type UploadProgress,
} from "./upload/engine";

type UserInfo = { login: string; avatar_url: string };

export function App() {
  // Token stays in React state only — never localStorage / sessionStorage
  const [token, setToken] = useState("");
  const [tokenVisible, setTokenVisible] = useState(false);
  const [user, setUser] = useState<UserInfo | null>(null);
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  const [repoInput, setRepoInput] = useState("");
  const [branch, setBranch] = useState("main");
  const [destDir, setDestDir] = useState("");
  const [commitMessage, setCommitMessage] = useState("Upload project via Rift Upload");
  const [stripRoot, setStripRoot] = useState(true);

  const [zipName, setZipName] = useState<string | null>(null);
  const [files, setFiles] = useState<ExtractedFile[] | null>(null);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [extractProgress, setExtractProgress] = useState({ n: 0, t: 0 });

  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const dropRef = useRef<HTMLLabelElement>(null);

  const appendLog = (line: string) => {
    const stamp = new Date().toLocaleTimeString();
    setLogs((prev) => [`[${stamp}] ${line}`, ...prev].slice(0, 200));
  };

  const clearToken = () => {
    setToken("");
    setUser(null);
    setTokenError(null);
    appendLog("Token cleared from memory.");
  };

  const verifyToken = async () => {
    const t = token.trim();
    if (!t) return;
    setChecking(true);
    setTokenError(null);
    try {
      const u = await getAuthenticatedUser(t);
      setUser({ login: u.login, avatar_url: u.avatar_url });
      appendLog(`Authenticated as ${u.login}.`);
    } catch (err) {
      setUser(null);
      const msg =
        err instanceof GitHubError
          ? `GitHub ${err.status}: ${err.message}`
          : err instanceof Error
            ? err.message
            : String(err);
      setTokenError(msg);
      appendLog(`Auth failed: ${msg}`);
    } finally {
      setChecking(false);
    }
  };

  const loadDefaultBranch = async () => {
    const t = token.trim();
    const full = repoInput
      .trim()
      .replace(/^https?:\/\/github\.com\//, "")
      .replace(/\.git$/, "");
    const [owner, repo] = full.split("/");
    if (!t || !owner || !repo) return;
    try {
      const branches = await listBranches(t, owner, repo);
      const names = branches.map((b) => b.name);
      if (names.includes("main")) setBranch("main");
      else if (names.includes("master")) setBranch("master");
      else if (names[0]) setBranch(names[0]);
      appendLog(
        `Branches: ${names.slice(0, 8).join(", ")}${names.length > 8 ? "…" : ""}`,
      );
    } catch (err) {
      appendLog(
        `Could not list branches: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  };

  const handleZip = async (file: File | null) => {
    if (!file) return;
    setExtractError(null);
    setFiles(null);
    setZipName(file.name);
    setExtracting(true);
    setExtractProgress({ n: 0, t: 0 });
    appendLog(`Reading ZIP: ${file.name} (${formatBytes(file.size)})`);
    try {
      const { files: extracted, totalBytes } = await extractZip(file, (n, t) =>
        setExtractProgress({ n, t }),
      );
      const final = stripRoot ? stripCommonRoot(extracted) : extracted;
      setFiles(final);
      appendLog(
        `Extracted ${final.length} files (${formatBytes(totalBytes)})${
          stripRoot ? " · common root stripped" : ""
        }`,
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setExtractError(msg);
      setFiles(null);
      appendLog(`Extract failed: ${msg}`);
    } finally {
      setExtracting(false);
    }
  };

  const totalBytes = useMemo(
    () => (files ? files.reduce((s, f) => s + f.size, 0) : 0),
    [files],
  );

  const repoFull = repoInput
    .trim()
    .replace(/^https?:\/\/github\.com\//, "")
    .replace(/\.git$/, "");

  const canUpload =
    Boolean(token.trim() && repoFull.includes("/") && branch.trim() && files?.length) &&
    !uploading &&
    !extracting;

  const startUpload = async () => {
    const t = token.trim();
    const [owner, repo] = repoFull.split("/");
    if (!t || !owner || !repo || !files?.length) return;

    setUploading(true);
    setProgress(null);
    const ac = new AbortController();
    abortRef.current = ac;
    appendLog(`Starting upload → ${owner}/${repo}@${branch}`);

    const result = await uploadProject({
      token: t,
      owner,
      repo,
      branch: branch.trim(),
      destDir: destDir.trim(),
      files,
      commitMessage: commitMessage.trim() || "Upload via Rift Upload",
      signal: ac.signal,
      onProgress: (p) => {
        setProgress(p);
        if (p.stage === "creating_blobs" && p.currentFile) {
          if (
            p.processedFiles === 1 ||
            p.processedFiles === p.totalFiles ||
            p.processedFiles % 10 === 0
          ) {
            appendLog(`Blob ${p.processedFiles}/${p.totalFiles}: ${p.currentFile}`);
          }
        } else if (
          p.stage === "resolving_branch" ||
          p.stage === "creating_tree" ||
          p.stage === "creating_commit" ||
          p.stage === "updating_ref" ||
          p.stage === "done" ||
          p.stage === "error"
        ) {
          appendLog(p.message + (p.error ? ` — ${p.error}` : ""));
        }
      },
    });

    setUploading(false);
    abortRef.current = null;
    setProgress(result);

    if (result.stage === "done" && result.commitSha) {
      appendLog(`Done. Commit ${result.commitSha.slice(0, 7)}`);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    dropRef.current?.classList.remove("dragover");
    const file = e.dataTransfer.files?.[0];
    if (file) void handleZip(file);
  };

  const pct = progress ? progressPercent(progress) : 0;

  return (
    <div className="app">
      <header className="header">
        <div className="logo">
          RIFT <span>UPLOAD</span>
        </div>
        <span className="badge">v1.0</span>
      </header>

      <p className="muted" style={{ marginTop: 0 }}>
        Paste a GitHub token, choose a repo, select a project ZIP. Files are extracted in
        this browser and pushed as <strong>one commit</strong> via the Git Data API. The
        token never leaves your device except requests to <code>api.github.com</code>.
      </p>

      <section className="card">
        <h2>1. Personal Access Token</h2>
        <div className="field">
          <label htmlFor="token">Token</label>
          <div className="row">
            <input
              id="token"
              style={{ flex: 1 }}
              type={tokenVisible ? "text" : "password"}
              autoComplete="off"
              spellCheck={false}
              placeholder="ghp_… or github_pat_…"
              value={token}
              onChange={(e) => {
                setToken(e.target.value);
                setUser(null);
              }}
            />
            <button
              type="button"
              className="btn"
              onClick={() => setTokenVisible((v) => !v)}
            >
              {tokenVisible ? "Hide" : "Show"}
            </button>
          </div>
        </div>
        <div className="row">
          <button
            type="button"
            className="btn btn-primary"
            disabled={!token.trim() || checking}
            onClick={() => void verifyToken()}
          >
            {checking ? "Checking…" : "Verify token"}
          </button>
          <button type="button" className="btn btn-danger" onClick={clearToken}>
            Clear token
          </button>
        </div>
        {user && (
          <div className="user" style={{ marginTop: 12 }}>
            <img src={user.avatar_url} alt="" />
            <div>
              <strong>{user.login}</strong>
              <div className="muted" style={{ fontSize: "0.8rem" }}>
                Token held in memory only
              </div>
            </div>
          </div>
        )}
        {tokenError && <div className="error-box">{tokenError}</div>}
        <p className="muted" style={{ marginBottom: 0 }}>
          Create a token at{" "}
          <a href="https://github.com/settings/tokens" target="_blank" rel="noreferrer">
            github.com/settings/tokens
          </a>
          . Classic: enable <strong>repo</strong>. Fine-grained:{" "}
          <strong>Contents: Read and write</strong> on the target repository. Never share
          this token.
        </p>
      </section>

      <section className="card">
        <h2>2. Repository</h2>
        <div className="field">
          <label htmlFor="repo">Owner/name</label>
          <input
            id="repo"
            placeholder="ItzBrezzX/Rift"
            value={repoInput}
            onChange={(e) => setRepoInput(e.target.value)}
            onBlur={() => void loadDefaultBranch()}
          />
        </div>
        <div className="field">
          <label htmlFor="branch">Branch</label>
          <input
            id="branch"
            placeholder="main"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="dest">Destination directory (optional)</label>
          <input
            id="dest"
            placeholder="leave empty for repository root"
            value={destDir}
            onChange={(e) => setDestDir(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="msg">Commit message</label>
          <input
            id="msg"
            value={commitMessage}
            onChange={(e) => setCommitMessage(e.target.value)}
          />
        </div>
      </section>

      <section className="card">
        <h2>3. ZIP file</h2>
        <label
          ref={dropRef}
          className="drop"
          onDragOver={(e) => {
            e.preventDefault();
            dropRef.current?.classList.add("dragover");
          }}
          onDragLeave={() => dropRef.current?.classList.remove("dragover")}
          onDrop={onDrop}
        >
          <div>
            <strong>Tap to choose</strong> or drop a <code>.zip</code>
          </div>
          <div className="muted" style={{ marginTop: 6 }}>
            Nested folders kept. Archive is not uploaded as a single file.
          </div>
          <input
            type="file"
            accept=".zip,application/zip,application/x-zip-compressed"
            onChange={(e) => void handleZip(e.target.files?.[0] ?? null)}
          />
        </label>
        <label className="row" style={{ marginTop: 12 }}>
          <input
            type="checkbox"
            checked={stripRoot}
            onChange={(e) => setStripRoot(e.target.checked)}
          />
          <span className="muted">Strip common root folder (re-select ZIP after toggle)</span>
        </label>
        {extracting && (
          <p className="muted">
            Extracting… {extractProgress.n}/{extractProgress.t}
          </p>
        )}
        {extractError && <div className="error-box">{extractError}</div>}
        {files && (
          <div style={{ marginTop: 12 }}>
            <div className="stat-grid">
              <div className="stat">
                Archive
                <b>{zipName}</b>
              </div>
              <div className="stat">
                Files
                <b>{files.length}</b>
              </div>
              <div className="stat">
                Size
                <b>{formatBytes(totalBytes)}</b>
              </div>
              <div className="stat">
                Target
                <b>
                  {repoFull || "—"}@{branch || "—"}
                </b>
              </div>
            </div>
            <div className="file-list">
              {files.slice(0, 50).map((f) => (
                <div key={f.path}>
                  {destDir.trim() ? `${destDir.trim().replace(/^\/|\/$/g, "")}/` : ""}
                  {f.path} · {formatBytes(f.size)}
                </div>
              ))}
              {files.length > 50 && <div>…and {files.length - 50} more</div>}
            </div>
          </div>
        )}
      </section>

      <section className="card">
        <h2>4. Upload</h2>
        <div className="row">
          <button
            type="button"
            className="btn btn-success"
            disabled={!canUpload}
            onClick={() => void startUpload()}
          >
            {uploading ? "Uploading…" : "Upload to GitHub"}
          </button>
          {uploading && (
            <button
              type="button"
              className="btn btn-danger"
              onClick={() => {
                abortRef.current?.abort();
                appendLog("Cancel requested.");
              }}
            >
              Cancel
            </button>
          )}
        </div>
        <p className="muted" style={{ marginBottom: 0 }}>
          Flow: resolve branch → create blobs → one tree with <code>base_tree</code> → one
          commit → update ref. Unrelated repo files are preserved.
        </p>
      </section>

      {(progress || logs.length > 0) && (
        <section className="card">
          <h2>Progress &amp; logs</h2>
          {progress && (
            <>
              <div
                className={`progress-bar${progress.stage === "done" ? " done" : ""}${
                  progress.stage === "error" ? " error" : ""
                }`}
              >
                <i style={{ width: `${pct}%` }} />
              </div>
              <div className="stat-grid">
                <div className="stat">
                  Stage
                  <b>{progress.stage}</b>
                </div>
                <div className="stat">
                  Files
                  <b>
                    {progress.processedFiles}/{progress.totalFiles}
                  </b>
                </div>
                <div className="stat">
                  Data
                  <b>
                    {formatBytes(progress.uploadedBytes)} / {formatBytes(progress.totalBytes)}
                  </b>
                </div>
                <div className="stat">
                  %
                  <b>{pct}</b>
                </div>
              </div>
              {progress.stage === "done" && progress.commitUrl && (
                <div className="success-box">
                  Uploaded.{" "}
                  <a href={progress.commitUrl} target="_blank" rel="noreferrer">
                    View commit {progress.commitSha?.slice(0, 7)}
                  </a>
                </div>
              )}
              {progress.error && <div className="error-box">{progress.error}</div>}
            </>
          )}
          <div className="file-list" style={{ maxHeight: 220, marginTop: 12 }}>
            {logs.length === 0 ? (
              <div className="muted">No activity yet.</div>
            ) : (
              logs.map((line, i) => <div key={`${i}-${line.slice(0, 24)}`}>{line}</div>)
            )}
          </div>
        </section>
      )}

      <footer className="footer">
        Rift Upload · Token in memory only · Direct GitHub API · No OAuth server required
      </footer>
    </div>
  );
}
