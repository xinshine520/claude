# pg_mcp_medium 数据库结构参考

## 概述
pg_mcp_medium 是一个中等规模的 PostgreSQL 数据库，包含电商、人力资源和项目管理数据。

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

#### 视图
- `active_orders`: 活跃订单视图
- `order_summary`: 订单汇总视图
- `product_sales`: 产品销售视图

### hr (人力资源)
#### 表
| 表名 | 说明 |
|------|------|
| departments | 部门表 |
| employees | 员工表 |
| salaries | 薪资表 |
| attendance | 考勤表 |

#### 视图
- `department_stats`: 部门统计视图
- `employee_summary`: 员工汇总视图

### projects (项目管理)
#### 表
| 表名 | 说明 |
|------|------|
| projects | 项目表 |
| tasks | 任务表 |
| milestones | 里程碑表 |
| project_members | 项目成员表 |

#### 视图
- `project_progress`: 项目进度视图

### analytics (分析)
#### 视图
- `daily_metrics`: 每日指标视图
- `monthly_revenue`: 月度收入视图
- `report_cache`: 报告缓存视图

---

## 常用查询示例

### 查询所有产品
```sql
SELECT * FROM products;
```

### 查询所有员工
```sql
SELECT * FROM hr.employees;
```

### 查询所有项目
```sql
SELECT * FROM projects.projects;
```

### 查询订单及用户信息
```sql
SELECT o.id, o.total_amount, o.status, u.name AS customer_name
FROM orders o
JOIN users u ON o.user_id = u.id;
```
