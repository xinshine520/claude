# pg_mcp_small 数据库结构参考

## 概述
pg_mcp_small 是一个小型 PostgreSQL 数据库。

## 数据库连接
- 主机: 127.0.0.1
- 端口: 5432
- 用户: postgres
- 密码: 123456

## Schema 结构

### public
#### 表
| 表名 | 说明 |
|------|------|
| categories | 分类表 |
| products | 产品表 |
| users | 用户表 |
| orders | 订单表 |
| order_items | 订单明细表 |

#### categories 表
| 列名 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| name | varchar | 分类名称 |

#### products 表
| 列名 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| name | varchar | 产品名称 |
| price | numeric | 价格 |
| category_id | integer | 外键，关联 categories |

#### users 表
| 列名 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| name | varchar | 用户名称 |
| email | varchar | 邮箱 |

#### orders 表
| 列名 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| user_id | integer | 外键，关联 users |
| total_amount | numeric | 总金额 |
| status | varchar | 订单状态 |
| created_at | timestamptz | 创建时间 |

#### order_items 表
| 列名 | 类型 | 说明 |
|------|------|------|
| id | integer | 主键 |
| order_id | integer | 外键，关联 orders |
| product_id | integer | 外键，关联 products |
| quantity | integer | 数量 |
| price | numeric | 价格 |

#### 视图
- `active_orders`: 活跃订单视图
- `product_sales_summary`: 产品销售汇总视图

---

## 常用查询示例

### 查询所有产品
```sql
SELECT * FROM products;
```

### 查询所有用户
```sql
SELECT * FROM users;
```

### 查询订单及用户信息
```sql
SELECT o.id, o.total_amount, o.status, u.name AS customer_name
FROM orders o
JOIN users u ON o.user_id = u.id;
```
