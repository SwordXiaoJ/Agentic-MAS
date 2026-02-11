# SLIM 安全配置指南

## 概述

本项目使用 SLIM (Secure Low-Latency Interactive Messaging) 作为 Agent 之间的通信传输层。安全配置用于保护 **Agent 之间的通信**，确保：

1. **传输加密** - 防止消息在网络中被窃听
2. **身份认证** - 确保通信双方是合法的 Agent
3. **端到端加密** - 即使 SLIM 服务器被攻破，消息内容也无法被解密

```
┌─────────────────┐                    ┌─────────────────┐
│  Medical Agent  │◄───── SLIM ───────►│ Satellite Agent │
│   (Org A)       │   (安全通道)        │    (Org B)      │
└─────────────────┘                    └─────────────────┘
         │                                      │
         │              ┌─────────┐             │
         └──────────────►  SLIM   ◄─────────────┘
                        │ Server  │
                        └─────────┘
                     (消息路由中心)
```

## 安全阶段

### Phase 1: Insecure (当前 - 开发环境)

```bash
SLIM_AUTH_MODE=insecure
```

**说明**: 无认证，无加密。仅用于本地开发和测试。

**适用场景**:
- 本地开发
- 内网测试环境
- 快速原型验证

**风险**: 任何人都可以连接到 SLIM 服务器并发送/接收消息。

---

### Phase 2: TLS + Basic Auth

```bash
SLIM_AUTH_MODE=basic
SLIM_TLS_ENABLED=true
SLIM_TLS_CERT_PATH=./infrastructure/certs/server-cert.pem
SLIM_TLS_KEY_PATH=./infrastructure/certs/server-key.pem
SLIM_BASIC_USERNAME=admin
SLIM_BASIC_PASSWORD=your-secure-password
```

**说明**:
- **TLS**: 传输层加密，防止网络窃听
- **Basic Auth**: 用户名/密码认证

**适用场景**:
- 小型团队内部部署
- 简单的生产环境

**安全级别**: ⭐⭐☆☆☆

---

### Phase 3: TLS + JWT

```bash
SLIM_AUTH_MODE=jwt
SLIM_TLS_ENABLED=true
SLIM_JWT_ISSUER=agntcy-network
SLIM_JWT_AUDIENCE=medical-agent,satellite-agent,general-agent
SLIM_JWT_PRIVATE_KEY_PATH=./infrastructure/certs/jwt-private.pem
SLIM_JWT_PUBLIC_KEY_PATH=./infrastructure/certs/jwt-public.pem
```

**说明**:
- **TLS**: 传输层加密
- **JWT (JSON Web Token)**: 基于令牌的认证，支持过期时间和权限控制

**JWT 工作流程**:
```
1. Agent 启动时使用私钥生成 JWT Token
2. JWT 包含: agent_id, 过期时间, 权限范围
3. 每次通信携带 JWT Token
4. SLIM 服务器验证 Token 签名和有效期
```

**适用场景**:
- 多团队协作
- 需要细粒度权限控制
- Token 可以设置过期时间

**安全级别**: ⭐⭐⭐☆☆

---

### Phase 4: mTLS + SPIRE (Zero Trust)

```bash
SLIM_AUTH_MODE=spire
SPIRE_AGENT_SOCKET=/run/spire/sockets/agent.sock
SPIRE_TRUST_DOMAIN=agntcy.network
SPIRE_TARGET_SPIFFE_ID=spiffe://agntcy.network/agent/medical
```

**说明**:
- **mTLS (Mutual TLS)**: 双向证书认证，客户端和服务器都需要提供证书
- **SPIRE**: 自动化的工作负载身份管理系统

**SPIRE 工作流程**:
```
1. SPIRE Agent 在每个节点上运行
2. Agent 启动时从 SPIRE 获取短期证书 (SVID)
3. 证书自动轮换，无需手动管理
4. 基于 SPIFFE ID 进行身份验证
```

**适用场景**:
- 企业级生产环境
- 云原生 / Kubernetes 部署
- 零信任架构

**安全级别**: ⭐⭐⭐⭐⭐

---

## MLS 端到端加密

```bash
SLIM_MLS_ENABLED=true
SLIM_SHARED_SECRET=your-mls-secret
```

**MLS (Message Layer Security)** 是独立于传输层的端到端加密：

```
┌────────────┐                              ┌────────────┐
│  Agent A   │                              │  Agent B   │
│            │                              │            │
│ [明文消息] │                              │ [明文消息] │
│     ↓      │                              │     ↑      │
│ [MLS加密]  │───► SLIM Server ────────────►│ [MLS解密]  │
│            │    (只能看到密文)             │            │
└────────────┘                              └────────────┘
```

**优势**:
- 即使 SLIM 服务器被攻破，消息内容也无法被解密
- 提供前向保密 (Forward Secrecy)
- 支持群组加密

---

## 各配置项详解

| 配置项 | 作用 | 说明 |
|--------|------|------|
| `SLIM_AUTH_MODE` | 认证模式 | insecure/basic/jwt/mtls/spire |
| `SLIM_TLS_ENABLED` | 启用 TLS | 传输层加密 |
| `SLIM_TLS_CERT_PATH` | TLS 证书路径 | 服务器证书 |
| `SLIM_TLS_KEY_PATH` | TLS 私钥路径 | 证书对应的私钥 |
| `SLIM_TLS_CA_PATH` | CA 证书路径 | 用于验证对方证书 |
| `SLIM_BASIC_USERNAME` | Basic Auth 用户名 | - |
| `SLIM_BASIC_PASSWORD` | Basic Auth 密码 | - |
| `SLIM_JWT_ISSUER` | JWT 签发者 | 标识谁签发的 Token |
| `SLIM_JWT_AUDIENCE` | JWT 受众 | 允许的目标 Agent 列表 |
| `SLIM_JWT_PRIVATE_KEY_PATH` | JWT 私钥 | 用于签名 Token |
| `SLIM_JWT_PUBLIC_KEY_PATH` | JWT 公钥 | 用于验证 Token |
| `SLIM_MLS_ENABLED` | 启用 MLS | 端到端加密 |
| `SLIM_SHARED_SECRET` | MLS 共享密钥 | 开发环境用，生产应使用密钥交换 |
| `SPIRE_AGENT_SOCKET` | SPIRE Socket | SPIRE Agent 通信路径 |
| `SPIRE_TRUST_DOMAIN` | 信任域 | SPIFFE 身份的命名空间 |

---

## 使用示例

### 检查当前安全配置

```python
from config.security_config import get_security_config, print_security_config

# 打印配置
print_security_config()

# 程序中使用
config = get_security_config()
if config.is_secure:
    print("Running in secure mode")
else:
    print("WARNING: Running in insecure mode")
```

### 在代码中获取安全设置

```python
from config.security_config import get_security_config

config = get_security_config()

# 获取传输层 TLS 配置
tls_config = config.get_transport_tls_config()
# 返回: {"insecure": True} 或 {"insecure": False, "ca_path": "..."}

# 获取身份认证配置
identity_config = config.get_identity_config()
# 返回: {"type": "jwt", "issuer": "...", ...} 等
```

---

## 推荐的升级路径

```
开发环境           测试环境              预生产环境           生产环境
   │                  │                    │                   │
   ▼                  ▼                    ▼                   ▼
Insecure    →    TLS + Basic    →    TLS + JWT    →    mTLS + SPIRE
                                                              +
                                                            MLS
```

## SLIMTransport 参数映射

当前版本 `slim-bindings 0.6.3` 和 `agntcy-app-sdk 0.4.6` 支持的参数：

| 环境变量 | SLIMTransport 参数 | 说明 |
|----------|-------------------|------|
| `SLIM_TLS_ENABLED` | `tls_insecure` | `True`=跳过验证, `False`=验证证书 |
| `SLIM_SHARED_SECRET` | `shared_secret_identity` | MLS 端到端加密密钥 |
| `SLIM_JWT_*` | `jwt` | JWT 认证令牌 |
| `SLIM_JWT_AUDIENCE` | `audience` | JWT 受众列表 |

代码通过 `security_config.get_slim_transport_kwargs()` 自动转换配置到正确的参数名。

---

## 常见问题

### Q: 为什么需要这些安全配置？

A: 当多个 Agent 分布在不同的服务器/组织时，通信可能经过公网。安全配置确保：
- 消息不被窃听 (TLS)
- 只有授权的 Agent 可以参与通信 (认证)
- 即使中间人攻击也无法解密消息 (MLS)

### Q: 本地开发需要配置吗？

A: 不需要。默认 `SLIM_AUTH_MODE=insecure` 即可正常运行。

### Q: JWT 和 SPIRE 有什么区别？

A:
- **JWT**: 需要手动管理密钥，适合简单场景
- **SPIRE**: 自动化证书管理，自动轮换，适合大规模部署

### Q: MLS 和 TLS 有什么区别？

A:
- **TLS**: 保护 Agent ↔ SLIM Server 之间的通信
- **MLS**: 保护 Agent ↔ Agent 之间的消息内容（SLIM Server 无法解密）
