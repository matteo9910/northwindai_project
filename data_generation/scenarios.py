from __future__ import annotations

from data_generation.config import SCENARIO_B_CUSTOMER_IDS, TOP_CUSTOMER_IDS

TOP_CUSTOMERS_SQL = """
select o.customer_id,
       sum(
           od.unit_price * od.quantity * (1 - od.discount)
       ) as net_revenue
from erp_core.orders o
join erp_core.order_details od on od.order_id = o.order_id
where o.order_date >= date '2025-01-01'
  and o.order_date <= date '2025-12-31'
group by o.customer_id
order by net_revenue desc
limit 10
"""


def assert_controlled_scenarios(cur) -> None:
    cur.execute(TOP_CUSTOMERS_SQL)
    top_customers = {row[0] for row in cur.fetchall()}
    missing = set(TOP_CUSTOMER_IDS) - top_customers
    if missing:
        raise AssertionError(f"Scenario A/C customers missing from top 10: {missing}")
    b_in_top = set(SCENARIO_B_CUSTOMER_IDS) & top_customers
    if b_in_top:
        raise AssertionError(f"Scenario B customers unexpectedly in top 10: {b_in_top}")

    cur.execute(
        """
        with top_customers as (
            select customer_id from (
                select o.customer_id,
                       sum(
                           od.unit_price * od.quantity * (1 - od.discount)
                       ) as net_revenue
                from erp_core.orders o
                join erp_core.order_details od on od.order_id = o.order_id
                where o.order_date between date '2025-01-01' and date '2025-12-31'
                group by o.customer_id
                order by net_revenue desc
                limit 10
            ) ranked
        )
        select avg(s.delay_days), count(distinct cc.communication_id)
        from erp_core.orders o
        join erp_core.order_details od on od.order_id = o.order_id
        join erp_core.products p on p.product_id = od.product_id
        join erp_core.shipments s on s.order_id = o.order_id
        left join erp_docs.customer_communications cc
          on cc.order_id = o.order_id
         and cc.contact_reason = 'complaint'
         and lower(cc.body) similar to '%(delay|late)%'
        where p.supplier_id = 4
          and o.customer_id in (select customer_id from top_customers)
          and o.order_date between date '2025-10-01' and date '2025-12-31'
        """
    )
    avg_delay, complaint_count = cur.fetchone()
    if avg_delay is None or float(avg_delay) <= 0 or complaint_count < 1:
        raise AssertionError("Scenario A probe failed")

    cur.execute(
        """
        with top_customers as (
            select customer_id from (
                select o.customer_id,
                       sum(
                           od.unit_price * od.quantity * (1 - od.discount)
                       ) as net_revenue
                from erp_core.orders o
                join erp_core.order_details od on od.order_id = o.order_id
                where o.order_date between date '2025-01-01' and date '2025-12-31'
                group by o.customer_id
                order by net_revenue desc
                limit 10
            ) ranked
        )
        select count(*)
        from erp_core.orders o
        join erp_core.order_details od on od.order_id = o.order_id
        join erp_core.products p on p.product_id = od.product_id
        join erp_core.shipments s on s.order_id = o.order_id
        where p.supplier_id = 1
          and s.delay_days > 0
          and o.customer_id not in (select customer_id from top_customers)
        """
    )
    if cur.fetchone()[0] < 1:
        raise AssertionError("Scenario B probe failed")

    cur.execute(
        """
        with top_customers as (
            select customer_id from (
                select o.customer_id,
                       sum(
                           od.unit_price * od.quantity * (1 - od.discount)
                       ) as net_revenue
                from erp_core.orders o
                join erp_core.order_details od on od.order_id = o.order_id
                where o.order_date between date '2025-01-01' and date '2025-12-31'
                group by o.customer_id
                order by net_revenue desc
                limit 10
            ) ranked
        )
        select
            coalesce(max(s.delay_days), 0),
            count(distinct cc.communication_id)
        from erp_core.orders o
        join erp_core.order_details od on od.order_id = o.order_id
        join erp_core.products p on p.product_id = od.product_id
        join erp_core.shipments s on s.order_id = o.order_id
        left join erp_docs.customer_communications cc
          on cc.order_id = o.order_id
         and cc.contact_reason = 'complaint'
         and lower(cc.body) not similar to '%(delay|late)%'
        where p.supplier_id = 7
          and o.customer_id in (select customer_id from top_customers)
        """
    )
    max_delay, complaint_count = cur.fetchone()
    if max_delay > 0 or complaint_count < 1:
        raise AssertionError("Scenario C probe failed")

    cur.execute(
        """
        select
            (select lead_time_days
             from erp_docs.supplier_contracts
             where supplier_id = 3),
            (select lead_time_days
             from erp_docs.supplier_contracts
             where supplier_id = 4),
            (select count(*) from erp_docs.customer_communications cc
             join erp_core.order_details od on od.order_id = cc.order_id
             join erp_core.products p on p.product_id = od.product_id
             where p.supplier_id = 3 and cc.contact_reason = 'complaint'),
            (select count(*) from erp_docs.customer_communications cc
             join erp_core.order_details od on od.order_id = cc.order_id
             join erp_core.products p on p.product_id = od.product_id
             where p.supplier_id = 4 and cc.contact_reason = 'complaint')
        """
    )
    grandma_lead, tokyo_lead, grandma_complaints, tokyo_complaints = cur.fetchone()
    if not (grandma_lead > tokyo_lead and grandma_complaints < tokyo_complaints):
        raise AssertionError("Scenario D probe failed")
