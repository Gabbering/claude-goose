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
class Review:
    id: int
    body: str
    author: str
    state: str  # COMMENTED / APPROVED / CHANGES_REQUESTED / DISMISSED / PENDING


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
                    )
                )
            if len(batch) < 100:
                break
            page += 1
        return out

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
