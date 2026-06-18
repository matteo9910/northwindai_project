from __future__ import annotations

import argparse

from data_generation.config import SEED, make_rng
from data_generation.docs import (
    generate_communications,
    generate_contracts,
    generate_documents,
    generate_product_specifications,
)
from data_generation.finance import generate_invoices, generate_price_history
from data_generation.loader import connect, load_generated_data
from data_generation.logistics import generate_shipments_and_inventory
from data_generation.masters import fetch_master_data
from data_generation.orders import generate_orders
from data_generation.reset import reset_phase_03_baseline
from data_generation.scenarios import assert_controlled_scenarios


def build_dataset(cur, seed: int) -> dict[str, list]:
    rng, _fake = make_rng(seed)
    master_data = fetch_master_data(cur)
    order_data = generate_orders(master_data, rng)
    logistics = generate_shipments_and_inventory(
        order_data["orders"],
        order_data["order_details"],
        rng,
    )
    contracts = generate_contracts()
    communications = generate_communications(
        order_data["orders"],
        order_data["order_details"],
        logistics["shipments"],
    )
    specs = generate_product_specifications(
        [product.product_id for product in master_data.products]
    )
    documents, document_entities = generate_documents(contracts, communications, specs)

    return {
        **order_data,
        **logistics,
        "invoices": generate_invoices(
            order_data["orders"],
            order_data["order_details"],
            rng,
        ),
        "price_history": generate_price_history(master_data.products),
        "supplier_contracts": contracts,
        "customer_communications": communications,
        "product_specifications": specs,
        "documents": documents,
        "document_entities": document_entities,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic Phase 03 data."
    )
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--reset-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with connect() as conn:
        with conn.cursor() as cur:
            reset_phase_03_baseline(cur)
            if args.reset_only:
                conn.commit()
                print("Phase 03 baseline reset complete.")
                return
            data = build_dataset(cur, args.seed)
            if args.dry_run:
                conn.rollback()
                for key in sorted(k for k in data if k != "order_products"):
                    print(f"{key}: {len(data[key])}")
                return
            load_generated_data(cur, data)
            assert_controlled_scenarios(cur)
        conn.commit()
    print("Phase 03 synthetic data generated and verified.")


if __name__ == "__main__":
    main()
