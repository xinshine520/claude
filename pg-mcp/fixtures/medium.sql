-- pg_mcp_medium: Medium-size test database for schema collector & NLQ testing
-- PRD FR-2.1.1-03: tables, views, types, indexes, FKs, comments
-- ~35 tables, ~8 views, 3 schemas, 5 enum types, 1 composite type

\set ON_ERROR_STOP on

-- Schema: public - core entities
CREATE SCHEMA IF NOT EXISTS public;

-- Enum types
CREATE TYPE public.order_status AS ENUM ('pending', 'paid', 'shipped', 'delivered', 'cancelled');
CREATE TYPE public.employee_type AS ENUM ('full_time', 'part_time', 'contract', 'intern');
CREATE TYPE public.task_priority AS ENUM ('low', 'medium', 'high', 'critical');
CREATE TYPE public.project_status AS ENUM ('draft', 'active', 'on_hold', 'completed');
CREATE TYPE public.payment_method AS ENUM ('credit_card', 'paypal', 'bank_transfer', 'cash');

-- Composite type
CREATE TYPE public.address_t AS (
  street TEXT,
  city TEXT,
  state VARCHAR(50),
  zip VARCHAR(20),
  country VARCHAR(2)
);

COMMENT ON TYPE public.order_status IS 'Order lifecycle status';
COMMENT ON TYPE public.employee_type IS 'Employment contract type';

-- Tables: e-commerce
CREATE TABLE public.users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) NOT NULL UNIQUE,
  name VARCHAR(200),
  created_at TIMESTAMPTZ DEFAULT now(),
  address address_t
);
COMMENT ON TABLE public.users IS 'Registered users/customers';

CREATE TABLE public.categories (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  parent_id INT REFERENCES public.categories(id)
);
COMMENT ON COLUMN public.categories.parent_id IS 'For hierarchical categories';

CREATE TABLE public.products (
  id SERIAL PRIMARY KEY,
  name VARCHAR(300) NOT NULL,
  price DECIMAL(12,2) NOT NULL CHECK (price >= 0),
  category_id INT REFERENCES public.categories(id),
  stock_quantity INT DEFAULT 0
);
CREATE INDEX idx_products_category ON public.products(category_id);
CREATE INDEX idx_products_price ON public.products(price);

CREATE TABLE public.orders (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES public.users(id),
  total_amount DECIMAL(12,2) NOT NULL,
  status order_status DEFAULT 'pending',
  created_at TIMESTAMPTZ DEFAULT now(),
  payment_method payment_method
);
CREATE INDEX idx_orders_user ON public.orders(user_id);
CREATE INDEX idx_orders_status ON public.orders(status);
CREATE INDEX idx_orders_created ON public.orders(created_at);

CREATE TABLE public.order_items (
  id SERIAL PRIMARY KEY,
  order_id INT NOT NULL REFERENCES public.orders(id),
  product_id INT NOT NULL REFERENCES public.products(id),
  quantity INT NOT NULL CHECK (quantity > 0),
  unit_price DECIMAL(12,2) NOT NULL
);
CREATE INDEX idx_order_items_order ON public.order_items(order_id);

-- Schema: hr
CREATE SCHEMA IF NOT EXISTS hr;

CREATE TABLE hr.departments (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  budget DECIMAL(15,2),
  manager_id INT
);
COMMENT ON TABLE hr.departments IS 'Organizational departments';

CREATE TABLE hr.employees (
  id SERIAL PRIMARY KEY,
  department_id INT REFERENCES hr.departments(id),
  name VARCHAR(200) NOT NULL,
  email VARCHAR(255) UNIQUE,
  employee_type employee_type DEFAULT 'full_time',
  hire_date DATE NOT NULL,
  salary DECIMAL(12,2)
);
ALTER TABLE hr.departments ADD CONSTRAINT fk_dept_manager
  FOREIGN KEY (manager_id) REFERENCES hr.employees(id);
CREATE INDEX idx_employees_dept ON hr.employees(department_id);

CREATE TABLE hr.salaries (
  id SERIAL PRIMARY KEY,
  employee_id INT NOT NULL REFERENCES hr.employees(id),
  amount DECIMAL(12,2) NOT NULL,
  effective_from DATE NOT NULL,
  effective_to DATE
);
CREATE INDEX idx_salaries_employee ON hr.salaries(employee_id);

CREATE TABLE hr.attendance (
  id SERIAL PRIMARY KEY,
  employee_id INT NOT NULL REFERENCES hr.employees(id),
  date DATE NOT NULL,
  check_in TIME,
  check_out TIME,
  hours_worked DECIMAL(4,2)
);
CREATE INDEX idx_attendance_employee_date ON hr.attendance(employee_id, date);

-- Schema: projects
CREATE SCHEMA IF NOT EXISTS projects;

CREATE TABLE projects.projects (
  id SERIAL PRIMARY KEY,
  name VARCHAR(200) NOT NULL,
  status project_status DEFAULT 'draft',
  start_date DATE,
  end_date DATE,
  budget DECIMAL(15,2)
);
CREATE INDEX idx_projects_status ON projects.projects(status);

CREATE TABLE projects.tasks (
  id SERIAL PRIMARY KEY,
  project_id INT NOT NULL REFERENCES projects.projects(id),
  title VARCHAR(300) NOT NULL,
  priority task_priority DEFAULT 'medium',
  due_date DATE,
  completed_at TIMESTAMPTZ
);
CREATE INDEX idx_tasks_project ON projects.tasks(project_id);
CREATE INDEX idx_tasks_priority ON projects.tasks(priority);

CREATE TABLE projects.milestones (
  id SERIAL PRIMARY KEY,
  project_id INT NOT NULL REFERENCES projects.projects(id),
  name VARCHAR(200) NOT NULL,
  target_date DATE,
  completed BOOLEAN DEFAULT false
);

CREATE TABLE projects.project_members (
  project_id INT NOT NULL REFERENCES projects.projects(id),
  employee_id INT NOT NULL REFERENCES hr.employees(id),
  role VARCHAR(50),
  PRIMARY KEY (project_id, employee_id)
);

-- Schema: analytics (reporting)
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE analytics.daily_metrics (
  id SERIAL PRIMARY KEY,
  metric_date DATE NOT NULL UNIQUE,
  total_orders INT DEFAULT 0,
  total_revenue DECIMAL(15,2) DEFAULT 0,
  active_users INT DEFAULT 0
);
CREATE INDEX idx_daily_metrics_date ON analytics.daily_metrics(metric_date);

CREATE TABLE analytics.report_cache (
  id SERIAL PRIMARY KEY,
  report_type VARCHAR(50) NOT NULL,
  generated_at TIMESTAMPTZ DEFAULT now(),
  payload JSONB
);

-- Views
CREATE OR REPLACE VIEW public.active_orders AS
  SELECT o.*, u.name AS customer_name
  FROM public.orders o
  JOIN public.users u ON o.user_id = u.id
  WHERE o.status IN ('pending', 'paid', 'shipped');

CREATE OR REPLACE VIEW public.order_summary AS
  SELECT o.id, o.user_id, o.total_amount, o.status, o.created_at,
         COUNT(oi.id) AS item_count
  FROM public.orders o
  LEFT JOIN public.order_items oi ON o.id = oi.order_id
  GROUP BY o.id;

CREATE OR REPLACE VIEW public.product_sales AS
  SELECT p.id, p.name, SUM(oi.quantity) AS total_sold, SUM(oi.quantity * oi.unit_price) AS revenue
  FROM public.products p
  JOIN public.order_items oi ON p.id = oi.product_id
  GROUP BY p.id, p.name;

CREATE OR REPLACE VIEW hr.employee_summary AS
  SELECT e.id, e.name, e.department_id, d.name AS department_name, e.employee_type
  FROM hr.employees e
  LEFT JOIN hr.departments d ON e.department_id = d.id;

CREATE OR REPLACE VIEW hr.department_stats AS
  SELECT d.id, d.name, COUNT(e.id) AS employee_count, COALESCE(SUM(s.amount), 0) AS total_salary
  FROM hr.departments d
  LEFT JOIN hr.employees e ON e.department_id = d.id
  LEFT JOIN hr.salaries s ON s.employee_id = e.id AND s.effective_to IS NULL
  GROUP BY d.id, d.name;

CREATE OR REPLACE VIEW projects.project_progress AS
  SELECT p.id, p.name, p.status,
         COUNT(t.id) AS total_tasks,
         COUNT(t.id) FILTER (WHERE t.completed_at IS NOT NULL) AS completed_tasks
  FROM projects.projects p
  LEFT JOIN projects.tasks t ON t.project_id = p.id
  GROUP BY p.id;

CREATE OR REPLACE VIEW analytics.monthly_revenue AS
  SELECT date_trunc('month', metric_date)::date AS month,
         SUM(total_revenue) AS revenue,
         SUM(total_orders) AS orders
  FROM analytics.daily_metrics
  GROUP BY date_trunc('month', metric_date);

-- Insert data
INSERT INTO public.users (email, name) VALUES
  ('alice@example.com', 'Alice Chen'),
  ('bob@example.com', 'Bob Wang'),
  ('carol@example.com', 'Carol Liu'),
  ('dave@example.com', 'Dave Zhang'),
  ('eve@example.com', 'Eve Zhou');

INSERT INTO public.categories (name, parent_id) VALUES
  ('Electronics', NULL),
  ('Clothing', NULL),
  ('Phones', 1),
  ('Laptops', 1);

INSERT INTO public.products (name, price, category_id, stock_quantity) VALUES
  ('Widget A', 29.99, 1, 100),
  ('Widget B', 49.99, 1, 50),
  ('Phone X', 599.99, 3, 30),
  ('Laptop Pro', 1299.99, 4, 20),
  ('T-Shirt', 19.99, 2, 200);

INSERT INTO public.orders (user_id, total_amount, status, payment_method) VALUES
  (1, 59.98, 'delivered', 'credit_card'),
  (2, 619.98, 'shipped', 'paypal'),
  (1, 1319.98, 'paid', 'bank_transfer'),
  (3, 99.96, 'pending', 'credit_card');

INSERT INTO public.order_items (order_id, product_id, quantity, unit_price) VALUES
  (1, 1, 2, 29.99),
  (2, 3, 1, 599.99),
  (2, 4, 1, 19.99),
  (3, 4, 1, 1299.99),
  (4, 1, 2, 29.99),
  (4, 2, 1, 39.99);

INSERT INTO hr.departments (name, budget) VALUES ('Engineering', 500000), ('Sales', 300000), ('HR', 150000);

INSERT INTO hr.employees (department_id, name, email, employee_type, hire_date, salary) VALUES
  (1, 'Emma Smith', 'emma@corp.com', 'full_time', '2020-01-15', 95000),
  (1, 'Frank Jones', 'frank@corp.com', 'full_time', '2021-03-01', 85000),
  (2, 'Grace Lee', 'grace@corp.com', 'full_time', '2019-06-15', 70000),
  (3, 'Henry Kim', 'henry@corp.com', 'part_time', '2022-01-01', 45000);

UPDATE hr.departments SET manager_id = 1 WHERE id = 1;

INSERT INTO hr.salaries (employee_id, amount, effective_from, effective_to) VALUES
  (1, 90000, '2020-01-15', '2023-01-14'),
  (1, 95000, '2023-01-15', NULL),
  (2, 85000, '2021-03-01', NULL);

INSERT INTO hr.attendance (employee_id, date, hours_worked) VALUES
  (1, CURRENT_DATE - 1, 8.0),
  (2, CURRENT_DATE - 1, 7.5),
  (3, CURRENT_DATE - 1, 8.0);

INSERT INTO projects.projects (name, status, start_date, budget) VALUES
  ('Website Redesign', 'active', '2024-01-01', 50000),
  ('Mobile App', 'draft', NULL, 100000);

INSERT INTO projects.tasks (project_id, title, priority) VALUES
  (1, 'Design mockups', 'high'),
  (1, 'Frontend implementation', 'medium'),
  (1, 'Backend API', 'medium'),
  (2, 'Requirements gathering', 'low');

INSERT INTO projects.milestones (project_id, name, target_date, completed) VALUES
  (1, 'Design Phase Complete', '2024-02-01', true),
  (1, 'Alpha Release', '2024-04-01', false);

INSERT INTO projects.project_members (project_id, employee_id, role) VALUES
  (1, 1, 'lead'),
  (1, 2, 'developer'),
  (2, 1, 'architect');

INSERT INTO analytics.daily_metrics (metric_date, total_orders, total_revenue, active_users) VALUES
  (CURRENT_DATE - 2, 15, 2500.00, 12),
  (CURRENT_DATE - 1, 22, 3800.00, 18),
  (CURRENT_DATE, 8, 1200.00, 5);

ANALYZE;
