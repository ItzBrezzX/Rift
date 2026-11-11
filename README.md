# Rift Upload

Upload an entire project ZIP to any GitHub repository from your browser (Android or desktop).

**No OAuth app. No backend. No Git. No Termux.**

1. Paste a Personal Access Token  
2. Enter `owner/repo`  
3. Select a `.zip`  
4. Upload  

Files are extracted in the browser and committed in **one** Git Data API transaction.

---

## Use

### 1. Create a GitHub token

https://github.com/settings/tokens

| Token type | Permission |
|------------|------------|
| Classic | **`repo`** scope |
| Fine-grained | **Contents: Read and write** on the target repo |

### 2. Run locally

```bash
npm install
npm run dev
```

Open the URL Vite prints (usually `http://127.0.0.1:5173`).

### 3. Deploy to GitHub Pages

```bash
npm run build
```

Push `dist/` to the `gh-pages` branch, or use the included GitHub Actions workflow
(Settings → Pages → Source: **GitHub Actions**).

For a project site at `https://USER.github.io/REPO/`:

```bash
VITE_BASE_PATH=/REPO/ npm run build
```

---

## How upload works

```
GET    /repos/{owner}/{repo}/branches/{branch}
POST   /repos/.../git/blobs          (each file, concurrent)
POST   /repos/.../git/trees          (base_tree + new paths)
POST   /repos/.../git/commits
PATCH  /repos/.../git/refs/heads/{branch}
```

- **`base_tree`** keeps files that are **not** in the ZIP.  
- Empty repos are seeded once via the Contents API, then the same flow runs.  
- Path traversal (`..`, absolute paths) is rejected.  
- Per-file limit ≈ 95 MiB (GitHub blob limit is 100 MiB).

---

## Security

| Rule | Implementation |
|------|----------------|
| Token not hardcoded | Entered by the user |
| Token not in localStorage | React state only; **Clear token** wipes it |
| Token not sent to third parties | Only `api.github.com` |
| Token never logged | UI never prints the secret |
| ZIP safety | `validatePath` rejects `..`, absolutes, NUL |

---

## Example

| Field | Value |
|-------|--------|
| Token | `ghp_…` |
| Repository | `ItzBrezzX/Rift` |
| Branch | `main` |
| ZIP | `KingBrezz-Port-Engine-v0.2.0.zip` |

Result: every file and folder from the archive appears on `main` under one commit.

---

## Stack

- React 18 + TypeScript + Vite  
- JSZip  
- GitHub REST / Git Data API  

---

## License

MIT
