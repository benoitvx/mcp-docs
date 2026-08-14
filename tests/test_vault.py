"""Filesystem layer of the vault sync: naming, frontmatter, safe writes."""

from pathlib import Path

import pytest

from mcp_docs.vault import (
    VaultPathError,
    compose,
    index_vault,
    prune_empty_dirs,
    read_meta,
    resolve_within,
    sanitize_name,
    split_frontmatter,
    write_atomic,
)


class TestSanitizeName:
    def test_strips_zero_width_characters(self) -> None:
        assert sanitize_name("🧩 ​Features") == "🧩 Features"

    def test_replaces_path_and_reserved_characters(self) -> None:
        assert sanitize_name("💜 Feedbacks / intérêt Hub") == "💜 Feedbacks - intérêt Hub"
        assert sanitize_name("Nom du produit : Tchap") == "Nom du produit - Tchap"

    def test_keeps_emoji(self) -> None:
        assert sanitize_name("🐙 LaSuite - Équipe Hub") == "🐙 LaSuite - Équipe Hub"

    def test_collapses_whitespace_and_trailing_dots(self) -> None:
        assert sanitize_name("  a   b  ...") == "a b"

    def test_empty_title_falls_back(self) -> None:
        assert sanitize_name("") == "sans-titre"
        assert sanitize_name("​  ") == "sans-titre"

    def test_truncates_on_byte_boundary(self) -> None:
        name = sanitize_name("é" * 200)
        assert len(name.encode("utf-8")) <= 120
        assert "�" not in name


class TestFrontmatter:
    def test_split_returns_lines_and_body(self) -> None:
        lines, body = split_frontmatter("---\na: 1\nb: 2\n---\n\nhello\n")
        assert lines == ["a: 1", "b: 2"]
        assert body == "hello\n"

    def test_split_without_frontmatter(self) -> None:
        assert split_frontmatter("hello\n") == ([], "hello\n")

    def test_split_with_unterminated_fence(self) -> None:
        assert split_frontmatter("---\na: 1\n") == ([], "---\na: 1\n")

    def test_read_meta_extracts_docs_keys_only(self) -> None:
        meta = read_meta('---\ndocs_id: abc\ntags: [x]\ndocs_title: "a: b"\n---\n\nbody\n')
        assert meta == {"docs_id": "abc", "docs_title": "a: b"}

    def test_compose_writes_frontmatter_then_body(self) -> None:
        assert compose({"docs_id": "abc"}, "hello") == "---\ndocs_id: abc\n---\n\nhello\n"

    def test_compose_quotes_values_needing_it(self) -> None:
        assert 'docs_title: "Nom : Tchap"' in compose({"docs_title": "Nom : Tchap"}, "x")

    def test_compose_preserves_user_frontmatter(self) -> None:
        existing = "---\ndocs_id: old\ntags:\n  - projet\nstatut: en cours\n---\n\nvieux corps\n"
        text = compose({"docs_id": "new"}, "nouveau corps", existing=existing)
        assert "docs_id: new" in text
        assert "docs_id: old" not in text
        assert "tags:\n  - projet" in text
        assert "statut: en cours" in text
        assert text.endswith("nouveau corps\n")


class TestWriteAtomic:
    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c.md"
        write_atomic(target, "hello\n")
        assert target.read_text(encoding="utf-8") == "hello\n"

    def test_leaves_no_temporary_file(self, tmp_path: Path) -> None:
        write_atomic(tmp_path / "c.md", "hello\n")
        assert [p.name for p in tmp_path.iterdir()] == ["c.md"]


class TestResolveWithin:
    def test_accepts_a_path_inside_the_root(self, tmp_path: Path) -> None:
        assert resolve_within(tmp_path, "Docs/a.md") == (tmp_path / "Docs" / "a.md").resolve()

    def test_rejects_parent_traversal(self, tmp_path: Path) -> None:
        with pytest.raises(VaultPathError):
            resolve_within(tmp_path, "../escape.md")

    def test_rejects_absolute_path(self, tmp_path: Path) -> None:
        with pytest.raises(VaultPathError):
            resolve_within(tmp_path, "/etc/passwd")

    def test_rejects_symlink_escaping_the_root(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside_vault"
        outside.mkdir()
        root = tmp_path / "vault"
        root.mkdir()
        (root / "link").symlink_to(outside, target_is_directory=True)
        with pytest.raises(VaultPathError):
            resolve_within(root, "link/note.md")


class TestIndexVault:
    def test_maps_docs_id_to_path(self, tmp_path: Path) -> None:
        write_atomic(tmp_path / "a.md", compose({"docs_id": "id-a"}, "a"))
        write_atomic(tmp_path / "sub" / "b.md", compose({"docs_id": "id-b"}, "b"))
        assert index_vault(tmp_path) == {
            "id-a": tmp_path / "a.md",
            "id-b": tmp_path / "sub" / "b.md",
        }

    def test_ignores_notes_without_docs_id(self, tmp_path: Path) -> None:
        (tmp_path / "perso.md").write_text("---\ntags: [x]\n---\n\nma note\n", encoding="utf-8")
        assert index_vault(tmp_path) == {}

    def test_missing_root_yields_empty_index(self, tmp_path: Path) -> None:
        assert index_vault(tmp_path / "nope") == {}


class TestPruneEmptyDirs:
    def test_removes_empty_directories_only(self, tmp_path: Path) -> None:
        (tmp_path / "empty" / "deeper").mkdir(parents=True)
        write_atomic(tmp_path / "full" / "a.md", "x\n")
        prune_empty_dirs(tmp_path)
        assert not (tmp_path / "empty").exists()
        assert (tmp_path / "full" / "a.md").exists()
        assert tmp_path.exists()
