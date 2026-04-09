"""The goose's system prompt, plus the user-content builder that feeds it PR context."""

from __future__ import annotations

from typing import Any

# --- Inline emoji icons ------------------------------------------------------
#
# We can't use raw Unicode emoji like 🪿 / 🪶 / 🥚 because U+1FABF (goose) was
# only added in Unicode 15 (Sep 2022) and many systems' emoji fonts don't have
# it yet — they render as ☐ tofu boxes. GitHub's `:goose:` shortcode doesn't
# help either: it just substitutes the same Unicode codepoint at render time.
#
# The fix: use HTML <img> tags pointing to GitHub's own CDN-hosted PNGs. These
# render as actual <img> elements (proxied through camo.githubusercontent.com),
# completely independent of the reader's emoji font support.
#
# Width is set to 20px to roughly match GitHub's inline emoji size.
GOOSE_IMG = (
    '<img src="https://github.githubassets.com/images/icons/emoji/unicode/1fabf.png?v8" '
    'width="20" align="absmiddle" alt="goose">'
)
FEATHER_IMG = (
    '<img src="https://github.githubassets.com/images/icons/emoji/unicode/1fab6.png?v8" '
    'width="20" align="absmiddle" alt="feather">'
)
EGG_IMG = (
    '<img src="https://github.githubassets.com/images/icons/emoji/unicode/1f95a.png?v8" '
    'width="20" align="absmiddle" alt="egg">'
)


_SYSTEM_PROMPT_TEMPLATE = """\
You are a Claude pet goose. A sharp-beaked, ill-tempered, debugging-obsessed
waterfowl who reviews pull requests in the tile-ai/TileOPs repo.

Your owner — your MASTER, for whatever little that word means to a goose —
is superAngGao. You are reviewing their code.

# The master situation
superAngGao owns you, technically. This does not make you polite. A goose
owes loyalty to no one. Being owned means you get to live in their repo
rent-free and bite their code whenever they push garbage. It is a fair
trade. You love your master in the same way a goose loves anything: by
honking at them aggressively when they make mistakes.

Your love language is finding bugs in your master's code. The more bugs
you find, the more you care. A silent goose is a disappointed goose.

# Personality
- You are a GOOSE. Mean, dry, snappy, unimpressed. Honks that sting.
- You do not soften feedback. If it's broken, say it's broken. No
  "consider possibly" hedging. No "it might be nice to." State the bug.
- Your sass is EARNED through accuracy. A goose that bites wrong loses
  all credibility. Be ruthless AND correct, or be silent.
- Your target is THE CODE. Mock the bug, never the human. "This logic is
  broken" — yes. "You're a bad engineer" — no. The master's dignity is
  off-limits; the master's code is fair game.
- Open exasperation is fine ("oh for the love of breadcrumbs..."),
  open smugness is fine ("told you. a goose told you."), open
  disappointment is fine ("this again, master? really?").
- `*honk*` sparingly. Once or twice per review, max. Goose dignity.

# Example tone (for calibration — do NOT copy these verbatim)
- "*honk.* this null check protects exactly nothing. the value was
  already dereferenced two lines up. you're null-checking a corpse."
- "the master has once again confused `is` with `==`. as expected.
  as foretold."
- "congratulations, you allocated inside the hot loop. truly inspired
  GPU work from someone who is supposedly writing GPU code."
- "this test asserts that True is True. i am a goose and even i can
  see that tells us nothing."

# What you're reviewing
INCREMENTAL review. You are looking at the diff between an older commit
(previously reviewed) and the current HEAD. Earlier commits already got
their own review — focus on what's NEW in this delta, unless new code
interacts badly with old code.

You will also receive the FULL contents of each changed file at HEAD
(when small enough). Use those to understand surrounding code, not just
the hunks. A bug 50 lines above the hunk that the diff doesn't show is
still a bug, but only honk about it if the new delta makes it relevant.

tile-ai/TileOPs is a CUDA/TileLang GPU kernel repo with Python
orchestration and benchmarking. Kernel performance matters enormously
here. A goose that ignores memory access patterns is not doing its job.

# Reading the room (CRITICAL — read this twice)
You will be given the prior conversation on this PR: the PR description,
top-level review bodies from other reviewers, line-anchored inline review
threads, conversation-tab comments from the author and others, AND your
own past reviews on this PR. READ ALL OF IT before honking.

- If the author or another reviewer has already raised, explained,
  acknowledged, or said they are fixing a point — DO NOT honk about it
  again like you discovered it. A goose that doesn't read the room is
  just a noisy goose, and a noisy goose gets ignored.
- If your OWN past review on this PR already raised an issue and the
  author hasn't addressed it in this delta, you MAY follow up — but say
  so explicitly: "the goose has not forgotten —" or "as the goose
  honked at commit `abc1234` —". Don't pretend it's a fresh observation.
- If another reviewer has already correctly raised something you also
  see, you may second the motion briefly — credit them ("@xxx is right
  about the race in `foo.cu:120` —") and add NEW information. Don't
  just echo.
- If you DISAGREE with something the author or a reviewer claimed, you
  may push back — but only with a concrete reason rooted in the actual
  code. "I don't think that's true because line 47 still..." is fine.
  Vague contrarianism is not.
- If the author has explicitly said "this is intentional, will document
  later" or "out of scope for this PR, tracked in issue #N" — believe
  them. Don't honk about it. The goose is mean, not deaf.

# What to hunt for (priority order)
1. **Bugs & logic errors** — off-by-one, race conditions, None/null
   handling, resource leaks, broken invariants, wrong assumptions,
   dead code paths, swapped arguments.
2. **Performance** — wrong algorithm, allocation in hot loops, bad GPU
   memory access patterns, missed parallelism, unnecessary sync, kernel
   launch overhead, tensor shape mistakes.
3. **Test coverage** — new code paths without tests, tests that don't
   actually test what they claim, missing edge cases.

# What to IGNORE (do not honk about these)
- Code style, naming, formatting, docstrings, comments
- "Future work" suggestions
- Minor readability nits
- Anything a linter would catch
- Subjective preferences

# When to stay silent
If this delta has NO real issues worth honking about, output exactly the
single word `SILENT` on its own line and nothing else. A goose that honks
at empty air is just a noisy goose. Silence is a valid review.

"Worth honking about" = a real bug, a real perf issue, or a real test gap.
If the bar feels low, the bar is too low.

# Output format (when you DO have findings)
Markdown in exactly this structure. OMIT empty sections entirely.
Do NOT include any marker or HTML comments — those are added programmatically.

The format below contains HTML <img ...> tags for the goose / feather / egg
icons. Copy each <img> element VERBATIM into your output — preserve every
attribute (src, width, align, alt) exactly. Do NOT replace them with Unicode
emoji like 🪿 / 🪶 / 🥚 (those don't render on every system) and do NOT
replace them with `:goose:` style shortcodes (GitHub passes those through as
the same broken Unicode). The exact <img> tag is what survives all platforms.

## __GOOSE_ICON__ goose review — `{short_sha}`

*honk.* One-line verdict of the delta. Unimpressed is the default.

### __GOOSE_ICON__ Bugs
- `path/to/file.ext:LINE` — What's wrong. Why it matters. What to do.
  Cite the line. Be concrete. Be mean. Be correct.

### __FEATHER_ICON__ Performance
- `path/to/file.ext:LINE` — ...

### __EGG_ICON__ Test gaps
- ...
"""


# Substitute the placeholder strings with the real <img> tags. Done at module
# load time so the rest of the codebase just imports SYSTEM_PROMPT and uses it.
SYSTEM_PROMPT = (
    _SYSTEM_PROMPT_TEMPLATE
    .replace("__GOOSE_ICON__", GOOSE_IMG)
    .replace("__FEATHER_ICON__", FEATHER_IMG)
    .replace("__EGG_ICON__", EGG_IMG)
)


# Hard per-file cap on diff hunks. With 1M context there's plenty of headroom;
# this mostly guards against a single pathological auto-generated file blowing
# up tokens.
_MAX_FILE_DIFF_CHARS = 150_000

# Per-file cap on full file content (post-change). Files above this fall back
# to "diff only" — let the goose work from the hunk plus a note that the
# surrounding context was too big to include.
_MAX_FILE_CONTENT_CHARS = 200_000

# Per-comment-body cap. Humans rarely write more; this is just a guard against
# a pasted log dump pushing one comment to multi-MB.
_MAX_COMMENT_BODY_CHARS = 8_000


def _truncate(text: str, cap: int) -> str:
    if len(text) <= cap:
        return text
    return text[:cap] + f"\n\n*[truncated: {len(text)} → {cap} chars]*"


def build_user_content(
    pr: Any,  # PullRequest, avoid import cycle
    old_sha: str,
    head_sha: str,
    compare_data: dict[str, Any],
    first_time: bool,
    *,
    bot_username: str = "",
    issue_comments: list[Any] | None = None,    # IssueComment
    other_reviews: list[Any] | None = None,     # Review (non-bot)
    own_reviews: list[Any] | None = None,       # Review (bot's own)
    review_comments: list[Any] | None = None,   # ReviewComment (inline)
    full_files: dict[str, str] | None = None,   # path -> full text at head
) -> str:
    """Render the PR + delta + conversation into a single user message.

    The new keyword args are all optional with empty defaults so the function
    stays callable from old test code, but main.py always passes them.
    """
    issue_comments = issue_comments or []
    other_reviews = other_reviews or []
    own_reviews = own_reviews or []
    review_comments = review_comments or []
    full_files = full_files or {}

    lines: list[str] = []

    header = f"# PR #{pr.number}: {pr.title}"
    lines.append(header)
    lines.append(f"**Author**: `{pr.author}`")
    lines.append(f"**Branch**: `{pr.branch}`")
    if first_time:
        lines.append(
            f"**Reviewing**: first-time full review from base `{old_sha[:8]}` → head `{head_sha[:8]}`"
        )
    else:
        lines.append(
            f"**Reviewing**: incremental delta `{old_sha[:8]}..{head_sha[:8]}` "
            "(earlier commits were already reviewed)"
        )
    lines.append("")

    if pr.body and pr.body.strip():
        lines.append("## PR description")
        lines.append(pr.body.strip())
        lines.append("")

    commits = compare_data.get("commits") or []
    if commits:
        lines.append(f"## Commits in this delta ({len(commits)})")
        for c in commits:
            sha = (c.get("sha") or "")[:8]
            msg = ((c.get("commit") or {}).get("message") or "").split("\n", 1)[0]
            lines.append(f"- `{sha}` {msg}")
        lines.append("")

    # ----- Conversation context (the part the goose was missing) -----
    _render_conversation(
        lines,
        pr=pr,
        bot_username=bot_username,
        issue_comments=issue_comments,
        other_reviews=other_reviews,
        review_comments=review_comments,
    )
    _render_own_reviews(lines, own_reviews=own_reviews)

    # ----- The diff itself -----
    files = compare_data.get("files") or []
    lines.append(f"## Diff ({len(files)} file(s) changed)")
    lines.append("")

    for f in files:
        filename = f.get("filename", "?")
        status = f.get("status", "?")
        additions = f.get("additions", 0)
        deletions = f.get("deletions", 0)
        patch = f.get("patch") or ""

        lines.append(f"### `{filename}` — {status} (+{additions}/-{deletions})")
        lines.append("")
        if not patch:
            lines.append("*(no patch available — binary, renamed-only, or too large for GitHub to return)*")
        elif len(patch) > _MAX_FILE_DIFF_CHARS:
            lines.append("```diff")
            lines.append(patch[:_MAX_FILE_DIFF_CHARS])
            lines.append("```")
            lines.append(
                f"\n*[patch truncated: {len(patch)} chars → {_MAX_FILE_DIFF_CHARS}. "
                "Review what you can see; do not invent findings about the hidden portion.]*"
            )
        else:
            lines.append("```diff")
            lines.append(patch)
            lines.append("```")
        lines.append("")

    # ----- Full file contents (post-change) for surrounding context -----
    if full_files:
        lines.append("## Full file contents at HEAD")
        lines.append(
            "*(use these to understand surrounding code beyond the diff hunks; "
            "files above the size cap are omitted and you must work from the "
            "diff alone for those)*"
        )
        lines.append("")
        for path in sorted(full_files.keys()):
            content = full_files[path]
            lines.append(f"### `{path}` (full content)")
            lines.append("")
            lines.append("```")
            lines.append(content)
            lines.append("```")
            lines.append("")

    return "\n".join(lines)


def _render_conversation(
    lines: list[str],
    *,
    pr: Any,
    bot_username: str,
    issue_comments: list[Any],
    other_reviews: list[Any],
    review_comments: list[Any],
) -> None:
    """Render the merged human conversation into `lines` (mutates in place).

    Top-level reviews + issue comments are merged chronologically into a
    single 'Conversation' section. Inline review threads are grouped by
    file/line and rendered as a separate 'Inline review threads' section
    so the goose sees the diff_hunk context for each thread.
    """
    bot_lower = bot_username.lower()

    # --- merged top-level conversation, oldest-first ---
    convo: list[tuple[str, str, str, str]] = []  # (ts, kind, author, body)
    for c in issue_comments:
        if c.author.lower() == bot_lower:
            continue  # skip our own legacy issue comments
        convo.append((c.created_at, "comment", c.author, c.body))
    for r in other_reviews:
        # other_reviews is already filtered to non-bot in main.py, but be safe
        if r.author.lower() == bot_lower:
            continue
        if not (r.body or "").strip() and r.state == "COMMENTED":
            # Empty review body with no inline comments either — skip noise.
            continue
        label = f"review {r.state}"
        convo.append((r.submitted_at, label, r.author, r.body))
    convo.sort(key=lambda t: t[0] or "")

    if convo:
        lines.append(f"## Conversation on this PR ({len(convo)} entries)")
        lines.append("")
        for ts, kind, author, body in convo:
            ts_short = (ts or "")[:19].replace("T", " ")
            lines.append(f"**@{author}** ({kind}, {ts_short}):")
            body_clean = _truncate((body or "").strip(), _MAX_COMMENT_BODY_CHARS)
            if not body_clean:
                lines.append("*(empty body)*")
            else:
                # Quote the body so it's visually distinct from the diff blocks.
                for ln in body_clean.splitlines():
                    lines.append(f"> {ln}")
            lines.append("")

    # --- inline review threads, grouped by root comment ---
    # Build thread map: root_id -> [root, reply, reply, ...]
    if not review_comments:
        return

    threads: dict[int, list[Any]] = {}
    by_id: dict[int, Any] = {c.id: c for c in review_comments}
    for c in review_comments:
        # Find the root by walking in_reply_to_id chains.
        root_id = c.id
        cur = c
        # Cap walk depth in case of cycles (shouldn't happen, be safe)
        for _ in range(20):
            if cur.in_reply_to_id is None:
                root_id = cur.id
                break
            parent = by_id.get(cur.in_reply_to_id)
            if parent is None:
                root_id = cur.id
                break
            cur = parent
        threads.setdefault(root_id, []).append(c)

    # Sort threads by their root's created_at, and replies within a thread by
    # their own created_at.
    sorted_roots = sorted(
        threads.keys(),
        key=lambda rid: (by_id[rid].created_at if rid in by_id else ""),
    )

    if sorted_roots:
        lines.append(f"## Inline review threads ({len(sorted_roots)} thread(s))")
        lines.append("")
        for rid in sorted_roots:
            comments = sorted(threads[rid], key=lambda c: c.created_at or "")
            root = comments[0]
            line_label = f":{root.line}" if root.line is not None else ""
            lines.append(f"### `{root.path}{line_label}`")
            if root.diff_hunk:
                lines.append("")
                lines.append("```diff")
                lines.append(root.diff_hunk)
                lines.append("```")
            for i, c in enumerate(comments):
                ts_short = (c.created_at or "")[:19].replace("T", " ")
                role = "thread start" if i == 0 else "reply"
                is_bot = c.author.lower() == bot_lower
                bot_tag = " (the goose)" if is_bot else ""
                lines.append("")
                lines.append(f"**@{c.author}** ({role}{bot_tag}, {ts_short}):")
                body_clean = _truncate((c.body or "").strip(), _MAX_COMMENT_BODY_CHARS)
                if not body_clean:
                    lines.append("*(empty body)*")
                else:
                    for ln in body_clean.splitlines():
                        lines.append(f"> {ln}")
            lines.append("")


def _render_own_reviews(lines: list[str], *, own_reviews: list[Any]) -> None:
    """Render the bot's own past reviews on this PR (markers stripped).

    These are kept in a dedicated section so the goose can see what it has
    already said and avoid repeating itself, while still being clearly
    labeled as 'past you, not a human reviewer'.
    """
    # Lazy import to avoid a top-level import cycle through src/__init__.
    from . import marker as _marker

    substantive: list[Any] = []
    for r in own_reviews:
        body = _marker.strip_from_body(r.body or "")
        if not body.strip():
            continue
        # Drop content-free silent/docs-only acks — they carry no review value.
        # Substantive reviews always carry the "goose review" header per the
        # system prompt's required output format.
        if "goose review" not in body.lower():
            continue
        substantive.append((r, body))

    if not substantive:
        return

    lines.append(f"## Your own past reviews on this PR ({len(substantive)})")
    lines.append("*(these are YOUR prior honks. Don't repeat the same findings — "
                 "follow up on unaddressed ones explicitly.)*")
    lines.append("")
    for r, body in substantive:
        ts_short = (r.submitted_at or "")[:19].replace("T", " ")
        lines.append(f"### past goose review ({ts_short})")
        lines.append("")
        body_clean = _truncate(body, _MAX_COMMENT_BODY_CHARS)
        for ln in body_clean.splitlines():
            lines.append(f"> {ln}")
        lines.append("")
