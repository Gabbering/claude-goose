"""Unit tests for the docs-only file filter."""

from __future__ import annotations

from src.path_filter import is_docs_only


def _f(path: str) -> dict:
    """Helper: build a fake GitHub compare-API file entry."""
    return {"filename": path}


def test_empty_is_not_docs_only() -> None:
    # No files = nothing to do; we want process_pr's separate empty-check to handle it,
    # not have docs-only short-circuit.
    assert is_docs_only([]) is False


def test_single_md() -> None:
    assert is_docs_only([_f("README.md")]) is True


def test_docs_dir_only() -> None:
    assert is_docs_only([_f("docs/naming-convention.md"), _f("docs/index.rst")]) is True


def test_mixed_doc_and_code_is_not_docs_only() -> None:
    assert is_docs_only([_f("README.md"), _f("src/foo.py")]) is False


def test_all_code() -> None:
    assert is_docs_only([_f("src/foo.py"), _f("src/bar.cu")]) is False


def test_license_and_changelog() -> None:
    assert is_docs_only([_f("LICENSE"), _f("CHANGELOG.md")]) is True


def test_nested_readme() -> None:
    assert is_docs_only([_f("subdir/README.md")]) is True


def test_md_in_src_still_counts_as_doc() -> None:
    # A .md file anywhere is prose, regardless of directory.
    assert is_docs_only([_f("src/notes.md")]) is True


def test_python_file_with_md_in_name_is_not_doc() -> None:
    # "*.md" only matches the suffix, not substring.
    assert is_docs_only([_f("src/markdown_parser.py")]) is False


def test_rst_file() -> None:
    assert is_docs_only([_f("docs/api.rst")]) is True


def test_contributing() -> None:
    assert is_docs_only([_f("CONTRIBUTING.md"), _f("CONTRIBUTING")]) is True
