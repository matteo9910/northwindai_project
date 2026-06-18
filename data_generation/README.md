# Phase 03 Synthetic Data

Run the deterministic Phase 03 generator with:

```powershell
python -m data_generation.generate
```

The generator uses `SEED = 42` and `AS_OF = 2025-12-31`. The fixed `AS_OF`
anchors “last 12 months” to `2025-01-01..2025-12-31` and “last 3 months” to
`2025-10-01..2025-12-31`, independent of wall-clock time.

Every full run first resets the Phase 03 baseline: Northwind master data is kept,
all generated/custom data is removed, and all operational `orders` plus
`order_details` are deleted. The run then regenerates about 16,200 orders across
`2020-01-01..2025-12-31`.

Useful commands:

```powershell
python -m data_generation.generate --dry-run
python -m data_generation.generate --reset-only
python -m data_generation.generate --seed 42
```

Verification SQL:

```sql
select
  (select count(*) from erp_core.orders where order_date >= '2020-01-01') as synth_orders,
  (select count(*) from erp_core.shipments) as shipments,
  (select count(*) from erp_core.invoices) as invoices,
  (select count(*) from erp_docs.customer_communications) as comms,
  (select count(*) from erp_docs.supplier_contracts) as contracts;

select count(*) from erp_core.orders where order_date < '2020-01-01';

select supplier_id, lead_time_days
from erp_docs.supplier_contracts
where supplier_id in (1, 3, 4, 7)
order by supplier_id;
```

