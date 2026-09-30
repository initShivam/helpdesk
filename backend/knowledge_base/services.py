from pathlib import Path

from django.core.files.uploadedfile import UploadedFile
from rest_framework.exceptions import ValidationError

from .models import Document, DocumentChunk
from .embeddings import embed_text
from .vector_store import store_chunk_vector


def _split_content(content: str, size: int = 1200) -> list[str]:
    words = content.split()
    chunks = []
    for index in range(0, len(words), size):
        chunks.append(" ".join(words[index:index + size]))
    return chunks or [""]


def index_document(*, title: str, content: str, source: str = "") -> Document:
    document_embedding, embedding_model = embed_text(content)
    document = Document.objects.create(
        title=title,
        content=content,
        source=source,
        embedding=document_embedding,
        embedding_model=embedding_model,
    )
    chunks = []
    for position, chunk in enumerate(_split_content(content)):
        embedding, chunk_model = embed_text(chunk)
        chunk_model_instance = DocumentChunk(
                document=document,
                content=chunk,
                position=position,
                embedding=embedding,
                embedding_model=chunk_model,
            )
        chunks.append(chunk_model_instance)
    DocumentChunk.objects.bulk_create(chunks)
    for chunk in chunks:
        store_chunk_vector(chunk.id, chunk.embedding, chunk.embedding_model)
    return document


def index_uploaded_file(upload: UploadedFile) -> Document:
    name = Path(upload.name).name
    if upload.size > 10 * 1024 * 1024:
        raise ValidationError({"file": "Files must be no larger than 10 MB."})
    extension = Path(name).suffix.lower()
    if extension not in {".pdf", ".md", ".txt"}:
        raise ValidationError({"file": "Only PDF, Markdown, and text files are supported."})
    if extension == ".pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(upload)
            if len(reader.pages) > 200:
                raise ValidationError({"file": "PDFs may contain no more than 200 pages."})
            content = "\n".join(page.extract_text() or "" for page in reader.pages)
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError({"file": "The uploaded PDF could not be read."}) from exc
    else:
        try:
            content = upload.read().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError({"file": "Text files must use UTF-8 encoding."}) from exc
    if len(content) > 100_000:
        raise ValidationError({"file": "Extracted document content must not exceed 100,000 characters."})
    if not content.strip():
        raise ValidationError({"file": "The uploaded document contains no readable text."})
    return index_document(title=name, content=content, source=name)
