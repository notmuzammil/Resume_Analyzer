import io
import os
import re
from docx import Document
from pypdf import PdfReader

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MIN_TEXT_LENGTH = 50

class ParseError(Exception):
    pass
def extract_text(filename: str, data: bytes) -> str:
    ext = os.path.splitext(filename.lower())[1]
    if ext not in SUPPORTED_EXTENSIONS:
        raise ParseError(f"Unsupported file type '{ext or 'unknown'}'. Please upload PDF or DOCX.")

    try:
        if ext == ".pdf":
            text = _pdf_text(data)
        elif ext == ".docx":
            text = _docx_text(data)
        else:
            text = data.decode("utf-8", errors="ignore")
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError(f"Could not open file: {exc}") from exc

    text = _clean(text)
    if len(text) < MIN_TEXT_LENGTH:
        raise ParseError("No readable text found. The file may be a scanned image or empty.")
    return text


def _pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise ParseError("PDF is password protected.") from exc
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _docx_text(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            cells = []
            for cell in row.cells:
                if cell.text not in cells:
                    cells.append(cell.text)
            parts.append(" | ".join(cells))
    return "\n".join(parts)


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()
