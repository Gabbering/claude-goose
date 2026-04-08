"""claude-goose entrypoint: scan tile-ai/TileOPs for open PRs by superAngGao,
run incremental goose reviews, and post/edit comments.

State is stored entirely in hidden HTML markers inside the bot's own comments —
see src/marker.py for the format. No database.
"""

from __future__ import annotations

import os
import sys
import traceback

from . import marker
from .github_api import Comment, GitHubClient, PullRequest
from .path_filter import is_docs_only
from .prompt import SYSTEM_PROMPT, build_user_content
from .reviewer import Reviewer, reviewer_from_env

# --- config (all env vars have sane defaults except the secrets) -------------

TARGET_REPO = os.environ.get("TARGET_REPO", "tile-ai/TileOPs")
TARGET_AUTHOR = os.environ.get("TARGET_AUTHOR", "superAngGao")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "Gabbering")

# If true, no comments are posted or edited — just print what would happen.
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")


# --- helpers -----------------------------------------------------------------


def _log(msg: str) -> None:
    print(msg, flush=True)


def _looks_silent(text: str) -> bool:
    """Lenient SILENT detection — accepts SILENT / silent. / *silent* / etc.

    Rule: the first non-empty line, stripped of punctuation/whitespace/markdown
    emphasis, must equal SILENT (case-insensitive), AND the whole response must
    be short (< 80 chars). The length cap prevents matching a real review that
    happens to start with the word "Silent" somewhere.
    """
    if not text:
        return True
    stripped = text.strip()
    if len(stripped) > 80:
        return False
    first_line = stripped.split("\n", 1)[0].strip()
    # Strip leading/trailing markdown emphasis, punctuation, whitespace.
    cleaned = first_line.strip("*_`~ \t.!,;:").upper()
    return cleaned == "SILENT"


def _find_latest_bot_marker(
    gh: GitHubClient, pr: PullRequest, bot_username: str
) -> tuple[Comment, marker.Marker] | tuple[None, None]:
    """Walk PR comments newest-first; return (comment, marker) of the most recent
    bot-authored comment that carries a valid marker. None if no such comment.
    """
    comments = gh.list_issue_comments(pr.number)
    bot_lower = bot_username.lower()
    for c in reversed(comments):
        if c.author.lower() != bot_lower:
            continue
        m = marker.parse(c.body)
        if m is not None:
            return c, m
    return None, None


# --- per-PR logic ------------------------------------------------------------


def process_pr(gh: GitHubClient, reviewer: Reviewer, pr: PullRequest) -> None:
    _log(f"[pr #{pr.number}] {pr.title[:70]}  head={pr.head_sha[:7]}")

    latest_comment, latest_marker = _find_latest_bot_marker(gh, pr, BOT_USERNAME)

    if latest_marker is not None and latest_marker.sha == pr.head_sha.lower():
        _log(f"  [skip] head {pr.head_sha[:7]} already processed (marker match)")
        return

    if latest_marker is not None:
        old_sha = latest_marker.sha
        first_time = False
        _log(f"  [review] incremental {old_sha[:7]}..{pr.head_sha[:7]}")
    else:
        old_sha = pr.base_sha
        first_time = True
        _log(f"  [review] first-time full {old_sha[:7]}..{pr.head_sha[:7]}")

    # Pull the delta from GitHub.
    try:
        compare = gh.compare(old_sha, pr.head_sha)
    except Exception as e:
        _log(f"  [error] compare failed: {e}")
        return

    changed_files = compare.get("files") or []
    if not changed_files:
        _log("  [skip] no files changed in delta (branch merged/rebased?)")
        return

    # Plan D: docs-only short-circuit. If every file in the delta is docs/prose,
    # don't burn an Opus call — geese don't review prose. Post (or advance) a
    # minimal acknowledge comment so state still moves forward.
    if is_docs_only(changed_files):
        _log(f"  [skip-claude] docs-only delta ({len(changed_files)} file(s))")
        _handle_docs_only(gh, pr, latest_comment, latest_marker)
        return

    user_content = build_user_content(pr, old_sha, pr.head_sha, compare, first_time)

    # Ask the goose.
    try:
        result = reviewer.review(SYSTEM_PROMPT, user_content)
    except Exception as e:
        _log(f"  [error] Claude API call failed: {e}")
        traceback.print_exc()
        return

    if not result:
        _log("  [warn] empty response from Claude — treating as SILENT")
        result = "SILENT"

    is_silent = _looks_silent(result)

    if is_silent:
        _handle_silent(gh, pr, latest_comment, latest_marker)
    else:
        _handle_findings(gh, pr, result)


def _post_or_advance_silent(
    gh: GitHubClient,
    pr: PullRequest,
    latest_comment: Comment | None,
    latest_marker: marker.Marker | None,
    first_time_body: str,
    log_label: str,
) -> None:
    """Shared 'no findings' state-advancement logic.

    - First-time (no prior bot comment): post a minimal acknowledge comment
      with `first_time_body` so the marker has a place to live.
    - Subsequent: edit the latest bot comment's marker to advance state. The
      visible body of the prior comment is left untouched (it might be real
      findings from an earlier commit — we don't want to overwrite that).
    """
    if latest_comment is None or latest_marker is None:
        # First-time path. Post a new minimal comment with marker.
        body = first_time_body.rstrip() + "\n\n" + marker.encode(pr.head_sha)
        if DRY_RUN:
            _log(f"  [{log_label}][dry-run] would post first-time ack for {pr.head_sha[:7]}")
            return
        try:
            created = gh.post_issue_comment(pr.number, body)
        except Exception as e:
            _log(f"  [error] failed to post first-time {log_label} ack: {e}")
            return
        _log(f"  [{log_label}] posted first-time ack {created.get('id')} for {pr.head_sha[:7]}")
        return

    # Subsequent path. Bump marker on the existing latest bot comment, leave
    # its body alone, append the head SHA to silent_skips for debugging.
    new_skips = list(latest_marker.silent_skips)
    skip_tag = pr.head_sha[:7].lower()
    if skip_tag not in new_skips:
        new_skips.append(skip_tag)
    new_skips = new_skips[-10:]  # cap; this is debug breadcrumbs not an audit log

    new_marker_str = marker.encode(pr.head_sha, silent_skips=new_skips)
    new_body = marker.replace_in_body(latest_comment.body, new_marker_str)

    if DRY_RUN:
        _log(f"  [{log_label}][dry-run] would edit comment {latest_comment.id} → marker sha={pr.head_sha[:7]}")
        return

    try:
        gh.edit_issue_comment(latest_comment.id, new_body)
    except Exception as e:
        _log(f"  [error] failed to edit marker on comment {latest_comment.id}: {e}")
        return
    _log(f"  [{log_label}] advanced marker on comment {latest_comment.id} → {pr.head_sha[:7]}")


def _handle_silent(
    gh: GitHubClient,
    pr: PullRequest,
    latest_comment: Comment | None,
    latest_marker: marker.Marker | None,
) -> None:
    """Claude returned SILENT — review ran, found nothing worth honking about."""
    body = f":goose: *goose skimmed `{pr.head_sha[:7]}` — nothing to honk about.*"
    _post_or_advance_silent(gh, pr, latest_comment, latest_marker, body, "silent")


def _handle_docs_only(
    gh: GitHubClient,
    pr: PullRequest,
    latest_comment: Comment | None,
    latest_marker: marker.Marker | None,
) -> None:
    """Docs-only delta — Claude was never called. Post a brief honk and move on."""
    body = (
        f":goose: *honk* — docs-only change. geese don't review prose. "
        f"skipping `{pr.head_sha[:7]}`."
    )
    _post_or_advance_silent(gh, pr, latest_comment, latest_marker, body, "docs-only")


def _handle_findings(gh: GitHubClient, pr: PullRequest, review_text: str) -> None:
    """Goose found something worth honking about — post a new comment."""
    new_marker_str = marker.encode(pr.head_sha)
    body = review_text.rstrip() + "\n\n" + new_marker_str

    if DRY_RUN:
        _log(f"  [post][dry-run] would post new comment for {pr.head_sha[:7]}:")
        _log("  " + "\n  ".join(body.splitlines()[:12]))
        return

    try:
        created = gh.post_issue_comment(pr.number, body)
    except Exception as e:
        _log(f"  [error] failed to post comment: {e}")
        return
    _log(f"  [post] created comment {created.get('id')} for head {pr.head_sha[:7]}")


# --- entrypoint --------------------------------------------------------------


def main() -> int:
    try:
        bot_token = os.environ["BOT_PAT"]
    except KeyError:
        print("[fatal] missing env var: BOT_PAT", file=sys.stderr)
        return 2

    # Match claude_utils.py convention: accept either ANTHROPIC_API_KEY or
    # ANTHROPIC_AUTH_TOKEN (some proxies use the latter name).
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
        "ANTHROPIC_AUTH_TOKEN"
    )
    if not anthropic_key:
        print(
            "[fatal] missing env var: ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN)",
            file=sys.stderr,
        )
        return 2

    base_url = os.environ.get("ANTHROPIC_BASE_URL") or "(default api.anthropic.com)"
    model = os.environ.get("CLAUDE_MODEL") or "(default)"
    _log(
        f"claude-goose starting: repo={TARGET_REPO} author={TARGET_AUTHOR} "
        f"bot={BOT_USERNAME} dry_run={DRY_RUN} base_url={base_url} model={model}"
    )

    with GitHubClient(bot_token, TARGET_REPO) as gh:
        reviewer = reviewer_from_env(anthropic_key)

        try:
            prs = gh.list_open_prs_by(TARGET_AUTHOR)
        except Exception as e:
            print(f"[fatal] failed to list PRs: {e}", file=sys.stderr)
            traceback.print_exc()
            return 1

        _log(f"found {len(prs)} open PR(s) by {TARGET_AUTHOR}")

        for pr in prs:
            try:
                process_pr(gh, reviewer, pr)
            except Exception as e:
                # Never let one bad PR crash the whole run.
                _log(f"[error] PR #{pr.number} failed: {e}")
                traceback.print_exc()

    _log("claude-goose done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
