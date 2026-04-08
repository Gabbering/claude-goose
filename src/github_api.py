"""Minimal GitHub REST client — just the endpoints claude-goose needs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
class Comment:
    id: int
    body: str
    author: str


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

    # ---------- comments ----------

    def list_issue_comments(self, pr_number: int) -> list[Comment]:
        """List issue comments on a PR, in chronological order (oldest first)."""
        out: list[Comment] = []
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
                    Comment(
                        id=c["id"],
                        body=c.get("body") or "",
                        author=user.get("login") or "",
                    )
                )
            if len(batch) < 100:
                break
            page += 1
        return out

    def post_issue_comment(self, pr_number: int, body: str) -> dict[str, Any]:
        r = self._client.post(
            f"/repos/{self.repo}/issues/{pr_number}/comments",
            json={"body": body},
        )
        r.raise_for_status()
        return r.json()

    def edit_issue_comment(self, comment_id: int, body: str) -> dict[str, Any]:
        r = self._client.patch(
            f"/repos/{self.repo}/issues/comments/{comment_id}",
            json={"body": body},
        )
        r.raise_for_status()
        return r.json()
