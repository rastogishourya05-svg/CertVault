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
            text = "\n".join(texts)[:50000]
            if not text.strip():
                raise PolicyError("Scanned PDF needs OCR; local OCR is not configured")
            return text
    except PolicyError:
        raise
    except Exception as exc:
        raise PolicyError("Malformed PDF; unable to safely extract text") from exc
