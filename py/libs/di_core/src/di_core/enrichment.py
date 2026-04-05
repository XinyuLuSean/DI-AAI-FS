"""Chunk enrichment for retrieval readiness.

After chunking and routing, chunks are plain text blobs with page provenance.
This module populates the retrieval metadata fields so downstream retrieval,
ranking, and citation systems can leverage document-level signals without
re-inspecting the full document.

Enrichment is a separate step (not baked into the chunker) because it
depends on signals that may arrive after chunking: routing results,
section detection, parse quality assessment.

Call enrich_chunks_for_retrieval() once after all prior pipeline stages
(parse, route, chunk, section detect) are complete.
"""

from __future__ import annotations

from data_model import Document, DocumentChunk, SectionLabel

from di_core.section_detector import detect_sections, section_label_for_chunk


def enrich_chunks_for_retrieval(doc: Document) -> Document:
    """Populate retrieval metadata on every chunk using document-level signals.

    Mutates doc.chunks in place and stores detected sections on doc.sections.
    Returns the document for pipeline chaining.
    """
    doc_type = ""
    if doc.routing:
        doc_type = doc.routing.predicted_type.value

    parse_quality = ""
    if doc.parse_meta:
        parse_quality = doc.parse_meta.quality.value

    source_filename = doc.filename

    sections = detect_sections(doc)
    doc.sections = sections

    for chunk in doc.chunks:
        chunk.doc_type = doc_type
        chunk.source_filename = source_filename
        chunk.parse_quality = parse_quality
        chunk.section_label = section_label_for_chunk(
            sections, chunk.page_numbers, chunk.char_start,
        )

    return doc
