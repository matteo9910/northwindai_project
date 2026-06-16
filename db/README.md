# Database Migrations

This directory contains the PostgreSQL foundation for the NorthwindAI Operational Source of Truth.

Migrations are applied to the Supabase project `northwindai` through the Supabase MCP `apply_migration` tool, in this order:

1. `0001_create_schemas.sql`: creates `erp_core` and `erp_docs`.
2. `0002_northwind_base.sql`: creates the base Northwind tables in `erp_core` and adds primary keys.
3. `0003_northwind_seed.sql`: loads the original Northwind seed data once and adds the original foreign keys.
4. `0004_erp_core_custom.sql`: creates empty custom ERP operational tables.
5. `0005_erp_docs.sql`: creates empty document, communication, contract, and specification tables.

`erp_core` holds transactional ERP facts. `erp_docs` holds document-adjacent records. Project tables should not be created in `public`.

## Verification Queries

```sql
-- schemas
select schema_name
from information_schema.schemata
where schema_name in ('erp_core', 'erp_docs');

-- custom table inventory
select table_schema, table_name
from information_schema.tables
where table_schema in ('erp_core', 'erp_docs')
order by table_schema, table_name;

-- base seed counts
select
    (select count(*) from erp_core.customers) as customers,
    (select count(*) from erp_core.orders) as orders,
    (select count(*) from erp_core.order_details) as order_details;

-- custom tables remain empty after Phase 02
select 'erp_core.warehouses' as table_name, count(*) from erp_core.warehouses
union all select 'erp_core.shipments', count(*) from erp_core.shipments
union all select 'erp_core.invoices', count(*) from erp_core.invoices
union all select 'erp_core.inventory_movements', count(*) from erp_core.inventory_movements
union all select 'erp_core.price_history', count(*) from erp_core.price_history
union all select 'erp_docs.documents', count(*) from erp_docs.documents
union all select 'erp_docs.document_entities', count(*) from erp_docs.document_entities
union all select 'erp_docs.customer_communications', count(*) from erp_docs.customer_communications
union all select 'erp_docs.supplier_contracts', count(*) from erp_docs.supplier_contracts
union all select 'erp_docs.product_specifications', count(*) from erp_docs.product_specifications;
```
