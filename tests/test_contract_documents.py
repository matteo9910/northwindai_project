from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from data_generation.contracts import (
    CONTRACT_DOCUMENT_SPECS,
    generate_contract_pdfs,
    hash_contract_files,
)


def test_contract_pdf_generation_is_deterministic(tmp_path: Path):
    first_paths = generate_contract_pdfs(output_dir=tmp_path)
    first_hashes = hash_contract_files(first_paths)
    second_paths = generate_contract_pdfs(output_dir=tmp_path)
    second_hashes = hash_contract_files(second_paths)

    assert [path.name for path in first_paths] == [
        "CT-1-2020.pdf",
        "CT-3-2020.pdf",
        "CT-4-2020.pdf",
        "CT-7-2020.pdf",
    ]
    assert first_hashes == second_hashes
    assert len(first_hashes) == 4


def test_contract_pdf_text_matches_structured_specs(tmp_path: Path):
    paths = generate_contract_pdfs(output_dir=tmp_path)
    text_by_name = {
        path.name: "\n".join(
            page.extract_text() or "" for page in PdfReader(str(path)).pages
        )
        for path in paths
    }

    for spec in CONTRACT_DOCUMENT_SPECS:
        text = text_by_name[f"{spec.contract_number}.pdf"]
        assert spec.company_name in text
        assert spec.contract_number in text
        assert str(spec.minimum_order_value) in text
        assert spec.status in text

    assert "fourteen business days" in text_by_name["CT-4-2020.pdf"]
    assert "Delivery Lead Time" in text_by_name["CT-7-2020.pdf"]
    assert "within thirty business days" in text_by_name["CT-3-2020.pdf"]
    assert "delivery window" in text_by_name["CT-1-2020.pdf"]
