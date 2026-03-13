-- pg_mcp_small: Minimal fixture for pg-mcp schema discovery tests
-- Tables: 6, Views: 2, Enums: 2, Indexes: 8, Foreign keys: 4
-- ~100 rows total across tables

\set ON_ERROR_STOP on

-- ---------------------------------------------------------------------------
-- ENUMS
-- ---------------------------------------------------------------------------
CREATE TYPE order_status AS ENUM ('pending', 'paid', 'shipped', 'delivered', 'cancelled');
COMMENT ON TYPE order_status IS 'Order lifecycle status';

CREATE TYPE product_category AS ENUM ('electronics', 'clothing', 'books', 'food');

-- ---------------------------------------------------------------------------
-- TABLES (public schema)
-- ---------------------------------------------------------------------------
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    description TEXT
);
COMMENT ON TABLE categories IS 'Product categories';
COMMENT ON COLUMN categories.name IS 'Unique category name';

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
COMMENT ON TABLE users IS 'Registered users';

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(10,2) NOT NULL CHECK (price >= 0),
    category_id INTEGER NOT NULL REFERENCES categories(id),
    stock INTEGER DEFAULT 0 CHECK (stock >= 0)
);
COMMENT ON TABLE products IS 'Product catalog';
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_products_price ON products(price);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    total_amount DECIMAL(12,2) NOT NULL,
    status order_status DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now()
);
COMMENT ON TABLE orders IS 'Customer orders';
CREATE INDEX idx_orders_user ON orders(user_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created ON orders(created_at);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(10,2) NOT NULL
);
COMMENT ON TABLE order_items IS 'Order line items';
CREATE INDEX idx_order_items_order ON order_items(order_id);

-- ---------------------------------------------------------------------------
-- VIEWS
-- ---------------------------------------------------------------------------
CREATE VIEW active_orders AS
SELECT o.id, o.user_id, o.total_amount, o.status, o.created_at,
       u.name AS customer_name
FROM orders o
JOIN users u ON u.id = o.user_id
WHERE o.status NOT IN ('delivered', 'cancelled');
COMMENT ON VIEW active_orders IS 'Orders not yet delivered or cancelled';

CREATE VIEW product_sales_summary AS
SELECT p.id, p.name, p.price,
       COALESCE(SUM(oi.quantity), 0)::INTEGER AS total_sold,
       COALESCE(SUM(oi.quantity * oi.unit_price), 0)::DECIMAL(12,2) AS total_revenue
FROM products p
LEFT JOIN order_items oi ON oi.product_id = p.id
GROUP BY p.id, p.name, p.price;

-- ---------------------------------------------------------------------------
-- SEED DATA
-- ---------------------------------------------------------------------------
INSERT INTO categories (name, description) VALUES
('electronics', 'Electronic devices and gadgets'),
('clothing', 'Apparel and accessories'),
('books', 'Physical and digital books'),
('food', 'Grocery and consumables');

INSERT INTO users (email, name) VALUES
('alice@example.com', 'Alice Zhang'),
('bob@example.com', 'Bob Li'),
('carol@example.com', 'Carol Wang'),
('dave@example.com', 'Dave Chen'),
('eve@example.com', 'Eve Liu');

INSERT INTO products (name, price, category_id, stock) VALUES
('Laptop Pro', 1299.99, 1, 50),
('Wireless Mouse', 29.99, 1, 200),
('T-Shirt Blue', 19.99, 2, 150),
('SQL Guide Book', 49.99, 3, 80),
('Organic Apples', 5.99, 4, 500);

INSERT INTO orders (user_id, total_amount, status) VALUES
(1, 1329.98, 'delivered'),
(2, 49.99, 'shipped'),
(3, 69.97, 'pending'),
(1, 25.98, 'paid'),
(4, 1299.99, 'delivered');

INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
(1, 1, 1, 1299.99),
(1, 2, 1, 29.99),
(2, 4, 1, 49.99),
(3, 2, 2, 29.99),
(3, 3, 1, 19.99),
(4, 2, 1, 29.99),
(4, 3, 1, 19.99),
(5, 1, 1, 1299.99);

-- Update stats for views
ANALYZE;
