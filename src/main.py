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
from .prompt import SYSTEM_PROMPT, build_user_content
from .reviewer import Reviewer

# --- config (all env vars have sane defaults except the secrets) -------------

TARGET_REPO = os.environ.get("TARGET_REPO", "tile-ai/TileOPs")
TARGET_AUTHOR = os.environ.get("TARGET_AUTHOR", "superAngGao")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "Gabbering")

# If true, no comments are posted or edited — just print what would happen.
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")


# --- helpers -----------------------------------------------------------------


def _log(msg: str) -> None:
    print(msg, flush=True)


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

    is_silent = result.strip().upper() == "SILENT"

    if is_silent:
        _handle_silent(gh, pr, latest_comment, latest_marker)
    else:
        _handle_findings(gh, pr, result)


def _handle_silent(
    gh: GitHubClient,
    pr: PullRequest,
    latest_comment: Comment | None,
    latest_marker: marker.Marker | None,
) -> None:
    """Goose has nothing to honk about for this delta."""
    if latest_comment is None or latest_marker is None:
        # First-ever review of this PR was silent. We can't advance state without
        # posting a visible comment, so we accept one wasted Claude call per cron
        # tick until either (a) a new commit changes head_sha, or (b) a future
        # review finds something. In practice this is rare — most first reviews
        # of non-trivial PRs surface at least one finding.
        _log("  [silent] no prior bot comment; state will not advance (accepted waste)")
        return

    # Advance the existing marker in-place. Comment body text stays the same
    # (still shows the old findings from whenever they were first written),
    # but the hidden marker is bumped to the current head so the next cron
    # tick won't re-review this commit.
    new_skips = list(latest_marker.silent_skips)
    skip_tag = pr.head_sha[:7].lower()
    if skip_tag not in new_skips:
        new_skips.append(skip_tag)
    # Cap the silent_skips list — it's for debugging, not a full audit log.
    new_skips = new_skips[-10:]

    new_marker_str = marker.encode(pr.head_sha, silent_skips=new_skips)
    new_body = marker.replace_in_body(latest_comment.body, new_marker_str)

    if DRY_RUN:
        _log(f"  [silent][dry-run] would edit comment {latest_comment.id} → marker sha={pr.head_sha[:7]}")
        return

    try:
        gh.edit_issue_comment(latest_comment.id, new_body)
    except Exception as e:
        _log(f"  [error] failed to edit marker on comment {latest_comment.id}: {e}")
        return
    _log(f"  [silent] advanced marker on comment {latest_comment.id} → {pr.head_sha[:7]}")


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
        anthropic_key = os.environ["ANTHROPIC_API_KEY"]
    except KeyError as e:
        print(f"[fatal] missing env var: {e}", file=sys.stderr)
        return 2

    _log(
        f"claude-goose starting: repo={TARGET_REPO} author={TARGET_AUTHOR} "
        f"bot={BOT_USERNAME} dry_run={DRY_RUN}"
    )

    with GitHubClient(bot_token, TARGET_REPO) as gh:
        reviewer = Reviewer(anthropic_key)

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
