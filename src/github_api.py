"""Minimal GitHub REST client — just the endpoints claude-goose needs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

_GITHUB_API = "https://api.github.com"


@dataclass
class PullRequest:
    number: int
    title: str
    body: str
    branch: str
    base_sha: str
    head_sha: str
    author: str
    html_url: str


@dataclass
class Review:
    id: int
    body: str
    author: str
    state: str  # COMMENTED / APPROVED / CHANGES_REQUESTED / DISMISSED / PENDING
    submitted_at: str  # ISO8601, "" if pending


@dataclass
class IssueComment:
    """A top-level conversation comment on a PR (the 'Conversation' tab)."""

    id: int
    body: str
    author: str
    created_at: str  # ISO8601


@dataclass
class ReviewComment:
    """An inline review comment attached to a specific line in a file.

    These form review threads via in_reply_to_id — root comments have it as
    None, replies point at the parent comment.
    """

    id: int
    body: str
    author: str
    path: str
    line: int | None  # None when GitHub couldn't anchor it (outdated diff)
    diff_hunk: str
    in_reply_to_id: int | None
    created_at: str


class GitHubClient:
    def __init__(self, token: str, repo: str, *, timeout: float = 30.0):
        self.repo = repo  # "owner/name"
        self._client = httpx.Client(
            base_url=_GITHUB_API,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "claude-goose/0.1",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ---------- PRs ----------

    def list_open_prs_by(self, author: str) -> list[PullRequest]:
        """List open PRs in `self.repo` authored by `author` (case-insensitive)."""
        author_lower = author.lower()
        out: list[PullRequest] = []
        page = 1
        while True:
            r = self._client.get(
                f"/repos/{self.repo}/pulls",
                params={"state": "open", "per_page": 100, "page": page},
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            for pr in batch:
                user = pr.get("user") or {}
                if (user.get("login") or "").lower() != author_lower:
                    continue
                out.append(
                    PullRequest(
                        number=pr["number"],
                        title=pr["title"] or "",
                        body=pr.get("body") or "",
                        branch=pr["head"]["ref"],
                        base_sha=pr["base"]["sha"],
                        head_sha=pr["head"]["sha"],
                        author=user.get("login") or "",
                        html_url=pr.get("html_url") or "",
                    )
                )
            if len(batch) < 100:
                break
            page += 1
        return out

    # ---------- compare / diff ----------

    def compare(self, base_sha: str, head_sha: str) -> dict[str, Any]:
        """GET /repos/{repo}/compare/{base}...{head} — files[].patch, commits, etc."""
        r = self._client.get(f"/repos/{self.repo}/compare/{base_sha}...{head_sha}")
        r.raise_for_status()
        return r.json()

    # ---------- reviews ----------

    def list_reviews(self, pr_number: int) -> list[Review]:
        """List reviews on a PR, in chronological order (oldest first)."""
        out: list[Review] = []
        page = 1
        while True:
            r = self._client.get(
                f"/repos/{self.repo}/pulls/{pr_number}/reviews",
                params={"per_page": 100, "page": page},
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            for rv in batch:
                user = rv.get("user") or {}
                out.append(
                    Review(
                        id=rv["id"],
                        body=rv.get("body") or "",
                        author=user.get("login") or "",
                        state=rv.get("state") or "",
                        submitted_at=rv.get("submitted_at") or "",
                    )
                )
            if len(batch) < 100:
                break
            page += 1
        return out

    # ---------- conversation: issue comments + inline review comments ----------

    def list_issue_comments(self, pr_number: int) -> list[IssueComment]:
        """List top-level conversation comments on a PR (oldest first).

        These are the 'Conversation' tab comments — distinct from review
        bodies (`list_reviews`) and inline review comments
        (`list_review_comments`). The author may use any of the three to
        respond to feedback, so the goose needs all three to understand
        what's been said.
        """
        out: list[IssueComment] = []
        page = 1
        while True:
            r = self._client.get(
                f"/repos/{self.repo}/issues/{pr_number}/comments",
                params={"per_page": 100, "page": page},
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            for c in batch:
                user = c.get("user") or {}
                out.append(
                    IssueComment(
                        id=c["id"],
                        body=c.get("body") or "",
                        author=user.get("login") or "",
                        created_at=c.get("created_at") or "",
                    )
                )
            if len(batch) < 100:
                break
            page += 1
        return out

    def list_review_comments(self, pr_number: int) -> list[ReviewComment]:
        """List inline review comments (line-anchored, threaded) oldest-first.

        These come from /pulls/{n}/comments — they are the line-level
        discussion threads that hang off specific lines in the diff.
        """
        out: list[ReviewComment] = []
        page = 1
        while True:
            r = self._client.get(
                f"/repos/{self.repo}/pulls/{pr_number}/comments",
                params={"per_page": 100, "page": page},
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            for c in batch:
                user = c.get("user") or {}
                # GitHub returns `line` (current diff line) and falls back to
                # `original_line` for outdated threads. Prefer line, fall back.
                line = c.get("line")
                if line is None:
                    line = c.get("original_line")
                out.append(
                    ReviewComment(
                        id=c["id"],
                        body=c.get("body") or "",
                        author=user.get("login") or "",
                        path=c.get("path") or "",
                        line=line,
                        diff_hunk=c.get("diff_hunk") or "",
                        in_reply_to_id=c.get("in_reply_to_id"),
                        created_at=c.get("created_at") or "",
                    )
                )
            if len(batch) < 100:
                break
            page += 1
        return out

    # ---------- file contents at a specific ref ----------

    def get_file_content(self, path: str, ref: str) -> str | None:
        """Fetch raw text content of a file at a given ref. None on miss/binary.

        Uses the contents API with the raw media type so we get the bytes
        directly instead of base64-wrapped JSON. Returns None for 404,
        binary content (octet-stream), or any other failure — the caller
        treats absence as 'no full-file context for this file'.
        """
        try:
            r = self._client.get(
                f"/repos/{self.repo}/contents/{quote(path, safe='/')}",
                params={"ref": ref},
                headers={"Accept": "application/vnd.github.raw"},
            )
        except httpx.HTTPError:
            return None
        if r.status_code != 200:
            return None
        ct = r.headers.get("Content-Type", "")
        if "octet-stream" in ct:
            return None
        return r.text

    def post_review(
        self,
        pr_number: int,
        body: str,
        *,
        commit_id: str | None = None,
        event: str = "COMMENT",
    ) -> dict[str, Any]:
        """Create a PR review. event ∈ {APPROVE, REQUEST_CHANGES, COMMENT}.

        We always use COMMENT — the goose isn't authorized to approve or
        request changes; it just leaves feedback at the review level so the
        body shows up under the GitHub Reviews API instead of as a flat
        issue comment.
        """
        payload: dict[str, Any] = {"body": body, "event": event}
        if commit_id is not None:
            payload["commit_id"] = commit_id
        r = self._client.post(
            f"/repos/{self.repo}/pulls/{pr_number}/reviews",
            json=payload,
        )
        r.raise_for_status()
        return r.json()

    def update_review(
        self, pr_number: int, review_id: int, body: str
    ) -> dict[str, Any]:
        """Update only the body text of an existing review (state unchanged)."""
        r = self._client.put(
            f"/repos/{self.repo}/pulls/{pr_number}/reviews/{review_id}",
            json={"body": body},
        )
        r.raise_for_status()
        return r.json()
