-- Northwind base table structure adapted from pthom/northwind_psql.
-- Project tables live in erp_core, never public.
set search_path to erp_core;

CREATE TABLE IF NOT EXISTS categories (
    category_id smallint NOT NULL,
    category_name character varying(15) NOT NULL,
    description text,
    picture bytea
);


--
-- Name: customer_customer_demo; Type: TABLE; Schema: public; Owner: -; Tablespace: 
--

CREATE TABLE IF NOT EXISTS customer_customer_demo (
    customer_id character varying(5) NOT NULL,
    customer_type_id character varying(5) NOT NULL
);


--
-- Name: customer_demographics; Type: TABLE; Schema: public; Owner: -; Tablespace: 
--

CREATE TABLE IF NOT EXISTS customer_demographics (
    customer_type_id character varying(5) NOT NULL,
    customer_desc text
);


--
-- Name: customers; Type: TABLE; Schema: public; Owner: -; Tablespace: 
--

CREATE TABLE IF NOT EXISTS customers (
    customer_id character varying(5) NOT NULL,
    company_name character varying(40) NOT NULL,
    contact_name character varying(30),
    contact_title character varying(30),
    address character varying(60),
    city character varying(15),
    region character varying(15),
    postal_code character varying(10),
    country character varying(15),
    phone character varying(24),
    fax character varying(24)
);


--
-- Name: employees; Type: TABLE; Schema: public; Owner: -; Tablespace: 
--

CREATE TABLE IF NOT EXISTS employees (
    employee_id smallint NOT NULL,
    last_name character varying(20) NOT NULL,
    first_name character varying(10) NOT NULL,
    title character varying(30),
    title_of_courtesy character varying(25),
    birth_date date,
    hire_date date,
    address character varying(60),
    city character varying(15),
    region character varying(15),
    postal_code character varying(10),
    country character varying(15),
    home_phone character varying(24),
    extension character varying(4),
    photo bytea,
    notes text,
    reports_to smallint,
    photo_path character varying(255)
);


--
-- Name: employee_territories; Type: TABLE; Schema: public; Owner: -; Tablespace: 
--

CREATE TABLE IF NOT EXISTS employee_territories (
    employee_id smallint NOT NULL,
    territory_id character varying(20) NOT NULL
);




--
-- Name: order_details; Type: TABLE; Schema: public; Owner: -; Tablespace: 
--

CREATE TABLE IF NOT EXISTS order_details (
    order_id smallint NOT NULL,
    product_id smallint NOT NULL,
    unit_price real NOT NULL,
    quantity smallint NOT NULL,
    discount real NOT NULL
);


--
-- Name: orders; Type: TABLE; Schema: public; Owner: -; Tablespace: 
--

CREATE TABLE IF NOT EXISTS orders (
    order_id smallint NOT NULL,
    customer_id character varying(5),
    employee_id smallint,
    order_date date,
    required_date date,
    shipped_date date,
    ship_via smallint,
    freight real,
    ship_name character varying(40),
    ship_address character varying(60),
    ship_city character varying(15),
    ship_region character varying(15),
    ship_postal_code character varying(10),
    ship_country character varying(15)
);


--
-- Name: products; Type: TABLE; Schema: public; Owner: -; Tablespace: 
--

CREATE TABLE IF NOT EXISTS products (
    product_id smallint NOT NULL,
    product_name character varying(40) NOT NULL,
    supplier_id smallint,
    category_id smallint,
    quantity_per_unit character varying(20),
    unit_price real,
    units_in_stock smallint,
    units_on_order smallint,
    reorder_level smallint,
    discontinued integer NOT NULL
);


--
-- Name: region; Type: TABLE; Schema: public; Owner: -; Tablespace: 
--

CREATE TABLE IF NOT EXISTS region (
    region_id smallint NOT NULL,
    region_description character varying(60) NOT NULL
);


--
-- Name: shippers; Type: TABLE; Schema: public; Owner: -; Tablespace: 
--

CREATE TABLE IF NOT EXISTS shippers (
    shipper_id smallint NOT NULL,
    company_name character varying(40) NOT NULL,
    phone character varying(24)
);



--
-- Name: suppliers; Type: TABLE; Schema: public; Owner: -; Tablespace: 
--

CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id smallint NOT NULL,
    company_name character varying(40) NOT NULL,
    contact_name character varying(30),
    contact_title character varying(30),
    address character varying(60),
    city character varying(15),
    region character varying(15),
    postal_code character varying(10),
    country character varying(15),
    phone character varying(24),
    fax character varying(24),
    homepage text
);


--
-- Name: territories; Type: TABLE; Schema: public; Owner: -; Tablespace: 
--

CREATE TABLE IF NOT EXISTS territories (
    territory_id character varying(20) NOT NULL,
    territory_description character varying(60) NOT NULL,
    region_id smallint NOT NULL
);


--
-- Name: us_states; Type: TABLE; Schema: public; Owner: -; Tablespace: 
--

CREATE TABLE IF NOT EXISTS us_states (
    state_id smallint NOT NULL,
    state_name character varying(100),
    state_abbr character varying(2),
    state_region character varying(50)
);


--
-- Data for Name: categories; Type: TABLE DATA; Schema: public; Owner: -
--


-- Primary keys from the source dump, guarded for migration replay safety.

do $constraint$
begin
    if not exists (
        select 1
        from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'erp_core'
          and t.relname = 'categories'
          and c.conname = 'pk_categories'
    ) then
        alter table only categories add constraint pk_categories PRIMARY KEY (category_id);
    end if;
end
$constraint$;

do $constraint$
begin
    if not exists (
        select 1
        from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'erp_core'
          and t.relname = 'customer_customer_demo'
          and c.conname = 'pk_customer_customer_demo'
    ) then
        alter table only customer_customer_demo add constraint pk_customer_customer_demo PRIMARY KEY (customer_id, customer_type_id);
    end if;
end
$constraint$;

do $constraint$
begin
    if not exists (
        select 1
        from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'erp_core'
          and t.relname = 'customer_demographics'
          and c.conname = 'pk_customer_demographics'
    ) then
        alter table only customer_demographics add constraint pk_customer_demographics PRIMARY KEY (customer_type_id);
    end if;
end
$constraint$;

do $constraint$
begin
    if not exists (
        select 1
        from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'erp_core'
          and t.relname = 'customers'
          and c.conname = 'pk_customers'
    ) then
        alter table only customers add constraint pk_customers PRIMARY KEY (customer_id);
    end if;
end
$constraint$;

do $constraint$
begin
    if not exists (
        select 1
        from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'erp_core'
          and t.relname = 'employees'
          and c.conname = 'pk_employees'
    ) then
        alter table only employees add constraint pk_employees PRIMARY KEY (employee_id);
    end if;
end
$constraint$;

do $constraint$
begin
    if not exists (
        select 1
        from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'erp_core'
          and t.relname = 'employee_territories'
          and c.conname = 'pk_employee_territories'
    ) then
        alter table only employee_territories add constraint pk_employee_territories PRIMARY KEY (employee_id, territory_id);
    end if;
end
$constraint$;

do $constraint$
begin
    if not exists (
        select 1
        from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'erp_core'
          and t.relname = 'order_details'
          and c.conname = 'pk_order_details'
    ) then
        alter table only order_details add constraint pk_order_details PRIMARY KEY (order_id, product_id);
    end if;
end
$constraint$;

do $constraint$
begin
    if not exists (
        select 1
        from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'erp_core'
          and t.relname = 'orders'
          and c.conname = 'pk_orders'
    ) then
        alter table only orders add constraint pk_orders PRIMARY KEY (order_id);
    end if;
end
$constraint$;

do $constraint$
begin
    if not exists (
        select 1
        from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'erp_core'
          and t.relname = 'products'
          and c.conname = 'pk_products'
    ) then
        alter table only products add constraint pk_products PRIMARY KEY (product_id);
    end if;
end
$constraint$;

do $constraint$
begin
    if not exists (
        select 1
        from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'erp_core'
          and t.relname = 'region'
          and c.conname = 'pk_region'
    ) then
        alter table only region add constraint pk_region PRIMARY KEY (region_id);
    end if;
end
$constraint$;

do $constraint$
begin
    if not exists (
        select 1
        from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'erp_core'
          and t.relname = 'shippers'
          and c.conname = 'pk_shippers'
    ) then
        alter table only shippers add constraint pk_shippers PRIMARY KEY (shipper_id);
    end if;
end
$constraint$;

do $constraint$
begin
    if not exists (
        select 1
        from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'erp_core'
          and t.relname = 'suppliers'
          and c.conname = 'pk_suppliers'
    ) then
        alter table only suppliers add constraint pk_suppliers PRIMARY KEY (supplier_id);
    end if;
end
$constraint$;

do $constraint$
begin
    if not exists (
        select 1
        from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'erp_core'
          and t.relname = 'territories'
          and c.conname = 'pk_territories'
    ) then
        alter table only territories add constraint pk_territories PRIMARY KEY (territory_id);
    end if;
end
$constraint$;

do $constraint$
begin
    if not exists (
        select 1
        from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'erp_core'
          and t.relname = 'us_states'
          and c.conname = 'pk_usstates'
    ) then
        alter table only us_states add constraint pk_usstates PRIMARY KEY (state_id);
    end if;
end
$constraint$;


