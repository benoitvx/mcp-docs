"""Rewriting in-tree Docs links as Obsidian wikilinks."""

from mcp_docs.sync import rewrite_links

BASE = "https://docs.example.org"
TARGET = "11111111-1111-4111-8111-111111111111"
NAMES = {TARGET: "🔮 Vision produit"}
OUT_OF_TREE = "22222222-2222-4222-8222-222222222222"


def test_markdown_link_keeps_its_text_as_an_alias() -> None:
    source = f"voir [la vision]({BASE}/docs/{TARGET}/)"
    assert rewrite_links(source, BASE, NAMES) == "voir [[🔮 Vision produit|la vision]]"


def test_markdown_link_whose_text_is_the_target_name_drops_the_alias() -> None:
    source = f"[🔮 Vision produit]({BASE}/docs/{TARGET}/)"
    assert rewrite_links(source, BASE, NAMES) == "[[🔮 Vision produit]]"


def test_bare_url_becomes_a_plain_wikilink() -> None:
    source = f"cf {BASE}/docs/{TARGET}/ pour la suite"
    assert rewrite_links(source, BASE, NAMES) == "cf [[🔮 Vision produit]] pour la suite"


def test_url_without_trailing_slash_is_matched() -> None:
    assert rewrite_links(f"{BASE}/docs/{TARGET}", BASE, NAMES) == "[[🔮 Vision produit]]"


def test_uppercase_uuid_is_matched() -> None:
    assert rewrite_links(f"{BASE}/docs/{TARGET.upper()}/", BASE, NAMES) == "[[🔮 Vision produit]]"


def test_link_outside_the_tree_is_left_alone() -> None:
    source = f"[ailleurs]({BASE}/docs/{OUT_OF_TREE}/)"
    assert rewrite_links(source, BASE, NAMES) == source


def test_media_url_is_left_alone() -> None:
    source = f"![img]({BASE}/media/abc/attachments/def.png)"
    assert rewrite_links(source, BASE, NAMES) == source


def test_trailing_slash_on_base_url_is_tolerated() -> None:
    source = f"{BASE}/docs/{TARGET}/"
    assert rewrite_links(source, BASE + "/", NAMES) == "[[🔮 Vision produit]]"
