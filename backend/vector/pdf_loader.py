from __future__ import annotations

from pathlib import Path


def load_pdf_text(path: Path) -> str:
    try:
        from langchain_opendataloader_pdf import OpenDataLoaderPDFLoader
    except ImportError as exc:
        raise RuntimeError(
            "langchain-opendataloader-pdf is required for live PDF loading"
        ) from exc

    loader = OpenDataLoaderPDFLoader(
        file_path=path,
        format="text",
        quiet=True,
        split_pages=False,
    )
    documents = loader.load()
    return "\n".join(document.page_content for document in documents)
