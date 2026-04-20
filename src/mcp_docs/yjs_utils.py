"""Yjs document encoding utilities for updating Docs content.

The Docs API stores document content as a base64-encoded Yjs (CRDT) update.
The structure follows BlockNote's XML schema:

    <blockGroup>
      <blockContainer id="uuid">
        <paragraph textColor="..." textAlignment="..." backgroundColor="...">
          text
        </paragraph>
      </blockContainer>
      ...
    </blockGroup>

Only plain text paragraphs are supported. Markdown formatting (headings, lists,
bold, italic) would require mapping to specific BlockNote block types and is
out of scope for this first implementation.
"""

import base64
import re
import uuid

import pycrdt

_PARAGRAPH_ATTRS = {
    "textColor": "default",
    "textAlignment": "left",
    "backgroundColor": "default",
}


def text_to_yjs_base64(text: str) -> str:
    """Convert plain text into a base64-encoded Yjs update.

    The text is split on double newlines into separate paragraph blocks.
    """
    doc = pycrdt.Doc()
    paragraphs = text.split("\n\n") if text else [""]
    containers: list[pycrdt.XmlElement] = []
    for paragraph_text in paragraphs:
        children = [pycrdt.XmlText(paragraph_text)] if paragraph_text else []
        paragraph = pycrdt.XmlElement("paragraph", _PARAGRAPH_ATTRS, children)
        containers.append(pycrdt.XmlElement("blockContainer", {"id": str(uuid.uuid4())}, [paragraph]))

    block_group = pycrdt.XmlElement("blockGroup", {}, containers)
    doc["document-store"] = pycrdt.XmlFragment([block_group])
    return base64.b64encode(doc.get_update()).decode("utf-8")


def yjs_base64_to_text(b64: str) -> str:
    """Extract plain text from a base64-encoded Yjs update (strips XML tags)."""
    if not b64:
        return ""
    doc = pycrdt.Doc()
    doc.apply_update(base64.b64decode(b64))
    fragment = doc.get("document-store", type=pycrdt.XmlFragment)
    xml_str = str(fragment)
    text = re.sub(r"<[^>]+>", " ", xml_str)
    return re.sub(r"\s+", " ", text).strip()
