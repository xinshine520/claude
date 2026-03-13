-- Test database seed for pg-mcp E2E tests
-- Creates users, departments, and sample data for E2E scenarios

\set ON_ERROR_STOP on

-- ---------------------------------------------------------------------------
-- TABLES
-- ---------------------------------------------------------------------------
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(10,2) NOT NULL CHECK (price >= 0),
    category_id INTEGER NOT NULL REFERENCES categories(id),
    stock INTEGER DEFAULT 0
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    total_amount DECIMAL(12,2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(10,2) NOT NULL
);

-- ---------------------------------------------------------------------------
-- SEED DATA
-- ---------------------------------------------------------------------------
INSERT INTO categories (name, description) VALUES
('electronics', 'Electronic devices'),
('clothing', 'Apparel'),
('books', 'Books'),
('food', 'Grocery');

INSERT INTO users (email, name) VALUES
('alice@example.com', 'Alice Zhang'),
('bob@example.com', 'Bob Li'),
('carol@example.com', 'Carol Wang'),
('dave@example.com', 'Dave Chen'),
('eve@example.com', 'Eve Liu');

INSERT INTO departments (name) VALUES
('Engineering'),
('Sales'),
('Marketing');

INSERT INTO products (name, price, category_id, stock) VALUES
('Laptop Pro', 1299.99, 1, 50),
('Wireless Mouse', 29.99, 1, 200),
('T-Shirt Blue', 19.99, 2, 150),
('SQL Guide Book', 49.99, 3, 80),
('Organic Apples', 5.99, 4, 500);

INSERT INTO orders (user_id, total_amount) VALUES
(1, 1329.98),
(2, 49.99),
(3, 69.97),
(1, 25.98),
(4, 1299.99);

INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
(1, 1, 1, 1299.99),
(1, 2, 1, 29.99),
(2, 4, 1, 49.99),
(3, 2, 2, 29.99),
(3, 3, 1, 19.99),
(4, 2, 1, 29.99),
(4, 3, 1, 19.99),
(5, 1, 1, 1299.99);

ANALYZE;
