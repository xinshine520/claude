# Java MQTT 框架对比分析：smart-mqtt vs mica-mqtt

> 分析日期：2026-03-28
>
> 仓库地址：
> - smart-mqtt：https://gitee.com/smartboot/smart-mqtt
> - mica-mqtt：https://gitee.com/dromara/mica-mqtt

---

## 一、项目概览

| 维度 | smart-mqtt | mica-mqtt |
|------|-----------|-----------|
| **定位** | 企业级云原生分布式 MQTT Broker | 轻量级 MQTT 物联网组件（Client + Server） |
| **组织** | smartboot（个人/小团队） | Dromara 社区 |
| **Stars** | ~795 | ~2600 |
| **Forks** | ~157 | ~792 |
| **提交数** | ~1474 | ~1902 |
| **协议** | **AGPL-3.0**（商用需授权） | **Apache-2.0**（商用友好） |
| **MQTT 版本** | v3.1.1 / v5.0 | v3.1 / v3.1.1 / v5.0 |
| **底层网络** | smart-socket（自研） | t-io / mica-net（自研，从 t-io 演化） |
| **JDK 要求** | JDK 8+ | JDK 8+ |
| **最新版本** | v1.5.3 | v2.6.0 |
| **发行包大小** | < 800KB | 核心依赖 ~500KB |

---

## 二、架构设计对比

### 2.1 smart-mqtt 架构

```
smart-mqtt
├── smart-mqtt-common        # 公共模块（协议编解码）
├── smart-mqtt-broker        # Broker 服务端（主入口）
├── smart-mqtt-client        # MQTT 客户端 SDK
├── smart-mqtt-plugin-spec   # 插件规范接口
├── smart-mqtt-maven-plugin  # 插件开发 Maven 工具
├── smart-mqtt-bench         # 压测工具
├── smart-mqtt-test          # 测试模块
├── plugins/                 # 官方插件集
│   ├── enterprise-plugin    # Web 控制台 + RESTful API
│   ├── cluster-plugin       # 集群支持
│   ├── websocket-plugin     # WebSocket 协议
│   ├── mqtts-plugin         # TLS/SSL 加密
│   ├── redis-bridge-plugin  # Redis 数据桥接
│   └── simple-auth-plugin   # 用户名密码认证 + ACL
└── pages/                   # 文档站
```

**核心特征**：纯插件化架构，所有扩展功能（WebSocket、SSL、认证、集群、管理控制台）均以插件形式加载，Broker 核心极其精简。

### 2.2 mica-mqtt 架构

```
mica-mqtt
├── mica-mqtt-codec          # 协议编解码
├── mica-mqtt-common         # 公共工具
├── mica-mqtt-client         # MQTT 客户端
├── mica-mqtt-server         # MQTT 服务端
├── starter/                 # 各框架集成 Starter
│   ├── mica-mqtt-client-spring-boot-starter
│   ├── mica-mqtt-server-spring-boot-starter
│   ├── mica-mqtt-client-solon-plugin
│   ├── mica-mqtt-server-solon-plugin
│   ├── mica-mqtt-client-jfinal-plugin
│   └── mica-mqtt-server-jfinal-plugin
├── example/                 # 示例代码
└── docs/                    # 文档
```

**核心特征**：组件化设计，提供 Client 和 Server 双端能力，通过 Spring Boot Starter / Solon Plugin / JFinal Plugin 等形式嵌入到现有项目中，强调作为"组件"而非"独立产品"使用。

---

## 三、核心能力对比

### 3.1 协议支持

| 能力 | smart-mqtt | mica-mqtt |
|------|-----------|-----------|
| MQTT 3.1 | ❌ | ✅ |
| MQTT 3.1.1 | ✅ | ✅ |
| MQTT 5.0 | ✅ | ✅ |
| WebSocket | ✅（插件） | ✅（内置） |
| SSL/TLS | ✅（插件） | ✅（配置） |
| 共享订阅 | ✅ | ✅ |
| 遗嘱消息 | ✅ | ✅ |
| 保留消息 | ✅ | ✅ |
| QoS 0/1/2 | ✅ | ✅ |

### 3.2 功能特性

| 能力 | smart-mqtt | mica-mqtt |
|------|-----------|-----------|
| **MQTT Client** | ✅ | ✅ |
| **MQTT Broker/Server** | ✅ | ✅ |
| **Web 管理控制台** | ✅（enterprise-plugin） | ✅（mica-mqtt-dashboard，独立项目） |
| **HTTP REST API** | ✅（enterprise-plugin） | ✅（内置 http api） |
| **集群支持** | ✅（cluster-plugin，内置） | ✅（基于 Redis Stream） |
| **数据桥接** | ✅（redis-bridge-plugin） | 需自行实现 |
| **Prometheus 监控** | 未明确 | ✅（原生支持 + Grafana） |
| **Docker 部署** | ✅（官方镜像） | 需自行打包 |
| **GraalVM Native** | 未明确 | ✅ |
| **Android 支持** | ❌ | ✅（Client + Server，API 26+） |
| **Spring Boot 集成** | ❌（独立部署） | ✅（一等公民级 Starter） |
| **Solon 集成** | ❌ | ✅ |
| **JFinal 集成** | ❌ | ✅ |
| **MCP（大模型接口）** | ✅（2026 AI重构） | ✅（2.5.x 起） |
| **代理协议（Proxy Protocol）** | 未明确 | ✅（nginx 转发源 IP） |
| **消息拦截器** | 通过插件 | ✅（内置 Interceptor） |
| **注解式消息监听** | ❌ | ✅（@MqttServerFunction，2.5.3+） |

### 3.3 性能表现

| 指标 | smart-mqtt | mica-mqtt |
|------|-----------|-----------|
| **并发连接** | 官方声称 10万+（单机），百万级（集群） | 官方声称百万级 Client |
| **消息吞吐** | QoS0 订阅 1000W/s，发布 230W/s | 低延迟高性能（无公开 benchmark） |
| **消息延迟** | < 1ms | 低延迟（无具体数据） |
| **压测工具** | ✅（内置 bench-plugin） | ❌（需第三方工具） |

> smart-mqtt 提供了详细的 benchmark 数据（8核16G，2000并发，128字节 payload），并支持与 EMQX、Mosquitto 横向对比。mica-mqtt 未提供公开的标准化压测数据。

---

## 四、开发体验对比

### 4.1 smart-mqtt 开发方式

**独立 Broker 部署 + 插件开发**：

```bash
# Docker 一键部署
docker run -p 1883:1883 -p 18083:18083 smartboot/smart-mqtt:latest
```

插件开发需要遵循 `smart-mqtt-plugin-spec` 规范，使用 `smart-mqtt-maven-plugin` 进行本地调试。v1.5.1 引入 Schema 配置规范，插件可声明配置项，Dashboard 自动渲染表单。

**Client 使用**：

```java
// smart-mqtt 客户端 SDK
MqttClient client = new MqttClient("127.0.0.1", 1883, "clientId");
client.connect();
client.subscribe("/test/topic", MqttQoS.AT_MOST_ONCE);
client.publish("/test/topic", "Hello".getBytes());
```

### 4.2 mica-mqtt 开发方式

**嵌入式组件 + Spring Boot Starter**：

```xml
<!-- 一行依赖即可集成 -->
<dependency>
  <groupId>org.dromara.mica-mqtt</groupId>
  <artifactId>mica-mqtt-server-spring-boot-starter</artifactId>
  <version>2.6.0</version>
</dependency>
```

```yaml
# application.yml 配置驱动
mqtt:
  server:
    enabled: true
    mqtt-listener:
      enable: true
      port: 1883
    ws-listener:
      enable: true
      port: 8083
```

```java
// 注解式消息监听（Spring Bean 即可）
@Service
public class MqttServerMessageListener {

    @MqttServerFunction("/device/${deviceId}/data")
    public void onDeviceData(String topic, byte[] message) {
        // 处理设备上报数据
    }
}

// 通过 Template 发送消息
@Autowired
private MqttServerTemplate server;

server.publishAll("/test/123", data);
```

**纯 Java 方式（无框架依赖）**：

```java
MqttServer mqttServer = MqttServer.create()
    .enableMqtt(1883)
    .messageListener((context, clientId, topic, qos, message) -> {
        // 处理消息
    })
    .connectStatusListener(new MqttConnectStatusListener())
    .enableMqttWs()
    .enableMqttHttpApi(builder -> builder.basicAuth("admin", "admin").build())
    .start();
```

### 4.3 开发体验总结

| 维度 | smart-mqtt | mica-mqtt |
|------|-----------|-----------|
| **上手难度** | 中等（需理解插件体系） | 低（Spring Boot 开发者 5 分钟上手） |
| **集成方式** | 独立部署，通过 MQTT 协议交互 | 嵌入应用进程，代码级集成 |
| **扩展方式** | 插件开发（有规范约束） | 实现接口 + 注册 Spring Bean |
| **文档质量** | 官方网站 + 部分文档 | 完善的文档站 + 视频教程 |
| **示例代码** | 较少 | 丰富（example 模块，阿里云/华为云示例） |
| **社区活跃度** | 一般（个人维护为主） | 较高（Dromara 社区，2600+ Star） |
| **API 设计** | 面向插件 SPI | 面向开发者 Fluent API + 注解 |

---

## 五、优缺点分析

### 5.1 smart-mqtt

**优点：**

1. **极致性能**：基于自研 smart-socket 异步非阻塞框架，有详细 benchmark 数据支撑，QoS0 订阅吞吐可达 1000W/s
2. **插件化架构**：真正的热插拔设计，功能按需加载，核心极其精简（< 800KB）
3. **独立 Broker 定位**：开箱即用的 MQTT Broker 服务器，Docker 一键部署
4. **内置 Web 管理控制台**：enterprise-plugin 提供可视化管理界面
5. **内置集群方案**：cluster-plugin 原生支持多节点部署
6. **内置压测工具**：bench-plugin 方便性能验证和对比
7. **企业客户验证**：比亚迪、顺丰科技等企业实际使用

**缺点：**

1. **AGPL-3.0 许可证**：商业使用必须购买授权，对二次开发有强传染性约束。即使修改后的代码也必须开源，对闭源商业产品极为不利
2. **无框架集成**：不提供 Spring Boot Starter 等集成方式，只能作为独立服务部署
3. **Client 能力偏弱**：重心在 Broker，Client SDK 功能相对简单
4. **社区规模较小**：主要由个人维护，Star 数和贡献者较少
5. **不支持 Android**：仅适用于服务端场景
6. **二次开发门槛**：需学习插件开发规范，开发约束较多
7. **不支持 MQTT 3.1**：仅支持 3.1.1 和 5.0

### 5.2 mica-mqtt

**优点：**

1. **Apache-2.0 许可证**：商用完全免费，无传染性约束，可自由修改和闭源
2. **一等公民级框架集成**：Spring Boot / Solon / JFinal Starter，与现有项目无缝融合
3. **Client + Server 双端能力**：同时提供高质量的客户端和服务端
4. **Android 原生支持**：Client 和 Server 均可运行在 Android（API 26+）
5. **开发者友好 API**：Fluent Builder、注解式消息监听（@MqttServerFunction）、Spring Event 解耦
6. **丰富的扩展接口**：IMqttServerAuthHandler、IMqttMessageListener、IMqttMessageInterceptor 等，通过实现接口 + 注册 Bean 完成定制
7. **完善的监控支持**：原生对接 Prometheus + Grafana，提供连接数、消息量等关键指标
8. **GraalVM 支持**：可编译为本地可执行程序
9. **社区活跃**：Dromara 社区支撑，2600+ Star，贡献者众多
10. **文档完善**：专业文档站 + 视频教程 + 丰富示例
11. **协议覆盖广**：支持 MQTT 3.1 / 3.1.1 / 5.0

**缺点：**

1. **缺乏标准化 Benchmark**：未提供公开的性能压测数据，难以量化评估极限性能
2. **集群方案依赖 Redis**：基于 Redis Stream 实现集群，引入了外部依赖
3. **非独立部署产品**：需要嵌入到应用中使用，不是开箱即用的 Broker 产品
4. **管理控制台为独立项目**：mica-mqtt-dashboard 单独维护，集成度不如 smart-mqtt
5. **规则引擎尚未实现**：基于 easy-rule + druid sql 的规则引擎仍在 TODO 中
6. **MQTT 5.0 支持待完善**：部分 v5.0 高级特性仍在优化中

---

## 六、使用场景推荐

### 6.1 选择 smart-mqtt 的场景

- **需要独立部署 MQTT Broker**：作为基础设施中间件独立运行，类似 EMQX / Mosquitto 的替代方案
- **极致性能要求**：对消息吞吐和延迟有极端要求的场景
- **已有非 Java 技术栈**：不需要与 Java 应用深度集成，仅需 MQTT 协议交互
- **愿意购买商业授权**：企业预算允许，且接受 AGPL 许可约束

### 6.2 选择 mica-mqtt 的场景

- **自研物联网平台**：需要将 MQTT 能力嵌入业务系统，进行深度二次开发
- **Spring Boot / Solon 技术栈**：已有 Java Web 项目，需快速集成 MQTT 能力
- **需要 Client + Server**：同时需要设备端客户端和云端服务端
- **商业项目**：需要 Apache-2.0 宽松许可证，避免法律风险
- **需要 Android 支持**：边缘端 / 网关设备运行 Android 系统
- **需要监控告警**：对接 Prometheus + Grafana 实现运维可观测

---

## 七、物联网二次开发推荐

### 最终推荐：mica-mqtt

**对于需要进行物联网二次开发的场景，推荐选择 mica-mqtt**，理由如下：

#### 1. 许可证优势（决定性因素）

mica-mqtt 采用 Apache-2.0 许可证，允许自由修改、分发和商用，**无需开源衍生代码**。smart-mqtt 的 AGPL-3.0 要求任何修改后的代码必须开源，且通过网络提供服务也算"分发"，对商业物联网平台而言是巨大的法律风险。即使 smart-mqtt 提供了商业授权选项（500~5000元/年），但这意味着持续的授权成本和供应商依赖。

#### 2. 集成能力优势

物联网平台通常是一个复杂的业务系统，包含设备管理、数据存储、规则引擎、告警通知、用户管理等模块。mica-mqtt 可以作为组件直接嵌入 Spring Boot 应用：

```java
// 一个 @Service 类就能处理设备数据
@MqttServerFunction("/device/${deviceId}/telemetry")
public void handleTelemetry(String topic, DeviceData data) {
    deviceService.saveTelemetry(data);    // 存储数据
    ruleEngine.evaluate(data);            // 触发规则
    alarmService.check(data);             // 检查告警
}
```

smart-mqtt 作为独立 Broker 部署，业务系统需要通过 MQTT 协议与之交互，增加了系统复杂度和网络开销。

#### 3. 开发效率优势

- **注解式开发**：`@MqttServerFunction` 让消息处理如同写 REST Controller
- **Spring 生态**：依赖注入、事件驱动、配置管理、监控等全部复用
- **丰富接口**：IMqttServerAuthHandler（认证）、IMqttConnectStatusListener（上下线）、IMqttMessageInterceptor（拦截器）等接口覆盖了二次开发的主要扩展点
- **Session 保持**：Spring Boot Client 插件原生支持 Session 保留

#### 4. 全栈能力

mica-mqtt 同时提供 Client 和 Server，可以覆盖：

| 场景 | 使用方式 |
|------|---------|
| 云端 MQTT Broker | mica-mqtt-server + Spring Boot |
| 边缘网关 | mica-mqtt-server + mica-mqtt-client |
| 设备端（Android） | mica-mqtt-client（Android API 26+） |
| 设备模拟器/测试 | mica-mqtt-client |

#### 5. 运维友好

- 原生 Prometheus + Grafana 监控
- HTTP REST API 管理
- 支持 nginx 代理协议转发源 IP
- 支持 GraalVM 编译优化启动速度和内存

### 选择 smart-mqtt 的例外情况

如果你的场景满足以下**全部条件**，可以考虑 smart-mqtt：

1. 仅需独立部署 MQTT Broker，不需要与业务代码深度集成
2. 对单机极限性能有严苛要求（如单节点需承载 10万+ 并发连接）
3. 愿意购买商业授权并接受持续授权费用
4. 团队有能力基于插件规范进行开发和维护

---

## 八、对比速查表

| 对比维度 | smart-mqtt | mica-mqtt | 二次开发推荐 |
|---------|-----------|-----------|------------|
| 许可证 | AGPL-3.0 | Apache-2.0 | ✅ mica-mqtt |
| 定位 | 独立 Broker 产品 | 嵌入式组件 | ✅ mica-mqtt |
| 性能数据 | 详细 benchmark | 缺乏公开数据 | ⚖️ smart-mqtt 略优 |
| Spring Boot | 不支持 | 一等公民 | ✅ mica-mqtt |
| Client 能力 | 基础 | 完善 | ✅ mica-mqtt |
| Android | 不支持 | 支持 | ✅ mica-mqtt |
| 插件体系 | 成熟完善 | 接口扩展 | ⚖️ 各有特色 |
| 管理控制台 | 内置 | 独立项目 | ⚖️ smart-mqtt 略优 |
| Docker 部署 | 官方镜像 | 需自行构建 | ⚖️ smart-mqtt 略优 |
| 监控对接 | 未明确 | Prometheus | ✅ mica-mqtt |
| 社区活跃度 | 一般 | 较高 | ✅ mica-mqtt |
| 文档完善度 | 一般 | 完善 | ✅ mica-mqtt |
| 集群方案 | 内置插件 | Redis Stream | ⚖️ smart-mqtt 略优 |
| **综合推荐** | | | **✅ mica-mqtt** |
