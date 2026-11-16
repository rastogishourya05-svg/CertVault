"""Real isolated OCR regression using a synthetic raster-only certificate."""

import os

import pymupdf
import pytest

from apps.api.pipeline_security import isolated_extract
from apps.api.processing import extract_pdf, sample_pdf


def test_inert_xml_metadata_does_not_block_text_extraction():
    with pymupdf.open(
        stream=sample_pdf("Metadata fixture", "Synthetic issuer"), filetype="pdf"
    ) as doc:
        doc.set_xml_metadata('<x:xmpmeta xmlns:x="adobe:ns:meta/"></x:xmpmeta>')
        data = doc.tobytes()
    assert "Metadata fixture" in extract_pdf(data)


@pytest.mark.skipif(
    os.getenv("CERTVAULT_TEST_SECURITY") != "1", reason="Requires built isolated OCR parser"
)
def test_scanned_pdf_ocr_in_restricted_container():
    with pymupdf.open(
        stream=sample_pdf("Python Training", "Synthetic Academy"), filetype="pdf"
    ) as source:
        pixels = source[0].get_pixmap(dpi=150).tobytes("png")
    with pymupdf.open() as raster:
        page = raster.new_page(width=842, height=595)
        page.insert_image(page.rect, stream=pixels)
        data = raster.tobytes()
    result = isolated_extract(data, "certvault-parser:dev")
    assert "Python Training" in result
    assert "Synthetic Academy" in result
