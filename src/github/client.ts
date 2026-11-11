/** Thin GitHub REST client. Token is never stored in this module. */

export class GitHubError extends Error {
  constructor(
    message: string,
    public status: number,
    public body?: unknown,
  ) {
    super(message);
    this.name = "GitHubError";
  }
}

async function request<T>(
  token: string,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/vnd.github+json");
  headers.set("Authorization", `Bearer ${token}`);
  headers.set("X-GitHub-Api-Version", "2022-11-28");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`https://api.github.com${path}`, { ...init, headers });
  const text = await res.text();
  let json: unknown = null;
  if (text) {
    try {
      json = JSON.parse(text);
    } catch {
      json = text;
    }
  }

  if (!res.ok) {
    const msg =
      typeof json === "object" && json && "message" in json
        ? String((json as { message: string }).message)
        : `GitHub API ${res.status}`;
    if (res.status === 403 || res.status === 429) {
      const remaining = res.headers.get("x-ratelimit-remaining");
      throw new GitHubError(
        `${msg}${remaining === "0" ? " (rate limit exceeded)" : ""}`,
        res.status,
        json,
      );
    }
    throw new GitHubError(msg, res.status, json);
  }
  return json as T;
}

export type GhUser = {
  login: string;
  name: string | null;
  avatar_url: string;
  html_url: string;
};

export type GhRepo = {
  id: number;
  name: string;
  full_name: string;
  description: string | null;
  private: boolean;
  default_branch: string;
  html_url: string;
  permissions?: { admin?: boolean; push?: boolean; pull?: boolean };
};

export type GhBranch = {
  name: string;
  commit: { sha: string };
  protected: boolean;
};

export async function getAuthenticatedUser(token: string): Promise<GhUser> {
  return request<GhUser>(token, "/user");
}

export async function listRepos(
  token: string,
  page = 1,
  perPage = 100,
): Promise<GhRepo[]> {
  return request<GhRepo[]>(
    token,
    `/user/repos?per_page=${perPage}&page=${page}&sort=updated&affiliation=owner,collaborator,organization_member`,
  );
}

export async function listAllRepos(token: string, maxPages = 5): Promise<GhRepo[]> {
  const all: GhRepo[] = [];
  for (let page = 1; page <= maxPages; page++) {
    const batch = await listRepos(token, page, 100);
    all.push(...batch);
    if (batch.length < 100) break;
  }
  return all;
}

export async function listBranches(
  token: string,
  owner: string,
  repo: string,
): Promise<GhBranch[]> {
  return request<GhBranch[]>(token, `/repos/${owner}/${repo}/branches?per_page=100`);
}

export async function getBranch(
  token: string,
  owner: string,
  repo: string,
  branch: string,
): Promise<{ name: string; commit: { sha: string; commit: { tree: { sha: string } } } }> {
  return request(token, `/repos/${owner}/${repo}/branches/${encodeURIComponent(branch)}`);
}

export async function createBlob(
  token: string,
  owner: string,
  repo: string,
  contentBase64: string,
): Promise<{ sha: string }> {
  return request(token, `/repos/${owner}/${repo}/git/blobs`, {
    method: "POST",
    body: JSON.stringify({ content: contentBase64, encoding: "base64" }),
  });
}

export type TreeEntry = {
  path: string;
  mode: "100644" | "100755" | "040000" | "160000" | "120000";
  type: "blob" | "tree" | "commit";
  sha?: string;
  content?: string;
};

export async function createTree(
  token: string,
  owner: string,
  repo: string,
  tree: TreeEntry[],
  baseTree?: string,
): Promise<{ sha: string }> {
  return request(token, `/repos/${owner}/${repo}/git/trees`, {
    method: "POST",
    body: JSON.stringify({
      tree,
      ...(baseTree ? { base_tree: baseTree } : {}),
    }),
  });
}

export async function createCommit(
  token: string,
  owner: string,
  repo: string,
  message: string,
  treeSha: string,
  parentSha?: string,
): Promise<{ sha: string; html_url?: string }> {
  return request(token, `/repos/${owner}/${repo}/git/commits`, {
    method: "POST",
    body: JSON.stringify({
      message,
      tree: treeSha,
      parents: parentSha ? [parentSha] : [],
    }),
  });
}

export async function updateRef(
  token: string,
  owner: string,
  repo: string,
  branch: string,
  sha: string,
  force = false,
): Promise<{ ref: string; object: { sha: string } }> {
  return request(token, `/repos/${owner}/${repo}/git/refs/heads/${encodeURIComponent(branch)}`, {
    method: "PATCH",
    body: JSON.stringify({ sha, force }),
  });
}

export async function createRef(
  token: string,
  owner: string,
  repo: string,
  branch: string,
  sha: string,
): Promise<unknown> {
  return request(token, `/repos/${owner}/${repo}/git/refs`, {
    method: "POST",
    body: JSON.stringify({ ref: `refs/heads/${branch}`, sha }),
  });
}

/** Empty repositories have no commits — seed with Contents API then use Git Data API. */
export async function putFileContents(
  token: string,
  owner: string,
  repo: string,
  path: string,
  contentBase64: string,
  message: string,
  branch: string,
): Promise<{ commit: { sha: string } }> {
  return request(token, `/repos/${owner}/${repo}/contents/${path.split("/").map(encodeURIComponent).join("/")}`, {
    method: "PUT",
    body: JSON.stringify({
      message,
      content: contentBase64,
      branch,
    }),
  });
}
