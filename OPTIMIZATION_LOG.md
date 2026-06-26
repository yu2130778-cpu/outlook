# Outlook 自动注册系统 — 优化记录

> 日期: 2026-06-26 | 基于 Zo 服务器 (Debian 12, 4GB RAM, x86_64) 实战验证

---

## 一、本次优化总览

| # | 优化项 | 状态 | 核心文件 |
|---|--------|------|----------|
| 1 | Xray 内核整合（v2ray 系，支持 Reality 协议） | ✅ | `邮箱注册/xray_proxy.py` (新增) |
| 2 | 代理内核纳入 daemon 保活（不再游离启动） | ✅ | `outlook_daemon.py` |
| 3 | 前端双内核控制面板（mihomo + xray） | ✅ | `outlook_dashboard_server.py` |
| 4 | Xray 直接抓订阅（clash YAML + base64 vless://） | ✅ | `邮箱注册/xray_proxy.py` |
| 5 | 节点轮循（按节点，非按 IP） | ✅ | `outlook_launcher.py` ProxyRotator |
| 6 | account_blocked 自动拉黑节点 4h | ✅ | `outlook_launcher.py` |
| 7 | 注册失败页面截图+dump 逆向分析 | ✅ | `邮箱注册/cdp_outlook.py` |
| 8 | RT 始终用新浏览器获取（禁用同浏览器） | ✅ | `邮箱注册/cdp_outlook.py` + `batch_rt.py` |
| 9 | unknown 状态快速成功检测 | ✅ | `邮箱注册/cdp_outlook.py` |
| 10 | 分批并行注册（可选 workers 参数） | ✅ | `outlook_launcher.py` |

---

## 二、架构变更

### 2.1 双内核并存

```
                    ┌─────────────────────────┐
                    │    ProxyRotator (轮循)    │
                    │  xray 为主，mihomo 兜底   │
                    └──────┬──────────┬────────┘
                           │          │
                    ┌──────▼──┐  ┌────▼─────┐
                    │  Xray   │  │ mihomo   │
                    │ 28889   │  │ 28888    │
                    │ 28890   │  │ (mixed)  │
                    │ (socks  │  │          │
                    │  +http) │  │          │
                    └────┬────┘  └────┬─────┘
                         │            │
                    vless节点     clash节点
                   (reality/      (全部类型)
                    tls/ws)
```

### 2.2 内核选型理由

| 内核 | 协议系 | Reality 支持 | 用途 |
|------|--------|-------------|------|
| **Xray-core** | V2Ray 系 | ✅ 原生 | **主内核** — 订阅大量 reality+xtls-rprx-vision 节点 |
| mihomo (Clash.Meta) | Clash 系 | ✅ | 兜底内核 — 解析全部 clash 格式节点 |

> ⚠️ 不能用 v2ray-core（不支持 Reality 协议），必须用 Xray-core（XTLS/Xray-core）。

### 2.3 端口规划

| 服务 | 端口 | 说明 |
|------|------|------|
| mihomo mixed | 28888 | HTTP+SOCKS 混合入站 |
| mihomo API | 29090 | RESTful 控制 API |
| xray socks | 28889 | SOCKS5 入站 |
| xray http | 28890 | HTTP 入站（注册机用） |
| dashboard | 8765 | 前端面板 |
| 用户独立 VPN | 443 | xray-vless 服务（绝不触碰） |

---

## 三、代理轮循详解

### 3.1 轮循规则

- **按节点轮循**（非按 IP 去重）：同一 IP 的不同节点照常轮循
- 游标遍历全部节点，每个注册取下一个「对 Outlook 可用且未被拉黑」的节点
- **遍历完一轮（全部节点都试过一遍）才算一个轮循**，之后重新开始下一轮
- `account_blocked` 时按**节点名**拉黑（4 小时不再使用该节点）
- 状态持久化到 `runtime_outlook/proxy_rotation.json`，跨批次保持游标

### 3.2 节点优先级排序

台湾/日本节点优先（实测成功率最高），美国 C 系列次之：
```python
PRIORITY = ["台湾", "日本", "JP", "TW", "Singapore", "新加坡", "HK", "香港"]
```

### 3.3 黑名单机制

```python
blocked_nodes.json: { "节点名": block_until_timestamp }
# account_blocked → mark_blocked(node_name, hours=4)
# 4 小时后自动解封
```

### 3.4 ⚠️ 并行注册的坑（重要）

**不要用真正的多线程并行注册**（workers > 1 的分批模式可以，但纯并行不行）：
- 多线程同时调 `xray.switch_node()` 会互相覆盖节点
- 一个线程 blocked 会误封另一个线程正在用的节点
- **建议：串行模式（workers=1）最稳定**，分批模式（workers=2）可用但需谨慎

---

## 四、RT 获取优化

### 4.1 核心变更：始终用新浏览器获取 RT

**原因**：注册浏览器有 Outlook 登录态，直接跳 OAuth 会进入"账号选择页"卡死。

**方案**：
1. 注册成功后关闭注册浏览器
2. 新开一个干净浏览器（无登录态）
3. 用 Playwright 走 OAuth device-code 流程获取 RT

### 4.2 RT 获取流程（参考原仓库 batch_rt.py）

```
新浏览器(无cookie) → 打开 OAuth authorize URL (含 login_hint + prompt=login)
→ 密码页(已预填email) → 填密码 → 提交
→ consent 页 → 点 Accept → localhost 回调拿到 code
→ exchange_authorization_code → refresh_token
```

### 4.3 batch_rt.py 重试机制

- 首次失败 → 新浏览器实例重试（换端口避免冲突）
- 确定性失败（not_exist / wrong_password）不重试
- 每个账号独立 Playwright 实例，用完清理 Chrome 孤儿进程

---

## 五、失败逆向分析

### 5.1 失败页面捕获

`cdp_outlook.py` 在所有错误分支调用 `_capture_failure_dump()`：
- 截图保存到 `runtime_outlook/fail_dumps/`
- 记录 URL、title、body 文本、页面状态

### 5.2 失败原因统计（今日 123 次注册）

| 原因 | 次数 | 占比 | 根因 |
|------|------|------|------|
| account_blocked | ~35 | 28% | 微软风控，IP/行为被标记 |
| max_iterations_reached | ~18 | 15% | 页面卡 unknown 状态 |
| proxy_error | 4 | 3% | 节点不通 |
| browser_crashed | 1 | 1% | Chrome OOM |

### 5.3 account_blocked 根因

- **不是 IP 问题**：同一节点有时成功有时 blocked
- **是行为指纹问题**：Chrome 自动化特征被检测
- **规律**：台湾/日本节点成功率 > 美国节点
- **对策**：拉黑节点 4h + 换节点重试

### 5.4 unknown 状态优化

注册成功后跳转到 OAuth 授权页，主循环检测不到已知页面状态 → 卡 unknown。
**修复**：在 unknown 处理前快速检测 OAuth URL（`oauth20_authorize`）+ account_home，提前判定成功。

---

## 六、注意事项

### 6.1 ⚠️ 绝对不要做的事

1. **不要 `pkill -9 chrome`** — 会杀掉 Zo 的 agent-browser，只匹配 `outlook.*user-data|cdp_outl|cdp_reg`
2. **不要用 headless 浏览器** — Outlook 检测 headless 并拦截
3. **不要用 v2ray-core** — 不支持 Reality 协议
4. **不要多线程同时操作 xray switch_node** — 会互相覆盖
5. **不要推送 subscriptions.json / config.yaml / 凭证目录** — 含订阅链接和账号密码

### 6.2 常见坑

| 坑 | 表现 | 解决 |
|----|------|------|
| Xvfb 僵尸锁 | Xvfb 起不来 | 删除 `/tmp/.X98-lock` + `/tmp/.X11-unix/X98` |
| Chrome 幽灵进程 | OOM | 每次 `kill_orphan_chrome_processes()` |
| __pycache__ 旧缓存 | 修复不生效 | `find . -name __pycache__ -exec rm -rf {} +` |
| 调度状态残留 | 跳过注册 | `echo {} > runtime_outlook/daemon_schedule.json` |
| mihomo 节点全 dead | 代理不通 | `ensure_mihomo_proxy.sh` 或手动重启 |
| xray 路由规则 | 走错 outbound | `routing.rules: []` 让 xray 走第一个 outbound |

### 6.3 4GB 内存优化

- 串行注册（workers=1），每批最多 5 个
- 每次注册后清理 Chrome 孤儿进程
- mihomo + xray 不同时跑大量实例
- 如果 OOM，减少每批数量为 3 个

---

## 七、验证结果（2026-06-26）

| 指标 | 数值 |
|------|------|
| 今日注册 | 62/123 成功 (50%) |
| 含 RT | 33/62 (53%) |
| 节点总数 | 63 (xray) |
| 轮循完成 | 1 轮全部节点 |
| 黑名单 | 11 节点 (4h 自动解封) |
| 失败捕获 | 全部截图+dump |

---

*文档版本: v1.0 | 最后更新: 2026-06-26*
