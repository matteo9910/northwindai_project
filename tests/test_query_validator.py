from __future__ import annotations

from backend.query.validator import validate_sql


def test_validator_accepts_schema_qualified_select_and_injects_limit():
    result = validate_sql("select customer_id from erp_core.customers")

    assert result.allowed is True
    assert result.statement_type == "SELECT"
    assert result.referenced_schemas == ["erp_core"]
    assert result.referenced_tables == ["erp_core.customers"]
    assert result.effective_sql is not None
    assert "LIMIT 1000" in result.effective_sql


def test_validator_accepts_with_query():
    result = validate_sql(
        """
        with recent_orders as (
            select order_id from erp_core.orders limit 5
        )
        select order_id from recent_orders
        """
    )

    assert result.allowed is True
    assert result.effective_sql is not None


def test_validator_caps_existing_limit():
    result = validate_sql("select order_id from erp_core.orders limit 5000")

    assert result.allowed is True
    assert result.effective_sql is not None
    assert "LIMIT 1000" in result.effective_sql


def test_validator_rejects_mutations():
    blocked_sql = [
        "insert into erp_core.customers (customer_id, company_name) values ('X', 'Y')",
        "update erp_core.customers set company_name = 'X'",
        "delete from erp_core.customers",
        "drop table erp_core.customers",
        "alter table erp_core.customers add column x text",
        "create table erp_core.x (id int)",
        "truncate erp_core.orders",
        "grant select on erp_core.orders to anon",
    ]

    for sql in blocked_sql:
        result = validate_sql(sql)
        assert result.allowed is False
        assert result.violations


def test_validator_rejects_multiple_statements():
    result = validate_sql(
        "select * from erp_core.orders; select * from erp_core.products"
    )

    assert result.allowed is False
    assert "multiple_statements" in result.violations


def test_validator_rejects_non_allowlisted_schema():
    result = validate_sql("select * from public.orders")

    assert result.allowed is False
    assert "schema_not_allowed:public" in result.violations
    assert "table_not_allowed:public.orders" in result.violations


def test_validator_rejects_unqualified_table():
    result = validate_sql("select * from orders")

    assert result.allowed is False
    assert "unqualified_table:orders" in result.violations


def test_validator_rejects_data_modifying_cte():
    # A DML hidden inside a CTE has a read-only Select at the top level.
    cte_dml = [
        ("with x as (insert into erp_core.orders (order_id) values (99) "
         "returning order_id) select order_id from x", "blocked_statement:insert"),
        ("with x as (update erp_core.orders set freight = 0 returning order_id) "
         "select order_id from x", "blocked_statement:update"),
        ("with x as (delete from erp_core.orders returning order_id) "
         "select order_id from x", "blocked_statement:delete"),
    ]

    for sql, expected in cte_dml:
        result = validate_sql(sql)
        assert result.allowed is False
        assert expected in result.violations
