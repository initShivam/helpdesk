from pathlib import Path

from django.core.files.uploadedfile import UploadedFile

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
    if name.lower().endswith(".pdf"):
        from pypdf import PdfReader

        content = "\n".join(page.extract_text() or "" for page in PdfReader(upload).pages)
    else:
        content = upload.read().decode("utf-8")
    return index_document(title=name, content=content, source=name)
