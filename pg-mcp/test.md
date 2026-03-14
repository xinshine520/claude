# pg-mcp 自然语言查询测试用例

> 本文档覆盖三个测试数据库（`pg_mcp_small`、`pg_mcp_medium`、`pg_mcp_large`）的自然语言提问，
> 从最简单的单表查询逐步递进到跨 schema 多表关联、聚合分析、窗口函数、CTE 等复杂场景。
> 每条问题均标注目标数据库、预期 SQL 类型及对应的关键表/字段。

---

## 目录

1. [入门级：单表简单查询](#1-入门级单表简单查询)
2. [初级：带条件过滤与排序](#2-初级带条件过滤与排序)
3. [中级：多表 JOIN 查询](#3-中级多表-join-查询)
4. [中级：聚合与分组统计](#4-中级聚合与分组统计)
5. [高级：子查询与 CTE](#5-高级子查询与-cte)
6. [高级：窗口函数与排名](#6-高级窗口函数与排名)
7. [高级：跨 Schema 复杂分析](#7-高级跨-schema-复杂分析)
8. [视图查询](#8-视图查询)
9. [枚举与类型过滤](#9-枚举与类型过滤)
10. [时间与日期分析](#10-时间与日期分析)
11. [存在性与 NULL 检测](#11-存在性与-null-检测)
12. [综合挑战：报表级查询](#12-综合挑战报表级查询)

---

## 1. 入门级：单表简单查询

### 1.1 列出所有用户

- **数据库**：`pg_mcp_small` / `pg_mcp_medium`
- **提问**：查询所有注册用户
- **预期表**：`users`
- **预期 SQL 类型**：`SELECT * FROM users`

---

### 1.2 查看产品列表

- **数据库**：`pg_mcp_small`
- **提问**：显示所有商品的名称和价格
- **预期表**：`products`
- **预期 SQL 类型**：`SELECT name, price FROM products`

---

### 1.3 查询所有分类

- **数据库**：`pg_mcp_small` / `pg_mcp_medium`
- **提问**：有哪些商品分类？
- **预期表**：`categories`
- **预期 SQL 类型**：`SELECT * FROM categories`

---

### 1.4 查询仓库列表

- **数据库**：`pg_mcp_large`
- **提问**：列出所有仓库的名称和容量
- **预期表**：`warehouses`
- **预期 SQL 类型**：`SELECT name, capacity_sqft FROM public.warehouses`

---

### 1.5 查看供应商

- **数据库**：`pg_mcp_large`
- **提问**：查询所有供应商的名称和联系邮箱
- **预期表**：`suppliers`
- **预期 SQL 类型**：`SELECT name, contact_email FROM public.suppliers`

---

## 2. 初级：带条件过滤与排序

### 2.1 查找特定状态的订单

- **数据库**：`pg_mcp_small`
- **提问**：查询所有状态为"已发货（shipped）"的订单
- **预期表**：`orders`
- **预期 SQL 类型**：`SELECT * FROM orders WHERE status = 'shipped'`

---

### 2.2 查找高价商品

- **数据库**：`pg_mcp_small`
- **提问**：列出价格超过 100 元的商品，按价格从高到低排序
- **预期表**：`products`
- **预期 SQL 类型**：`SELECT * FROM products WHERE price > 100 ORDER BY price DESC`

---

### 2.3 查找库存不足的产品

- **数据库**：`pg_mcp_small`
- **提问**：哪些商品的库存少于 100？
- **预期表**：`products`
- **预期 SQL 类型**：`SELECT * FROM products WHERE stock < 100`

---

### 2.4 查询特定员工类型

- **数据库**：`pg_mcp_medium`
- **提问**：查询所有全职员工（full_time）的姓名和邮箱
- **预期表**：`hr.employees`
- **预期 SQL 类型**：`SELECT name, email FROM hr.employees WHERE employee_type = 'full_time'`

---

### 2.5 查询进行中的项目

- **数据库**：`pg_mcp_medium`
- **提问**：显示所有状态为 active 的项目名称和开始日期
- **预期表**：`projects.projects`
- **预期 SQL 类型**：`SELECT name, start_date FROM projects.projects WHERE status = 'active'`

---

### 2.6 按区域过滤客户

- **数据库**：`pg_mcp_large`
- **提问**：查询 region_id 为 1 的所有客户
- **预期表**：`sales.customers`
- **预期 SQL 类型**：`SELECT * FROM sales.customers WHERE region_id = 1`

---

### 2.7 查询低库存产品

- **数据库**：`pg_mcp_large`
- **提问**：找出库存状态为 low_stock 的所有产品
- **预期表**：`catalog.products`
- **预期 SQL 类型**：`SELECT * FROM catalog.products WHERE status = 'low_stock'`

---

### 2.8 查询已取消的订单

- **数据库**：`pg_mcp_small`
- **提问**：查询所有被取消或已完成配送的订单，按创建时间倒序排列，最多显示 10 条
- **预期表**：`orders`
- **预期 SQL 类型**：`SELECT * FROM orders WHERE status IN ('cancelled', 'delivered') ORDER BY created_at DESC LIMIT 10`

---

## 3. 中级：多表 JOIN 查询

### 3.1 用户与订单

- **数据库**：`pg_mcp_small`
- **提问**：查询每个用户的姓名及其下单总次数
- **预期表**：`users`, `orders`
- **预期 SQL 类型**：`JOIN + GROUP BY`

---

### 3.2 订单明细展开

- **数据库**：`pg_mcp_small`
- **提问**：列出所有订单中包含的商品名称、数量和单价
- **预期表**：`orders`, `order_items`, `products`
- **预期 SQL 类型**：多表 JOIN

---

### 3.3 商品归属分类

- **数据库**：`pg_mcp_small`
- **提问**：显示所有商品的名称以及对应的分类名称
- **预期表**：`products`, `categories`
- **预期 SQL 类型**：`JOIN`

---

### 3.4 员工所在部门

- **数据库**：`pg_mcp_medium`
- **提问**：查询每位员工的姓名、所在部门名称以及入职日期
- **预期表**：`hr.employees`, `hr.departments`
- **预期 SQL 类型**：`JOIN`

---

### 3.5 项目成员列表

- **数据库**：`pg_mcp_medium`
- **提问**：列出"Website Redesign"项目的所有成员姓名和角色
- **预期表**：`projects.projects`, `projects.project_members`, `hr.employees`
- **预期 SQL 类型**：多表 JOIN + WHERE

---

### 3.6 订单与客户关联

- **数据库**：`pg_mcp_large`
- **提问**：查询每笔订单的客户名称、订单状态和总金额
- **预期表**：`sales.orders`, `sales.customers`
- **预期 SQL 类型**：`JOIN`

---

### 3.7 订单行与产品关联

- **数据库**：`pg_mcp_large`
- **提问**：列出订单 #1 中所有商品的 SKU、名称和订购数量
- **预期表**：`sales.order_lines`, `catalog.products`
- **预期 SQL 类型**：`JOIN + WHERE`

---

### 3.8 库存与仓库关联

- **数据库**：`pg_mcp_large`
- **提问**：查询每个仓库中每种产品的库存数量，显示仓库名称、产品名称和库存
- **预期表**：`inventory.stock_levels`, `public.warehouses`, `catalog.products`
- **预期 SQL 类型**：多表 JOIN

---

### 3.9 发货状态与订单

- **数据库**：`pg_mcp_large`
- **提问**：查询所有运输中（in_transit）的货物对应的客户名称和订单金额
- **预期表**：`logistics.shipments`, `sales.orders`, `sales.customers`
- **预期 SQL 类型**：多表 JOIN + WHERE

---

### 3.10 考勤记录与员工

- **数据库**：`pg_mcp_medium`
- **提问**：查询昨天所有员工的出勤记录，显示员工姓名和工作小时数
- **预期表**：`hr.employees`, `hr.attendance`
- **预期 SQL 类型**：`JOIN + WHERE date = CURRENT_DATE - 1`

---

## 4. 中级：聚合与分组统计

### 4.1 各分类商品数量

- **数据库**：`pg_mcp_small`
- **提问**：每个商品分类下有多少种商品？
- **预期表**：`products`, `categories`
- **预期 SQL 类型**：`GROUP BY + COUNT`

---

### 4.2 每个用户的消费总额

- **数据库**：`pg_mcp_small`
- **提问**：计算每位用户的历史订单总金额，按金额从高到低排列
- **预期表**：`users`, `orders`
- **预期 SQL 类型**：`JOIN + GROUP BY + SUM + ORDER BY`

---

### 4.3 各状态订单数量统计

- **数据库**：`pg_mcp_small`
- **提问**：统计各订单状态下的订单数量
- **预期表**：`orders`
- **预期 SQL 类型**：`GROUP BY status + COUNT`

---

### 4.4 各部门员工人数

- **数据库**：`pg_mcp_medium`
- **提问**：每个部门有多少名员工？
- **预期表**：`hr.departments`, `hr.employees`
- **预期 SQL 类型**：`GROUP BY + COUNT`

---

### 4.5 各部门平均薪资

- **数据库**：`pg_mcp_medium`
- **提问**：计算各部门员工的平均薪资，并按平均薪资降序排列
- **预期表**：`hr.departments`, `hr.employees`
- **预期 SQL 类型**：`GROUP BY + AVG + ORDER BY`

---

### 4.6 项目任务完成率

- **数据库**：`pg_mcp_medium`
- **提问**：统计每个项目的任务总数和已完成任务数
- **预期表**：`projects.projects`, `projects.tasks`
- **预期 SQL 类型**：`GROUP BY + COUNT + FILTER`

---

### 4.7 每种优先级的任务数量

- **数据库**：`pg_mcp_medium`
- **提问**：按优先级统计任务数量
- **预期表**：`projects.tasks`
- **预期 SQL 类型**：`GROUP BY priority + COUNT`

---

### 4.8 各区域客户数量

- **数据库**：`pg_mcp_large`
- **提问**：每个销售区域有多少客户？
- **预期表**：`sales.customers`, `public.regions`
- **预期 SQL 类型**：`JOIN + GROUP BY + COUNT`

---

### 4.9 各产品线总库存

- **数据库**：`pg_mcp_large`
- **提问**：统计每条产品线的产品种数和在所有仓库中的总库存数量
- **预期表**：`catalog.product_lines`, `catalog.products`, `inventory.stock_levels`
- **预期 SQL 类型**：多表 JOIN + GROUP BY + COUNT + SUM

---

### 4.10 财务账户余额

- **数据库**：`pg_mcp_large`
- **提问**：计算每个财务账户的当前余额（借方减贷方）
- **预期表**：`finance.accounts`, `finance.transactions`
- **预期 SQL 类型**：`GROUP BY + SUM + CASE WHEN`

---

### 4.11 每种支付方式的订单量

- **数据库**：`pg_mcp_medium`
- **提问**：统计各支付方式（payment_method）的订单数量和总金额
- **预期表**：`orders`
- **预期 SQL 类型**：`GROUP BY payment_method + COUNT + SUM`

---

### 4.12 商品销售额排行

- **数据库**：`pg_mcp_small`
- **提问**：统计每种商品的累计销售数量和销售额，按销售额从高到低排列
- **预期表**：`products`, `order_items`
- **预期 SQL 类型**：`JOIN + GROUP BY + SUM + ORDER BY`

---

## 5. 高级：子查询与 CTE

### 5.1 查找消费最高的用户

- **数据库**：`pg_mcp_small`
- **提问**：找出历史消费总金额最高的那位用户的姓名和邮箱
- **预期 SQL 类型**：子查询或 CTE + ORDER BY LIMIT 1

---

### 5.2 查询未下过订单的用户

- **数据库**：`pg_mcp_small`
- **提问**：哪些用户从未下过订单？
- **预期 SQL 类型**：`LEFT JOIN ... WHERE orders.id IS NULL` 或 `NOT EXISTS`

---

### 5.3 查询销量最好的前 3 种商品

- **数据库**：`pg_mcp_small`
- **提问**：销量最好的前 3 种商品是什么？
- **预期 SQL 类型**：子查询或 CTE + ORDER BY + LIMIT 3

---

### 5.4 超过平均薪资的员工

- **数据库**：`pg_mcp_medium`
- **提问**：哪些员工的薪资高于所在部门的平均薪资？
- **预期 SQL 类型**：子查询（相关子查询）或 CTE

---

### 5.5 没有完成任何任务的项目

- **数据库**：`pg_mcp_medium`
- **提问**：哪些项目目前没有任何已完成的任务？
- **预期 SQL 类型**：`NOT EXISTS` 或 LEFT JOIN + HAVING

---

### 5.6 连续购买的用户

- **数据库**：`pg_mcp_small`
- **提问**：找出下过 2 笔及以上订单的用户，列出其姓名和订单数量
- **预期 SQL 类型**：CTE 或子查询 + HAVING COUNT >= 2

---

### 5.7 库存总量低于 20 的产品

- **数据库**：`pg_mcp_large`
- **提问**：找出在所有仓库合计库存不足 20 件的产品，显示产品名称和总库存
- **预期 SQL 类型**：GROUP BY + HAVING + SUM

---

### 5.8 各部门薪资最高的员工

- **数据库**：`pg_mcp_medium`
- **提问**：每个部门中薪资最高的员工是谁？
- **预期 SQL 类型**：CTE + RANK() 或子查询 + MAX

---

### 5.9 参与多个项目的员工

- **数据库**：`pg_mcp_medium`
- **提问**：哪些员工同时参与了 2 个或以上的项目？
- **预期 SQL 类型**：GROUP BY + HAVING COUNT >= 2

---

### 5.10 审计日志中操作最频繁的表

- **数据库**：`pg_mcp_large`
- **提问**：在审计日志中，哪些表被操作的次数最多？列出前 5 名
- **预期表**：`public.audit_log`
- **预期 SQL 类型**：`GROUP BY table_name + ORDER BY COUNT DESC LIMIT 5`

---

## 6. 高级：窗口函数与排名

### 6.1 用户订单金额排名

- **数据库**：`pg_mcp_small`
- **提问**：对每位用户的每笔订单按金额从大到小排名，显示用户名、订单 ID、金额和名次
- **预期 SQL 类型**：`RANK() OVER (PARTITION BY user_id ORDER BY total_amount DESC)`

---

### 6.2 商品价格百分位

- **数据库**：`pg_mcp_small`
- **提问**：计算每种商品的价格在所有商品中的百分位排名
- **预期 SQL 类型**：`PERCENT_RANK() OVER (ORDER BY price)`

---

### 6.3 员工薪资累计排名

- **数据库**：`pg_mcp_medium`
- **提问**：按部门对员工薪资做排名，显示员工姓名、部门、薪资和部门内排名
- **预期 SQL 类型**：`RANK() OVER (PARTITION BY department_id ORDER BY salary DESC)`

---

### 6.4 每月新增用户趋势

- **数据库**：`pg_mcp_medium`
- **提问**：按月统计新注册用户数量以及累计总用户数
- **预期 SQL 类型**：`date_trunc + GROUP BY + SUM() OVER (ORDER BY month)`

---

### 6.5 每个客户的订单金额环比

- **数据库**：`pg_mcp_large`
- **提问**：查询每位客户历次订单的金额，以及与上一笔订单的金额差额
- **预期 SQL 类型**：`LAG() OVER (PARTITION BY customer_id ORDER BY created_at)`

---

### 6.6 每个账户的交易流水累计金额

- **数据库**：`pg_mcp_large`
- **提问**：按时间顺序展示每个财务账户的每笔交易记录及截至该笔交易的累计金额
- **预期 SQL 类型**：`SUM() OVER (PARTITION BY account_id ORDER BY created_at)`

---

## 7. 高级：跨 Schema 复杂分析

### 7.1 员工参与项目与其部门预算

- **数据库**：`pg_mcp_medium`
- **提问**：查询每位员工参与的项目数量，以及他们所在部门的总预算
- **预期表**：`hr.employees`, `hr.departments`, `projects.project_members`, `projects.projects`
- **预期 SQL 类型**：多表 JOIN + GROUP BY

---

### 7.2 客户订单与对应货运状态

- **数据库**：`pg_mcp_large`
- **提问**：查询客户"Alpha Inc"的所有订单及每笔订单最新的货运状态
- **预期表**：`sales.customers`, `sales.orders`, `logistics.shipments`
- **预期 SQL 类型**：多表 JOIN + WHERE

---

### 7.3 产品库存与产品线分布

- **数据库**：`pg_mcp_large`
- **提问**：统计每条产品线在各仓库的总库存量，按产品线和仓库分组
- **预期表**：`catalog.product_lines`, `catalog.products`, `inventory.stock_levels`, `public.warehouses`
- **预期 SQL 类型**：多表 JOIN + GROUP BY

---

### 7.4 各区域的订单收入汇总

- **数据库**：`pg_mcp_large`
- **提问**：按销售区域汇总已成交订单的总收入（状态为 delivered）
- **预期表**：`public.regions`, `sales.customers`, `sales.orders`
- **预期 SQL 类型**：多表 JOIN + WHERE + GROUP BY + SUM

---

### 7.5 部门预算使用率

- **数据库**：`pg_mcp_medium`
- **提问**：计算每个部门的预算总额和实际薪资支出总额，以及预算使用比例
- **预期表**：`hr.departments`, `hr.employees`, `hr.salaries`
- **预期 SQL 类型**：多表 JOIN + GROUP BY + 百分比计算

---

### 7.6 项目里程碑完成情况与负责员工

- **数据库**：`pg_mcp_medium`
- **提问**：列出所有项目的未完成里程碑，以及该项目的 lead 角色成员姓名
- **预期表**：`projects.projects`, `projects.milestones`, `projects.project_members`, `hr.employees`
- **预期 SQL 类型**：多表 JOIN + WHERE + 子查询

---

### 7.7 财务收入账户与销售订单对账

- **数据库**：`pg_mcp_large`
- **提问**：查询财务 Revenue（4000）账户的所有贷方交易，关联对应的描述，按金额降序排列
- **预期表**：`finance.accounts`, `finance.transactions`
- **预期 SQL 类型**：JOIN + WHERE account_type = 'revenue' AND entry_type = 'credit'

---

## 8. 视图查询

### 8.1 查询活跃订单

- **数据库**：`pg_mcp_small`
- **提问**：查询所有活跃订单（未完成且未取消），显示客户名和订单金额
- **预期**：使用视图 `active_orders`

---

### 8.2 商品销售汇总

- **数据库**：`pg_mcp_small`
- **提问**：从商品销售汇总视图中找出总销售额超过 1000 元的商品
- **预期**：使用视图 `product_sales_summary` + WHERE

---

### 8.3 订单汇总视图

- **数据库**：`pg_mcp_medium`
- **提问**：从订单汇总视图中查询包含 3 件以上商品的订单
- **预期**：使用视图 `order_summary` + WHERE item_count >= 3

---

### 8.4 员工总览

- **数据库**：`pg_mcp_medium`
- **提问**：通过员工汇总视图，查询工程部（Engineering）的所有员工
- **预期**：使用视图 `hr.employee_summary` + WHERE

---

### 8.5 项目进度

- **数据库**：`pg_mcp_medium`
- **提问**：查看每个项目的任务完成情况，显示项目名称、总任务数和已完成数
- **预期**：使用视图 `projects.project_progress`

---

### 8.6 库存汇总视图

- **数据库**：`pg_mcp_large`
- **提问**：从库存汇总视图中找出总库存为 0 的产品
- **预期**：使用视图 `inventory.stock_summary` + WHERE total_stock = 0

---

### 8.7 待处理发货

- **数据库**：`pg_mcp_large`
- **提问**：查询所有尚未完成发货（pending 或 in_transit）的货物清单
- **预期**：使用视图 `logistics.pending_shipments`

---

### 8.8 余额表

- **数据库**：`pg_mcp_large`
- **提问**：查询资产类型（asset）账户的余额
- **预期**：使用视图 `finance.balance_sheet` + WHERE account_type = 'asset'

---

## 9. 枚举与类型过滤

### 9.1 订单状态枚举筛选

- **数据库**：`pg_mcp_small`
- **提问**：查询所有处于"已支付"或"运输中"状态的订单
- **预期**：`WHERE status IN ('paid', 'shipped')`

---

### 9.2 合同类型过滤

- **数据库**：`pg_mcp_large`
- **提问**：查询合同类型为 supplier 的供应商列表
- **预期**：`WHERE contract_type = 'supplier'`

---

### 9.3 多枚举条件组合

- **数据库**：`pg_mcp_large`
- **提问**：查询状态为 confirmed 或 processing 的订单中，货币为 USD 的订单
- **预期**：`WHERE status IN ('confirmed', 'processing') AND currency = 'USD'`

---

### 9.4 各支付状态的交易数量

- **数据库**：`pg_mcp_large`
- **提问**：统计不同账户类型的财务账户数量
- **预期**：`GROUP BY account_type`

---

### 9.5 员工类型分布

- **数据库**：`pg_mcp_medium`
- **提问**：统计各类型员工（全职/兼职/合同工/实习生）的人数
- **预期**：`GROUP BY employee_type + COUNT`

---

## 10. 时间与日期分析

### 10.1 最近 7 天的订单

- **数据库**：`pg_mcp_small`
- **提问**：查询最近 7 天内创建的所有订单
- **预期**：`WHERE created_at >= NOW() - INTERVAL '7 days'`

---

### 10.2 按月统计订单量

- **数据库**：`pg_mcp_medium`
- **提问**：按月统计订单数量和总金额
- **预期**：`date_trunc('month', created_at) GROUP BY`

---

### 10.3 员工工龄排行

- **数据库**：`pg_mcp_medium`
- **提问**：查询所有员工的姓名和工龄（年），按工龄从长到短排列
- **预期**：`EXTRACT(YEAR FROM AGE(CURRENT_DATE, hire_date))`

---

### 10.4 最近 3 天的每日指标

- **数据库**：`pg_mcp_medium`
- **提问**：查询最近 3 天的每日订单数量和收入
- **预期表**：`analytics.daily_metrics`
- **预期**：`WHERE metric_date >= CURRENT_DATE - 3`

---

### 10.5 本年度有效薪资记录

- **数据库**：`pg_mcp_medium`
- **提问**：查询当前仍有效（effective_to 为空）的薪资记录及对应员工姓名
- **预期**：`WHERE effective_to IS NULL JOIN employees`

---

### 10.6 发货时间统计

- **数据库**：`pg_mcp_large`
- **提问**：计算已完成发货的货物从发货到送达的平均天数
- **预期**：`AVG(delivered_at - shipped_at) WHERE status = 'delivered'`

---

## 11. 存在性与 NULL 检测

### 11.1 没有商品描述的分类

- **数据库**：`pg_mcp_small`
- **提问**：哪些商品分类没有填写描述（description 为空）？
- **预期**：`WHERE description IS NULL`

---

### 11.2 没有分配部门的员工

- **数据库**：`pg_mcp_medium`
- **提问**：查询尚未分配到任何部门的员工
- **预期**：`WHERE department_id IS NULL`

---

### 11.3 没有设置预算的项目

- **数据库**：`pg_mcp_medium`
- **提问**：找出未设置预算的项目
- **预期**：`WHERE budget IS NULL`

---

### 11.4 没有里程碑的项目

- **数据库**：`pg_mcp_medium`
- **提问**：哪些项目还没有设置任何里程碑？
- **预期**：`NOT EXISTS` 或 `LEFT JOIN ... WHERE milestones.id IS NULL`

---

### 11.5 无库存记录的产品

- **数据库**：`pg_mcp_large`
- **提问**：找出在库存表中没有任何库存记录的产品
- **预期**：`LEFT JOIN stock_levels WHERE stock_levels.id IS NULL`

---

### 11.6 没有设置经理的部门

- **数据库**：`pg_mcp_medium`
- **提问**：哪些部门还没有指定经理（manager_id 为空）？
- **预期**：`WHERE manager_id IS NULL`

---

## 12. 综合挑战：报表级查询

### 12.1 销售业绩报表

- **数据库**：`pg_mcp_small`
- **提问**：生成一份销售业绩报表，显示每位用户的姓名、订单总数、消费总金额、平均单笔金额，以及最近一笔订单的状态，按消费总额降序排列
- **预期 SQL 类型**：CTE + JOIN + GROUP BY + MAX/AVG + ORDER BY

---

### 12.2 商品库存健康报告

- **数据库**：`pg_mcp_small`
- **提问**：生成商品库存健康报告，显示每种商品的名称、分类、当前库存、总销售量，以及如果按当前月均销量计算还能卖几个月（库存/月均销量）
- **预期 SQL 类型**：CTE + 多表 JOIN + 除法计算

---

### 12.3 人力资源综合分析

- **数据库**：`pg_mcp_medium`
- **提问**：输出人力资源报表：每个部门的员工人数、平均薪资、最高薪资、最低薪资、部门预算以及薪资总支出占预算的比例
- **预期 SQL 类型**：CTE + JOIN + GROUP BY + 多个聚合函数 + 比例计算

---

### 12.4 项目健康度报告

- **数据库**：`pg_mcp_medium`
- **提问**：生成项目健康度报告，显示每个项目的名称、状态、总任务数、已完成任务数、完成率（百分比）、成员数量和预算，只显示 active 状态的项目
- **预期 SQL 类型**：CTE + 多表 JOIN + GROUP BY + 百分比计算 + WHERE

---

### 12.5 供应链全链路分析

- **数据库**：`pg_mcp_large`
- **提问**：分析每条产品线的销售表现：显示产品线名称、产品数量、总库存量、已下单总数量、已完成配送的订单金额总计
- **预期 SQL 类型**：CTE + 多 schema JOIN + GROUP BY + SUM + FILTER

---

### 12.6 区域销售竞争力排名

- **数据库**：`pg_mcp_large`
- **提问**：对各销售区域进行排名，显示区域名称、客户数、订单数、已交付订单总收入，以及该区域收入占全国总收入的百分比，按收入降序排列
- **预期 SQL 类型**：CTE + 多表 JOIN + GROUP BY + SUM + 窗口函数 (占比) + ORDER BY

---

### 12.7 财务健康状况综合报表

- **数据库**：`pg_mcp_large`
- **提问**：生成财务健康报表，列出所有账户的代码、名称、账户类型、借方总额、贷方总额和净余额（借方-贷方），并在最后一行汇总所有账户的借贷合计
- **预期 SQL 类型**：GROUP BY + SUM + CASE WHEN + UNION ALL（或 ROLLUP）

---

### 12.8 客户 360° 视图

- **数据库**：`pg_mcp_large`
- **提问**：对客户"Alpha Inc"生成 360° 分析：显示其区域、历史订单数、总消费金额、平均单笔金额、最大单笔订单金额、首次下单时间、最近下单时间、当前待处理货运数量
- **预期 SQL 类型**：CTE + 多表 JOIN + GROUP BY + 多聚合函数

---

### 12.9 库存预警与补货建议

- **数据库**：`pg_mcp_large`
- **提问**：生成库存预警报告，找出总库存低于 20 件或状态为 low_stock 的产品，显示产品 SKU、名称、当前总库存、状态，以及各仓库的库存分布（仓库名和数量）
- **预期 SQL 类型**：CTE + HAVING + FILTER + 多表 JOIN + 可能使用 STRING_AGG 汇总仓库信息

---

### 12.10 审计与操作频率分析

- **数据库**：`pg_mcp_large`
- **提问**：分析审计日志，统计过去所有记录中每张表被 select/insert/update/delete 的操作次数，输出表名、各操作次数，按总操作次数降序排列，只显示总操作次数超过 5 次的表
- **预期 SQL 类型**：GROUP BY + COUNT + FILTER/CASE WHEN + HAVING + ORDER BY

---

## 附录：快速参考

### 数据库对照表

| 数据库             | 规模    | 核心 Schema / 主要表                                                                 |
| ------------------ | ------- | ------------------------------------------------------------------------------------ |
| `pg_mcp_small`     | 6 表    | `users`, `products`, `categories`, `orders`, `order_items`                          |
| `pg_mcp_medium`    | ~35 表  | `public`(电商), `hr`(人力资源), `projects`(项目管理), `analytics`(数据分析)         |
| `pg_mcp_large`     | ~220 表 | `public`(基础), `sales`(销售), `inventory`(库存), `finance`(财务), `logistics`(物流), `catalog`(商品) |

### 问题复杂度分布

| 难度   | 问题数 | 适用场景                         |
| ------ | ------ | -------------------------------- |
| 入门   | 5      | 基本连通性和单表查询验证         |
| 初级   | 8      | 条件过滤、排序、基本 WHERE       |
| 中级   | 22     | JOIN、聚合、GROUP BY             |
| 高级   | 24     | 子查询、CTE、窗口函数、跨 Schema |
| 报表级 | 10     | 复杂多表、业务分析、综合统计     |
| **合计** | **69** |                                |
