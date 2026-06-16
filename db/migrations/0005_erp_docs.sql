set search_path to erp_docs, erp_core;

-- Registry of generated or processed documents.
create table if not exists documents (
    document_id bigint generated always as identity primary key,
    doc_type text not null,
    title text,
    order_id smallint references erp_core.orders(order_id),
    supplier_id smallint references erp_core.suppliers(supplier_id),
    customer_id character varying(5) references erp_core.customers(customer_id),
    file_path text,
    status text not null default 'generated',
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

-- Bridge between documents and the entities they mention or extract.
create table if not exists document_entities (
    document_entity_id bigint generated always as identity primary key,
    document_id bigint not null references documents(document_id),
    entity_type text not null,
    entity_ref text not null,
    mention text,
    confidence numeric(4,3),
    created_at timestamptz not null default now()
);

-- Customer communications; complaints become CustomerComplaintEvent in Neo4j.
create table if not exists customer_communications (
    communication_id bigint generated always as identity primary key,
    customer_id character varying(5) not null references erp_core.customers(customer_id),
    order_id smallint references erp_core.orders(order_id),
    product_id smallint references erp_core.products(product_id),
    channel text,
    contact_reason text,
    subject text,
    body text,
    sentiment text,
    occurred_at timestamptz not null,
    created_at timestamptz not null default now()
);

-- Structured supplier contracts; source of ContractTermEvent before document parsing.
-- Spec mapping: "leadTimeDays" is stored as lead_time_days in Postgres.
create table if not exists supplier_contracts (
    contract_id bigint generated always as identity primary key,
    supplier_id smallint not null references erp_core.suppliers(supplier_id),
    contract_number text not null unique,
    lead_time_days integer,
    start_date date not null,
    end_date date,
    minimum_order_value numeric(12,2),
    status text not null default 'active',
    created_at timestamptz not null default now()
);

-- Product technical sheets and descriptive content.
create table if not exists product_specifications (
    spec_id bigint generated always as identity primary key,
    product_id smallint not null references erp_core.products(product_id),
    title text,
    spec_text text,
    attributes jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
