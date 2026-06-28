from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import psycopg

from backend.config import Settings, get_settings
from data_generation.contracts import CONTRACT_DOCUMENT_SPECS, DEFAULT_CONTRACT_DIR


@dataclass(frozen=True)
class ContractDocumentPath:
    supplier_id: int
    contract_number: str
    file_path: str


def contract_document_paths(
    contract_dir: Path = DEFAULT_CONTRACT_DIR,
) -> list[ContractDocumentPath]:
    return [
        ContractDocumentPath(
            supplier_id=spec.supplier_id,
            contract_number=spec.contract_number,
            file_path=str(contract_dir / f"{spec.contract_number}.pdf").replace(
                "\\",
                "/",
            ),
        )
        for spec in CONTRACT_DOCUMENT_SPECS
    ]


def apply_contract_document_paths(
    settings: Settings | None = None,
    contract_dir: Path = DEFAULT_CONTRACT_DIR,
) -> int:
    settings = settings or get_settings()
    rows = contract_document_paths(contract_dir=contract_dir)
    updated = 0
    with psycopg.connect(settings.postgres_dsn) as conn:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(
                    """
                    update erp_docs.documents
                    set file_path = %s
                    where doc_type = 'supplier_contract'
                      and supplier_id = %s
                      and metadata->>'contract_number' = %s
                    """,
                    (row.file_path, row.supplier_id, row.contract_number),
                )
                updated += cur.rowcount
        conn.commit()
    return updated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Set supplier contract document file_path values in Postgres."
    )
    parser.add_argument(
        "--contract-dir",
        type=Path,
        default=DEFAULT_CONTRACT_DIR,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    updated = apply_contract_document_paths(contract_dir=args.contract_dir)
    print(f"Updated {updated} supplier contract document file_path values.")


if __name__ == "__main__":
    main()
