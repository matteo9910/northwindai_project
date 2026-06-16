set search_path to erp_core;

-- Warehouse master data.
create table if not exists warehouses (
    warehouse_id bigint generated always as identity primary key,
    code text not null unique,
    name text not null,
    location text,
    warehouse_type text,
    capacity_units integer,
    created_at timestamptz not null default now()
);

-- Shipments connected to customer orders. Source facts for ShipmentDelayEvent in Neo4j.
create table if not exists shipments (
    shipment_id bigint generated always as identity primary key,
    order_id smallint not null references orders(order_id),
    carrier text,
    shipper_id smallint references shippers(shipper_id),
    expected_delivery_date date,
    shipped_date date,
    actual_delivery_date date,
    delay_days integer generated always as (
        case
            when actual_delivery_date is not null and expected_delivery_date is not null
            then actual_delivery_date - expected_delivery_date
        end
    ) stored,
    status text not null default 'pending',
    created_at timestamptz not null default now()
);

-- Invoices generated from orders.
create table if not exists invoices (
    invoice_id bigint generated always as identity primary key,
    invoice_number text not null unique,
    order_id smallint not null references orders(order_id),
    invoice_date date not null,
    due_date date not null,
    payment_date date,
    amount numeric(12,2) not null,
    tax_amount numeric(12,2) not null default 0,
    total_amount numeric(12,2) not null,
    status text not null default 'issued',
    payment_method text,
    created_at timestamptz not null default now()
);

-- Inventory movements: inbound, outbound, return, or adjustment.
create table if not exists inventory_movements (
    movement_id bigint generated always as identity primary key,
    product_id smallint not null references products(product_id),
    warehouse_id bigint not null references warehouses(warehouse_id),
    movement_type text not null,
    quantity integer not null,
    movement_date timestamptz not null,
    reference text,
    created_at timestamptz not null default now()
);

-- Product price change history.
create table if not exists price_history (
    price_history_id bigint generated always as identity primary key,
    product_id smallint not null references products(product_id),
    old_price numeric(12,2),
    new_price numeric(12,2) not null,
    effective_date date not null,
    created_at timestamptz not null default now()
);
