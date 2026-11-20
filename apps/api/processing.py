"""Local PDF demonstration processing; live parser isolation and scanning are release gates."""

import pymupdf

from apps.api.domain import PolicyError


def sample_pdf(title: str, issuer: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    page.draw_rect(pymupdf.Rect(24, 24, 818, 571), color=(0.12, 0.29, 0.5), width=3)
    page.insert_text((70, 110), "CERTVAULT / SAMPLE CREDENTIAL", fontsize=14)
    page.insert_text((70, 190), "Certificate of achievement", fontsize=32)
    page.insert_text((70, 265), title, fontsize=23)
    page.insert_text((70, 320), f"Issuer: {issuer}", fontsize=16)
    page.insert_text((70, 370), "Issued to: Demo learner", fontsize=16)
    page.insert_text((70, 430), "Synthetic sample - not an authentic credential", fontsize=13)
    output = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return output


def extract_pdf(data: bytes, *, ocr=False) -> str:
    if not data.startswith(b"%PDF-"):
        raise PolicyError("Only PDF content is accepted in this milestone")
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if doc.is_encrypted or not 1 <= len(doc) <= 100:
                raise PolicyError("Encrypted or over-100-page PDFs require manual review")
            if doc.embfile_count():
                raise PolicyError("Embedded files require manual review")
            # Reject active actions before exposing a preview/download.
            for xref in range(1, doc.xref_length()):
                obj = doc.xref_object(xref)
                if any(
                    key in obj for key in ("/JavaScript", "/Launch", "/OpenAction", "/RichMedia")
                ):
                    raise PolicyError("Active PDF content is unsupported")
            texts = []
            ocr_pages = 0
            for page in doc:
                page_text = page.get_text()[:10000]
                if ocr and len(page_text.strip()) < 30:
                    ocr_pages += 1
                    if ocr_pages > 3:
                        raise PolicyError("OCR page limit exceeded; manual review required")
                    page_text = page.get_text(
                        textpage=page.get_textpage_ocr(language="eng", dpi=150, full=True)
                    )[:10000]
                texts.append(page_text)
                # Preserve PDF hyperlink targets as data for issuer review; never fetch them here.
                for link in page.get_links()[:20]:
                    uri = link.get("uri", "")
                    if uri.startswith("https://") and len(uri) <= 1000:
                        texts.append("Verification reference: " + uri)
            text = "\n".join(texts)[:50000]
            if not text.strip():
                raise PolicyError("Scanned PDF needs OCR; local OCR is not configured")
            return text
    except PolicyError:
        raise
    except Exception as exc:
        raise PolicyError("Malformed PDF; unable to safely extract text") from exc


def extract_document(data: bytes, *, ocr: bool) -> str:
    """Decode images only inside the same resource-limited parser used for PDFs."""
    from apps.api.documents import extension

    if extension(data) == ".pdf":
        return extract_pdf(data, ocr=ocr)
    import struct

    if extension(data) == ".png":
        width, height = struct.unpack_from(">II", data, 16)
    else:
        cursor = 2
        width = height = 0
        while cursor + 4 <= len(data) and data[cursor] == 0xFF:
            cursor += 1
            while cursor < len(data) and data[cursor] == 0xFF:
                cursor += 1
            marker = data[cursor]
            size = int.from_bytes(data[cursor + 1 : cursor + 3], "big")
            if marker in (0xC0, 0xC1, 0xC2):
                height, width = struct.unpack_from(">HH", data, cursor + 4)
                break
            if size < 2 or marker in (0xDA, 0xD9):
                break
            cursor += 1 + size
    if not 0 < width * height <= 12_000_000:
        raise PolicyError("Unsupported image dimensions")
    pix = pymupdf.Pixmap(data)
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)
    if pix.colorspace and pix.colorspace.n != 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    pdf = pix.pdfocr_tobytes(language="eng")
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        text = document[0].get_text()[:50000].strip()
    if not text:
        raise PolicyError("No readable certificate text found")
    return text
