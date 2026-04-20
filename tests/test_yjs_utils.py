"""Tests for Yjs encoding utilities."""

import base64

import pycrdt

from mcp_docs.yjs_utils import text_to_yjs_base64, yjs_base64_to_text


class TestTextToYjsBase64:
    def test_single_paragraph(self) -> None:
        result = text_to_yjs_base64("hello world")
        assert isinstance(result, str)
        # Valid base64 that decodes to a Yjs update
        decoded = base64.b64decode(result)
        doc = pycrdt.Doc()
        doc.apply_update(decoded)
        xml = str(doc.get("document-store", type=pycrdt.XmlFragment))
        assert "hello world" in xml
        assert "<blockGroup>" in xml
        assert "<blockContainer" in xml
        assert "<paragraph" in xml

    def test_multiple_paragraphs(self) -> None:
        result = text_to_yjs_base64("first\n\nsecond\n\nthird")
        doc = pycrdt.Doc()
        doc.apply_update(base64.b64decode(result))
        xml = str(doc.get("document-store", type=pycrdt.XmlFragment))
        assert "first" in xml
        assert "second" in xml
        assert "third" in xml
        # 3 blockContainers for 3 paragraphs
        assert xml.count("<blockContainer") == 3

    def test_empty_text(self) -> None:
        result = text_to_yjs_base64("")
        doc = pycrdt.Doc()
        doc.apply_update(base64.b64decode(result))
        xml = str(doc.get("document-store", type=pycrdt.XmlFragment))
        assert "<paragraph" in xml

    def test_paragraph_has_expected_attrs(self) -> None:
        result = text_to_yjs_base64("x")
        doc = pycrdt.Doc()
        doc.apply_update(base64.b64decode(result))
        xml = str(doc.get("document-store", type=pycrdt.XmlFragment))
        assert 'textColor="default"' in xml
        assert 'textAlignment="left"' in xml
        assert 'backgroundColor="default"' in xml


class TestYjsBase64ToText:
    def test_roundtrip(self) -> None:
        original = "hello world"
        b64 = text_to_yjs_base64(original)
        extracted = yjs_base64_to_text(b64)
        assert extracted == "hello world"

    def test_roundtrip_multiple_paragraphs(self) -> None:
        original = "first\n\nsecond"
        b64 = text_to_yjs_base64(original)
        extracted = yjs_base64_to_text(b64)
        # Whitespace is normalized on extraction
        assert "first" in extracted
        assert "second" in extracted

    def test_empty_base64(self) -> None:
        assert yjs_base64_to_text("") == ""
