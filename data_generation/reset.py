from __future__ import annotations


def reset_phase_03_baseline(cur) -> None:
    cur.execute(
        """
        truncate erp_docs.document_entities, erp_docs.documents,
                 erp_docs.customer_communications, erp_docs.supplier_contracts,
                 erp_docs.product_specifications restart identity cascade
        """
    )
    cur.execute(
        """
        truncate erp_core.inventory_movements, erp_core.price_history,
                 erp_core.invoices, erp_core.shipments restart identity cascade
        """
    )
    cur.execute("truncate erp_core.warehouses restart identity cascade")
    cur.execute("delete from erp_core.order_details")
    cur.execute("delete from erp_core.orders")

