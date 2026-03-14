# pg_mcp_large 数据库结构参考

## 概述
pg_mcp_large 是一个大型 PostgreSQL 数据库，包含完整的业务数据，包括产品目录、财务、库存、物流、销售等模块。

## 数据库连接
- 主机: 127.0.0.1
- 端口: 5432
- 用户: postgres
- 密码: 123456

## Schema 结构

### 1. catalog (产品目录)
#### 表
| 表名 | 说明 |
|------|------|
| products | 产品表 |
| product_lines | 产品线表 |

#### products 表
| 列名 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| product_line_id | integer | 外键，关联 product_lines |
| sku | varchar | 产品SKU，唯一 |
| name | varchar | 产品名称 |
| price | numeric | 价格 |
| status | inventory_status_t | 库存状态 |
| created_at | timestamptz | 创建时间 |

#### product_lines 表
| 列名 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| name | varchar | 产品线名称 |
| description | text | 描述 |
| discontinued | boolean | 是否停产 |

#### 视图
- `low_stock_products`: 低库存产品视图

---

### 2. finance (财务)
#### 表
| 表名 | 说明 |
|------|------|
| accounts | 账户表 |
| transactions | 交易表 |

#### accounts 表
| 列名 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| code | varchar | 账户代码，唯一 |
| name | varchar | 账户名称 |
| account_type | account_type_t | 账户类型 |
| parent_id | integer | 父账户ID |

#### transactions 表
| 列名 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| account_id | integer | 外键，关联 accounts |
| entry_type | ledger_entry_t | 条目类型（借/贷） |
| amount | numeric | 金额 |
| description | text | 描述 |
| created_at | timestamptz | 创建时间 |

#### 视图
- `balance_sheet`: 资产负债表视图

---

### 3. inventory (库存)
#### 表
| 表名 | 说明 |
|------|------|
| stock_levels | 库存水平表 |

#### stock_levels 表
| 列名 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| product_id | integer | 外键，关联 products |
| warehouse_id | integer | 外键，关联 warehouses |
| quantity | integer | 数量 |
| updated_at | timestamptz | 更新时间 |

#### 视图
- `stock_summary`: 库存汇总视图

---

### 4. logistics (物流)
#### 表
| 表名 | 说明 |
|------|------|
| shipments | 发货表 |

#### shipments 表
| 列名 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| order_id | integer | 订单ID |
| warehouse_id | integer | 仓库ID |
| status | shipment_status_t | 发货状态 |
| shipped_at | timestamptz | 发货时间 |
| delivered_at | timestamptz | 送达时间 |

#### 视图
- `pending_shipments`: 待发货视图

---

### 5. sales (销售)
#### 表
| 表名 | 说明 |
|------|------|
| customers | 客户表 |
| orders | 订单表 |
| order_lines | 订单明细表 |

#### customers 表
| 列名 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| name | varchar | 客户名称 |
| email | varchar | 邮箱 |
| region_id | integer | 外键，关联 regions |
| created_at | timestamptz | 创建时间 |

#### orders 表
| 列名 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| customer_id | integer | 外键，关联 customers |
| status | order_status_t | 订单状态 |
| total_amount | numeric | 总金额 |
| currency | currency_t | 货币类型 |
| created_at | timestamptz | 创建时间 |

#### order_lines 表
| 列名 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| order_id | integer | 外键，关联 orders |
| product_id | integer | 外键，关联 products |
| quantity | integer | 数量 |
| unit_price | numeric | 单价 |

#### 视图
- `customer_orders`: 客户订单视图
- `order_detail`: 订单详情视图

---

### 6. public (公共)
#### 表
| 表名 | 说明 |
|------|------|
| audit_log | 审计日志表 |
| regions | 地区表 |
| warehouses | 仓库表 |
| suppliers | 供应商表 |

#### regions 表
| 列名 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| name | varchar | 地区名称 |
| code | region_t | 地区代码 |
| manager_id | integer | 经理ID |

#### warehouses 表
| 列名 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| name | varchar | 仓库名称 |
| region_id | integer | 外键，关联 regions |
| address | text | 地址 |
| capacity_sqft | integer | 容量（平方英尺） |

#### suppliers 表
| 列名 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| name | varchar | 供应商名称 |
| contact_email | varchar | 联系邮箱 |
| contract_type | contract_type_t | 合同类型 |

#### 视图
- `region_summary`: 地区汇总视图
- `view_recent_orders`: 最近订单视图

---

## 枚举类型 (Enum Types)

| 类型名 | 可选值 |
|--------|--------|
| account_type_t | asset, liability, equity, revenue, expense |
| audit_action_t | insert, update, delete, select |
| contract_type_t | supplier, customer, partner, internal |
| currency_t | USD, EUR, GBP, CNY, JPY |
| inventory_status_t | in_stock, low_stock, out_of_stock, discontinued |
| ledger_entry_t | debit, credit |
| order_status_t | draft, confirmed, processing, shipped, delivered, cancelled |
| region_t | north, south, east, west, central |
| shipment_status_t | pending, picked, in_transit, delivered, returned |

---

## 常用查询示例

### 查询所有客户
```sql
SELECT name, email FROM sales.customers;
```

### 查询客户订单
```sql
SELECT c.name, o.id AS order_id, o.status, o.total_amount
FROM sales.customers c
LEFT JOIN sales.orders o ON c.id = o.customer_id;
```

### 查询订单详情（含产品信息）
```sql
SELECT o.id AS order_id, o.status, o.total_amount,
       p.name AS product_name, ol.quantity, ol.unit_price
FROM sales.orders o
JOIN sales.order_lines ol ON o.id = ol.order_id
JOIN catalog.products p ON ol.product_id = p.id;
```

### 查询库存汇总
```sql
SELECT * FROM inventory.stock_summary;
```

### 查询低库存产品
```sql
SELECT * FROM catalog.low_stock_products;
```

### 查询待发货订单
```sql
SELECT * FROM logistics.pending_shipments;
```

### 按地区统计销售
```sql
SELECT r.name AS region, SUM(o.total_amount) AS total_sales
FROM sales.orders o
JOIN sales.customers c ON o.customer_id = c.id
JOIN public.regions r ON c.region_id = r.id
WHERE o.status NOT IN ('cancelled', 'draft')
GROUP BY r.name
ORDER BY total_sales DESC;
```
