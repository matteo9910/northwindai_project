from __future__ import annotations

from pathlib import Path

from data_generation.contract_documents import contract_document_paths


def test_contract_document_paths_are_scoped_to_supplier_contracts():
    rows = contract_document_paths(Path("data/contracts"))

    assert [(row.supplier_id, row.contract_number, row.file_path) for row in rows] == [
        (1, "CT-1-2020", "data/contracts/CT-1-2020.pdf"),
        (3, "CT-3-2020", "data/contracts/CT-3-2020.pdf"),
        (4, "CT-4-2020", "data/contracts/CT-4-2020.pdf"),
        (7, "CT-7-2020", "data/contracts/CT-7-2020.pdf"),
    ]
