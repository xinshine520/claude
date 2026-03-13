-- pg_mcp_large: Large fixture for schema collector budget & RAG testing
-- ~220 tables, ~35 views, 6 schemas, 12 enum types, 100+ indexes
-- PRD FR-2.1.1-03: stress schema retrieval & max_tables_per_db behavior

\set ON_ERROR_STOP on

-- Schemas
CREATE SCHEMA IF NOT EXISTS public;
CREATE SCHEMA IF NOT EXISTS sales;
CREATE SCHEMA IF NOT EXISTS inventory;
CREATE SCHEMA IF NOT EXISTS finance;
CREATE SCHEMA IF NOT EXISTS logistics;
CREATE SCHEMA IF NOT EXISTS catalog;

-- Enum types (12)
CREATE TYPE public.region_t AS ENUM ('north', 'south', 'east', 'west', 'central');
CREATE TYPE public.order_status_t AS ENUM ('draft', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled');
CREATE TYPE public.payment_status_t AS ENUM ('pending', 'authorized', 'captured', 'refunded', 'failed');
CREATE TYPE public.inventory_status_t AS ENUM ('in_stock', 'low_stock', 'out_of_stock', 'discontinued');
CREATE TYPE public.shipment_status_t AS ENUM ('pending', 'picked', 'in_transit', 'delivered', 'returned');
CREATE TYPE public.account_type_t AS ENUM ('asset', 'liability', 'equity', 'revenue', 'expense');
CREATE TYPE public.ledger_entry_t AS ENUM ('debit', 'credit');
CREATE TYPE public.contract_type_t AS ENUM ('supplier', 'customer', 'partner', 'internal');
CREATE TYPE public.audit_action_t AS ENUM ('insert', 'update', 'delete', 'select');
CREATE TYPE public.priority_t AS ENUM ('low', 'medium', 'high', 'urgent');
CREATE TYPE public.approval_status_t AS ENUM ('pending', 'approved', 'rejected');
CREATE TYPE public.currency_t AS ENUM ('USD', 'EUR', 'GBP', 'CNY', 'JPY');

-- Core tables with FKs and data (explicit)
CREATE TABLE public.regions (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  code region_t NOT NULL UNIQUE,
  manager_id INT
);
CREATE INDEX idx_regions_code ON public.regions(code);
COMMENT ON TABLE public.regions IS 'Sales/manufacturing regions';

CREATE TABLE public.warehouses (
  id SERIAL PRIMARY KEY,
  name VARCHAR(200) NOT NULL,
  region_id INT REFERENCES public.regions(id),
  address TEXT,
  capacity_sqft INT
);
CREATE INDEX idx_warehouses_region ON public.warehouses(region_id);

CREATE TABLE public.suppliers (
  id SERIAL PRIMARY KEY,
  name VARCHAR(200) NOT NULL,
  contact_email VARCHAR(255),
  contract_type contract_type_t DEFAULT 'supplier'
);
CREATE INDEX idx_suppliers_type ON public.suppliers(contract_type);

CREATE TABLE catalog.product_lines (
  id SERIAL PRIMARY KEY,
  name VARCHAR(200) NOT NULL,
  description TEXT,
  discontinued BOOLEAN DEFAULT false
);

CREATE TABLE catalog.products (
  id SERIAL PRIMARY KEY,
  product_line_id INT REFERENCES catalog.product_lines(id),
  sku VARCHAR(50) NOT NULL UNIQUE,
  name VARCHAR(300) NOT NULL,
  price DECIMAL(12,2) NOT NULL,
  status inventory_status_t DEFAULT 'in_stock',
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_products_line ON catalog.products(product_line_id);
CREATE INDEX idx_products_sku ON catalog.products(sku);
CREATE INDEX idx_products_status ON catalog.products(status);

CREATE TABLE sales.customers (
  id SERIAL PRIMARY KEY,
  name VARCHAR(200) NOT NULL,
  email VARCHAR(255) UNIQUE,
  region_id INT REFERENCES public.regions(id),
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_customers_region ON sales.customers(region_id);

CREATE TABLE sales.orders (
  id SERIAL PRIMARY KEY,
  customer_id INT NOT NULL REFERENCES sales.customers(id),
  status order_status_t DEFAULT 'draft',
  total_amount DECIMAL(15,2) NOT NULL,
  currency currency_t DEFAULT 'USD',
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_orders_customer ON sales.orders(customer_id);
CREATE INDEX idx_orders_status ON sales.orders(status);
CREATE INDEX idx_orders_created ON sales.orders(created_at);

CREATE TABLE sales.order_lines (
  id SERIAL PRIMARY KEY,
  order_id INT NOT NULL REFERENCES sales.orders(id),
  product_id INT NOT NULL REFERENCES catalog.products(id),
  quantity INT NOT NULL CHECK (quantity > 0),
  unit_price DECIMAL(12,2) NOT NULL
);
CREATE INDEX idx_order_lines_order ON sales.order_lines(order_id);

CREATE TABLE inventory.stock_levels (
  id SERIAL PRIMARY KEY,
  product_id INT NOT NULL REFERENCES catalog.products(id),
  warehouse_id INT NOT NULL REFERENCES public.warehouses(id),
  quantity INT NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (product_id, warehouse_id)
);
CREATE INDEX idx_stock_product ON inventory.stock_levels(product_id);
CREATE INDEX idx_stock_warehouse ON inventory.stock_levels(warehouse_id);

CREATE TABLE finance.accounts (
  id SERIAL PRIMARY KEY,
  code VARCHAR(20) NOT NULL UNIQUE,
  name VARCHAR(200) NOT NULL,
  account_type account_type_t NOT NULL,
  parent_id INT REFERENCES finance.accounts(id)
);
CREATE INDEX idx_accounts_type ON finance.accounts(account_type);

CREATE TABLE finance.transactions (
  id SERIAL PRIMARY KEY,
  account_id INT NOT NULL REFERENCES finance.accounts(id),
  entry_type ledger_entry_t NOT NULL,
  amount DECIMAL(15,2) NOT NULL,
  description TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_transactions_account ON finance.transactions(account_id);
CREATE INDEX idx_transactions_created ON finance.transactions(created_at);

CREATE TABLE logistics.shipments (
  id SERIAL PRIMARY KEY,
  order_id INT REFERENCES sales.orders(id),
  warehouse_id INT REFERENCES public.warehouses(id),
  status shipment_status_t DEFAULT 'pending',
  shipped_at TIMESTAMPTZ,
  delivered_at TIMESTAMPTZ
);
CREATE INDEX idx_shipments_order ON logistics.shipments(order_id);
CREATE INDEX idx_shipments_status ON logistics.shipments(status);

-- Audit/log tables (many rows for aggregation tests)
CREATE TABLE public.audit_log (
  id BIGSERIAL PRIMARY KEY,
  table_name VARCHAR(100) NOT NULL,
  record_id INT NOT NULL,
  action audit_action_t NOT NULL,
  changed_at TIMESTAMPTZ DEFAULT now(),
  user_id INT
);
CREATE INDEX idx_audit_table ON public.audit_log(table_name);
CREATE INDEX idx_audit_changed ON public.audit_log(changed_at);

-- Generate ~200 additional tables across schemas via PL/pgSQL
DO $$
DECLARE
  i INT;
  sch TEXT;
  tbl TEXT;
  schemas TEXT[] := ARRAY['public','sales','inventory','finance','logistics','catalog'];
  sid INT;
BEGIN
  FOR i IN 1..200 LOOP
    sch := schemas[1 + (i % 6)];
    tbl := sch || '.entity_' || i;
    EXECUTE format(
      'CREATE TABLE IF NOT EXISTS %I (
        id SERIAL PRIMARY KEY,
        name VARCHAR(200),
        ref_id INT,
        status VARCHAR(50),
        created_at TIMESTAMPTZ DEFAULT now()
      )', tbl);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_entity_%s_ref ON %I(ref_id)', i, tbl);
    EXECUTE format('CREATE INDEX IF NOT EXISTS idx_entity_%s_status ON %I(status)', i, tbl);
    IF i <= 50 THEN
      EXECUTE format('COMMENT ON TABLE %I IS %L', tbl, 'Generated entity table ' || i);
    END IF;
  END LOOP;
END $$;

-- Views (~35)
CREATE VIEW public.region_summary AS
  SELECT r.id, r.name, r.code, COUNT(w.id) AS warehouse_count
  FROM public.regions r LEFT JOIN public.warehouses w ON w.region_id = r.id
  GROUP BY r.id, r.name, r.code;

CREATE VIEW sales.customer_orders AS
  SELECT c.id, c.name, COUNT(o.id) AS order_count, COALESCE(SUM(o.total_amount), 0) AS total_spent
  FROM sales.customers c LEFT JOIN sales.orders o ON o.customer_id = c.id
  GROUP BY c.id, c.name;

CREATE VIEW sales.order_detail AS
  SELECT o.id, o.customer_id, c.name AS customer_name, o.status, o.total_amount,
         COUNT(ol.id) AS line_count
  FROM sales.orders o
  JOIN sales.customers c ON c.id = o.customer_id
  LEFT JOIN sales.order_lines ol ON ol.order_id = o.id
  GROUP BY o.id, o.customer_id, c.name, o.status, o.total_amount;

CREATE VIEW inventory.stock_summary AS
  SELECT p.id, p.sku, p.name, p.status,
         COALESCE(SUM(sl.quantity), 0)::INT AS total_stock
  FROM catalog.products p
  LEFT JOIN inventory.stock_levels sl ON sl.product_id = p.id
  GROUP BY p.id, p.sku, p.name, p.status;

CREATE VIEW finance.balance_sheet AS
  SELECT a.code, a.name, a.account_type,
         SUM(CASE WHEN t.entry_type = 'debit' THEN t.amount ELSE -t.amount END) AS balance
  FROM finance.accounts a
  LEFT JOIN finance.transactions t ON t.account_id = a.id
  GROUP BY a.id, a.code, a.name, a.account_type;

CREATE VIEW logistics.pending_shipments AS
  SELECT s.*, o.total_amount
  FROM logistics.shipments s
  JOIN sales.orders o ON o.id = s.order_id
  WHERE s.status IN ('pending', 'picked', 'in_transit');

-- More views: public has entity_6, entity_12, entity_18, ... (i where i%6=0)
DO $$
DECLARE i INT; eid INT;
BEGIN
  FOR i IN 1..30 LOOP
    eid := i * 6;
    IF eid > 200 THEN EXIT; END IF;
    BEGIN
      EXECUTE format(
        'CREATE OR REPLACE VIEW public.view_entity_%s AS SELECT id, name, ref_id, status FROM public.entity_%s',
        eid, eid
      );
    EXCEPTION WHEN OTHERS THEN NULL;
    END;
  END LOOP;
END $$;

-- Simpler: create views over explicit entity tables
CREATE VIEW public.view_recent_orders AS
  SELECT id, customer_id, status, total_amount, created_at FROM sales.orders ORDER BY created_at DESC LIMIT 100;

CREATE VIEW catalog.low_stock_products AS
  SELECT p.* FROM catalog.products p
  JOIN inventory.stock_levels sl ON sl.product_id = p.id
  GROUP BY p.id HAVING SUM(sl.quantity) < 10;

-- Seed data for core tables
INSERT INTO public.regions (name, code) VALUES
  ('North America', 'north'),
  ('Europe', 'east'),
  ('Asia Pacific', 'central');

INSERT INTO public.warehouses (name, region_id, capacity_sqft) VALUES
  ('WH-001', 1, 50000),
  ('WH-002', 1, 75000),
  ('WH-003', 2, 30000),
  ('WH-004', 3, 100000);

INSERT INTO public.suppliers (name, contact_email) VALUES
  ('Acme Corp', 'supply@acme.com'),
  ('Global Parts', 'orders@globalparts.com'),
  ('Tech Supplies', 'sales@techsupplies.com');

INSERT INTO catalog.product_lines (name, description) VALUES
  ('Electronics', 'Consumer electronics'),
  ('Office', 'Office supplies'),
  ('Furniture', 'Office furniture');

INSERT INTO catalog.products (product_line_id, sku, name, price, status) VALUES
  (1, 'ELEC-001', 'Monitor 24"', 299.99, 'in_stock'),
  (1, 'ELEC-002', 'Keyboard Wireless', 79.99, 'in_stock'),
  (1, 'ELEC-003', 'Mouse Ergo', 49.99, 'low_stock'),
  (2, 'OFF-001', 'Stapler', 12.99, 'in_stock'),
  (2, 'OFF-002', 'Notebook A4', 5.99, 'in_stock'),
  (3, 'FURN-001', 'Desk Chair', 249.99, 'in_stock');

INSERT INTO sales.customers (name, email, region_id) VALUES
  ('Alpha Inc', 'alpha@example.com', 1),
  ('Beta Ltd', 'beta@example.com', 2),
  ('Gamma Corp', 'gamma@example.com', 1),
  ('Delta LLC', 'delta@example.com', 3),
  ('Epsilon Co', 'epsilon@example.com', 2);

INSERT INTO sales.orders (customer_id, status, total_amount) VALUES
  (1, 'delivered', 379.98),
  (2, 'shipped', 305.98),
  (1, 'processing', 249.99),
  (3, 'draft', 59.98),
  (4, 'confirmed', 79.99);

INSERT INTO sales.order_lines (order_id, product_id, quantity, unit_price) VALUES
  (1, 1, 1, 299.99),
  (1, 2, 1, 79.99),
  (2, 1, 1, 299.99),
  (2, 4, 1, 5.99),
  (3, 6, 1, 249.99),
  (4, 2, 2, 29.99),
  (5, 3, 1, 49.99);

INSERT INTO inventory.stock_levels (product_id, warehouse_id, quantity) VALUES
  (1, 1, 100),
  (1, 2, 50),
  (2, 1, 200),
  (3, 1, 8),
  (4, 1, 500),
  (5, 1, 1000),
  (6, 1, 30),
  (6, 3, 25);

INSERT INTO finance.accounts (code, name, account_type) VALUES
  ('1000', 'Cash', 'asset'),
  ('1100', 'Receivables', 'asset'),
  ('2000', 'Payables', 'liability'),
  ('3000', 'Equity', 'equity'),
  ('4000', 'Revenue', 'revenue'),
  ('5000', 'COGS', 'expense');

INSERT INTO finance.transactions (account_id, entry_type, amount, description) VALUES
  (1, 'debit', 10000.00, 'Opening'),
  (4, 'credit', 10000.00, 'Opening'),
  (5, 'credit', 685.96, 'Order #1'),
  (1, 'debit', 685.96, 'Order #1 payment'),
  (5, 'credit', 305.98, 'Order #2');

INSERT INTO logistics.shipments (order_id, warehouse_id, status) VALUES
  (1, 1, 'delivered'),
  (2, 1, 'in_transit'),
  (3, 1, 'pending');

INSERT INTO public.audit_log (table_name, record_id, action, user_id)
  SELECT 'orders', n, 'select', 1 FROM generate_series(1, 50) n;

-- Bulk insert into generated entity tables
DO $$
DECLARE
  i INT;
  sch TEXT;
  tbl TEXT;
BEGIN
  FOR i IN 1..200 LOOP
    sch := (ARRAY['public','sales','inventory','finance','logistics','catalog'])[1 + (i % 6)];
    tbl := sch || '.entity_' || i;
    EXECUTE format(
      'INSERT INTO %I (name, ref_id, status) SELECT ''Item '' || n, (n %% 10), CASE n %% 3 WHEN 0 THEN ''active'' WHEN 1 THEN ''pending'' ELSE ''inactive'' END FROM generate_series(1, 5) n',
      tbl
    );
  END LOOP;
END $$;

ANALYZE;
