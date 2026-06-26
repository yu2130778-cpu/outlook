# Outlook 自动注册系统 — AI 部署指南（多云适配）

> 本文档面向**在云端服务器上运行的 AI 助手**。将本文档完整发送给目标服务器的 AI，它将自动完成全部部署。
>
> **核心原则**：先检测环境，再适配路径和权限，绝不硬编码。

---

## 一、架构概览

```
┌──────────────────────────────────────────────────────────┐
│                     单机部署架构                           │
│                                                            │
│  Xvfb :98 (虚拟显示，Chrome 必须非 headless)               │
│    └── Chrome 浏览器 (CDP 协议)                            │
│                                                            │
│  代理内核（双内核，xray 优先）                              │
│    ├── Xray-core (:28890 http / :28889 socks)  ← 主内核    │
│    │   └── 从订阅拉取 vless 节点，每注册轮循切换节点        │
│    └── mihomo (:28888 mixed)                    ← 兜底内核 │
│        └── 从订阅拉取 clash/ss/trojan 节点                 │
│                                                            │
│  outlook_daemon.py (守护进程)                              │
│    ├── 每 4 小时串行注册 N 个 Outlook 账号                  │
│    ├── 注册时自动轮循代理节点（按节点，blocked 拉黑 4h）    │
│    ├── 注册后新开浏览器获取 refresh_token（避免会话干扰）   │
│    └── 每天 00:00 推送凭证到 GitHub 私有仓库                │
│                                                            │
│  outlook_dashboard_server.py (:8765)                      │
│    └── Web 面板：状态展示 + 手动操作 + 代理/节点/内核控制   │
│                                                            │
│  凭证仓库: GitHub 私有仓库 (三凭证/四凭证)                  │
│    ├── 三凭证: email----password----client_id              │
│    └── 四凭证: email----password----client_id----rt        │
└──────────────────────────────────────────────────────────┘
```

---

## 二、服务器类型适配矩阵

| 维度 | Zo Computer | Gcore / 通用 VPS | AWS / 阿里云 ECS |
|------|------------|-----------------|-----------------|
| **用户** | root | ubuntu（非 root） | root 或 ec2-user |
| **项目路径** | `/home/workspace/Email-Register` | `/home/ubuntu/Email-Register` | 自定义，建议 `/opt/Email-Register` |
| **Python** | 系统 python3 (3.12) | 需装 python3-venv，建议 venv | 需装 python3 + venv |
| **Chrome** | apt chromium + google-chrome | apt chromium 或 google-chrome | yum/apt chromium |
| **保活** | `register_user_service` (supervisor) | systemd service | systemd service |
| **sudo** | 不需要（已 root） | 需要 | 需要（除非 root 用户） |
| **磁盘** | 充足 | 建议 ≥ 20G | 建议 ≥ 20G |
| **内存** | 充足 | 建议 ≥ 4G（Chrome 每个 300-500M） | 建议 ≥ 4G |
| **网络** | 需访问 outlook.com | 需海外节点 | 需海外节点 |

---

## 三、前置准备（人工完成，AI 无权代劳）

### 3.1 必须准备

| 服务 | 用途 | 获取方式 |
|------|------|----------|
| **GitHub 私有仓库** | 存储邮箱凭证 | 新建私有仓库（如 `cloud-register-email`） |
| **GitHub Token** | 推送凭证 | Settings → Developer settings → Fine-grained token（仓库 contents 读写权限） |
| **订阅链接** | 代理节点来源 | 机场/代理服务提供的订阅 URL（支持 clash / vless / base64 格式） |

### 3.2 可选

| 服务 | 用途 |
|------|------|
| ngrok 账号 + 固定域名 | 面板外网访问 |
| CAPTCHA API Key | 自动过验证码（capsolver / nopecha） |
| SMS API Key | 自动接短信验证 |

> **⚠️ 订阅链接含敏感信息，绝不写入代码或提交到 Git。** 运行时通过环境变量或面板手动添加。

---

## 四、AI 自动部署流程

### 第 0 步：环境检测（必须先执行）

AI 在做任何操作前，**必须先运行以下检测**，根据结果适配后续路径和权限：

```bash
#!/bin/bash
# ─── 环境检测 ───
echo "=== 环境检测 ==="
echo "用户: $(whoami)"
echo "UID: $(id -u)"
echo "系统: $(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2)"
echo "架构: $(uname -m)"
echo "内存: $(free -h | awk '/^Mem:/{print $2}')"
echo "磁盘: $(df -h / | awk 'NR==2{print $4\" 可用\"}')"

# 检测是否需要 sudo
SUDO=""
[[ "$(id -u)" -ne 0 ]] && SUDO="sudo"
echo "SUDO: ${SUDO:-不需要（root）}"

# 检测项目路径
PROJECT_DIR=""
for d in /home/workspace/Email-Register /home/ubuntu/Email-Register /opt/Email-Register; do
  [[ -d "$d" ]] && PROJECT_DIR="$d" && break
done
if [[ -z "$PROJECT_DIR" ]]; then
  # 按 HOME 目录推断
  if [[ "$(whoami)" == "root" ]]; then
    PROJECT_DIR="/opt/Email-Register"
  else
    PROJECT_DIR="$HOME/Email-Register"
  fi
fi
echo "PROJECT_DIR: $PROJECT_DIR"

# 检测 Python
PYTHON="python3"
if [[ -f "$PROJECT_DIR/../email-register-venv/bin/python3" ]]; then
  PYTHON="$PROJECT_DIR/../email-register-venv/bin/python3"
fi
python3 --version 2>&1
echo "PYTHON: $PYTHON"
```

### 第 1 步：安装系统依赖

```bash
# apt 系（Debian/Ubuntu）
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq \
  python3 python3-pip python3-venv \
  git curl wget xvfb \
  chromium chromium-driver \
  libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
  libgbm1 libxshmfence1 libxcomposite1 libxrandr2 \
  libxdamage1 libpango-1.0-0 libcairo2 libatspi2.0-0 \
  libgtk-3-0 libx11-xcb1

# Google Chrome（兼容性优于 chromium，优先安装）
if ! command -v google-chrome-stable &>/dev/null; then
  wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  $SUDO dpkg -i /tmp/chrome.deb 2>/dev/null || $SUDO apt-get install -f -y -qq
fi

# yum 系（CentOS/Amazon Linux）—— 如果 apt 不可用
if ! command -v apt-get &>/dev/null; then
  $SUDO yum install -y python3 python3-pip git curl wget \
    xorg-x11-server-Xvfb chromium \
    nss atk at-spi2-atk libdrm libxkbcommon \
    libgbm libXcomposite libXrandr libXdamage pango cairo
fi
```

### 第 2 步：Python 依赖

```bash
# 创建虚拟环境（推荐，避免系统 Python 污染）
VENV_DIR="$(dirname $PROJECT_DIR)/email-register-venv"
python3 -m venv "$VENV_DIR" 2>/dev/null || $SUDO apt-get install -y python3-venv && python3 -m venv "$VENV_DIR"
PYTHON="$VENV_DIR/bin/python3"

$PYTHON -m pip install --upgrade pip -q
$PYTHON -m pip install -q \
  playwright requests aiohttp pyyaml toml \
  fake-useragent undetected-chromedriver \
  ddddocr httpx sqlalchemy PySocks
$PYTHON -m playwright install chromium
$PYTHON -m playwright install-deps chromium 2>/dev/null || $SUDO $PYTHON -m playwright install-deps chromium
```

### 第 3 步：克隆代码

```bash
git clone https://github.com/xingluoyuankong/outlook-auto-register.git "$PROJECT_DIR"
cd "$PROJECT_DIR"
```

### 第 4 步：Xvfb 虚拟显示

> **⚠️ Outlook 会检测 headless 浏览器并拦截，必须用 Xvfb + 可视实体浏览器。**

```bash
# 清理僵尸锁（进程已死但锁文件残留 → 新 Xvfb 起不来）
if ! pgrep -f "Xvfb :98" &>/dev/null; then
  rm -f /tmp/.X98-lock /tmp/.X11-unix/X98
  Xvfb :98 -screen 0 1366x768x24 -ac -nolisten tcp &
  sleep 2
fi
export DISPLAY=:98
```

### 第 5 步：代理内核

系统使用**双内核**：Xray（主）+ mihomo（兜底）。

```bash
cd "$PROJECT_DIR"

# 5.1 安装 mihomo (MetaCubeX)
MIHOMO_DIR="邮箱注册/mihomo_runtime"
mkdir -p "$MIHOMO_DIR"
ARCH=$(uname -m)
if [[ ! -x "$MIHOMO_DIR/mihomo-linux" ]]; then
  case "$ARCH" in
    x86_64)  URL="https://github.com/MetaCubeX/mihomo/releases/download/v1.19.12/mihomo-linux-amd64-v1.19.12.gz" ;;
    aarch64) URL="https://github.com/MetaCubeX/mihomo/releases/download/v1.19.12/mihomo-linux-arm64-v1.19.12.gz" ;;
  esac
  curl -fsSL "$URL" | gunzip > "$MIHOMO_DIR/mihomo-linux"
  chmod +x "$MIHOMO_DIR/mihomo-linux"
fi

# 5.2 安装 Xray-core
XRAY_DIR="邮箱注册/xray_runtime"
mkdir -p "$XRAY_DIR"
if ! command -v xray &>/dev/null && [[ ! -x "$XRAY_DIR/xray" ]]; then
  case "$ARCH" in
    x86_64)  XURL="https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip" ;;
    aarch64) XURL="https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-arm64-v8a.zip" ;;
  esac
  curl -fsSL "$XURL" -o /tmp/xray.zip
  $SUDO unzip -o /tmp/xray.zip -d /usr/local/bin/ xray >/dev/null 2>&1
  $SUDO chmod +x /usr/local/bin/xray
fi

# 5.3 添加订阅链接（运行时配置，不写入代码）
# 方式 A：环境变量
#   export SUB_PROXY_URL="https://your-subscription-url/subscribe?token=xxx"
# 方式 B：面板手动添加（部署后访问 :8765 → 订阅管理 tab）
# 方式 C：直接写入 subscriptions.json
echo '[]' > "$MIHOMO_DIR/subscriptions.json"  # 初始为空，后续通过面板添加
```

### 第 6 步：凭证仓库

```bash
CLOUD_DIR="$PROJECT_DIR/云端注册邮箱"
# 优先 SSH 克隆，失败用 HTTPS + Token
git clone "git@github.com:你的用户名/cloud-register-email.git" "$CLOUD_DIR" 2>/dev/null || \
git clone "https://${GITHUB_TOKEN}@github.com/你的用户名/cloud-register-email.git" "$CLOUD_DIR" 2>/dev/null || \
mkdir -p "$CLOUD_DIR"  # 克隆失败不阻塞，后续手动配置
```

### 第 7 步：创建运行时目录

```bash
mkdir -p "$PROJECT_DIR/runtime_outlook/logs"
mkdir -p "$PROJECT_DIR/runtime_outlook/rt_tokens"
mkdir -p "$PROJECT_DIR/runtime_outlook/rt_input"
chmod -R u+rwX,g+rwX "$PROJECT_DIR/runtime_outlook"
```

### 第 8 步：清除 Python 缓存

> **⚠️ 修改代码后 __pycache__ 中旧 .pyc 会导致修复不生效。每次部署/改代码后必须清缓存。**

```bash
find "$PROJECT_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
```

### 第 9 步：配置保活（按服务器类型）

#### 方案 A：Zo Computer（用 register_user_service）

```python
# 让 Zo 的 AI 执行：
register_user_service(
    label="outlook-auto-register",
    mode="process",
    entrypoint="bash outlook_daemon_hub.sh",
    workdir="/home/workspace/Email-Register",
)
```

#### 方案 B：通用 VPS（systemd）

```bash
cat > /etc/systemd/system/outlook-auto-register.service << EOF
[Unit]
Description=Outlook Auto Register Daemon
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$PROJECT_DIR
Environment=DISPLAY=:98
Environment=PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$PYTHON $PROJECT_DIR/outlook_daemon.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

$SUDO systemctl daemon-reload
$SUDO systemctl enable outlook-auto-register
$SUDO systemctl start outlook-auto-register
```

### 第 10 步：部署后验证

```bash
echo "=== 部署验证清单 ==="

# 1. Xvfb 运行中
pgrep -f "Xvfb :98" >/dev/null && echo "✅ Xvfb" || echo "❌ Xvfb"

# 2. 守护进程运行中
# Zo:    supervisorctl status
# VPS:   systemctl is-active outlook-auto-register
systemctl is-active outlook-auto-register 2>/dev/null && echo "✅ daemon" || echo "⚠️ daemon（Zo 用 supervisorctl 检查）"

# 3. 面板可访问
curl -s -m 5 http://localhost:8765/ | head -1 >/dev/null 2>&1 && echo "✅ 面板 :8765" || echo "❌ 面板"

# 4. xray 内核
curl -s -m 8 --proxy http://127.0.0.1:28890 https://ipinfo.io/json | grep -q ip && echo "✅ xray 代理" || echo "⚠️ xray（需先添加订阅）"

# 5. 磁盘空间
AVAIL=$(df -h / | awk 'NR==2{print $4}')
echo "✅ 磁盘可用: $AVAIL"

# 6. 手动注册测试
echo "手动注册: cd $PROJECT_DIR && $PYTHON outlook_launcher.py run --count 5 --shuffle"
```

---

## 五、核心概念与注意事项

### 5.1 代理轮循（关键机制）

- **按节点轮循**：每注册一个账号自动切换到下一个可用节点
- **遍历全部节点算一轮**：跑完所有节点后才算一个轮循，然后重新开始
- **blocked 自动拉黑**：账号被 Outlook 拦截时，将该节点拉黑 4 小时
- **节点优先级**：台湾/日本节点优先排序（成功率最高）
- **状态持久化**：游标/黑名单/轮次保存在 `runtime_outlook/proxy_rotation.json`，跨批次不丢失

### 5.2 RT 获取（refresh_token）

- **必须新开浏览器**获取 RT，不能复用注册时的浏览器（会话干扰导致卡在账号选择页）
- 注册成功后，新开一个独立 Chrome 实例 → 导航到 OAuth 授权 URL → 输入邮箱密码 → 同意授权 → 回调获取 code → 换取 RT
- RT 获取失败不影响注册成功，后续可批量补 RT

### 5.3 unknown 页面状态处理

- 注册成功后 Outlook 会跳转到 `account.live.com` 或 OAuth 授权页
- 检测到这些 URL 应立即判定为成功，不要在 "unknown" 状态死循环
- 最多迭代 50 次（约 2.5 分钟）后超时

### 5.4 浏览器清理

- **绝不用 `pkill -9 chrome`** — 会误杀 Zo 的 agent-browser
- 只匹配 `outlook.*user-data|cdp_outl|cdp_reg` 模式
- 每次注册后、每批次后、RT 提取后自动清理孤儿进程
- 内存紧张时（4G 服务器）堆积会导致 OOM

### 5.5 订阅格式兼容

- **clash 格式**：YAML，含 `proxies` 列表
- **vless URI 格式**：base64 编码的 `vless://uuid@server:port?...#name` 列表
- **混合格式**：自动检测并解析
- 订阅链接的 User-Agent 影响返回格式，系统已处理

---

## 六、常见坑（按严重程度排序）

| # | 坑 | 表现 | 解决 |
|---|-----|------|------|
| 1 | **路径硬编码** | 非 Zo 服务器 Chrome 启动失败 `Permission denied: '/home/workspace'` | 全局搜索 `/home/workspace` 并替换为动态路径 |
| 2 | **Xvfb 僵尸锁** | 新 Xvfb 起不来，Chrome 无法连接 X 显示 | 启动前删 `/tmp/.X98-lock` 和 `/tmp/.X11-unix/X98` |
| 3 | **headless 被拦截** | Outlook 检测到 headless 直接 blocked | 必须 Xvfb + 非 headless Chrome |
| 4 | **__pycache__ 缓存** | 改了代码但修复不生效 | `find ... -name __pycache__ -exec rm -rf {} +` |
| 5 | **调度状态残留** | daemon 跳过注册："距上次完成未满 4 小时" | `echo "{}" > runtime_outlook/daemon_schedule.json` |
| 6 | **凭证文件名 @ 符号** | `@` 被 `safe_name()` 替换成 `_at_` 导致找不到 | 直接用完整邮箱作文件名 |
| 7 | **python3-venv 缺失** | `python3 -m venv` 报错 | `apt install python3-venv` 或 `python3.13-venv` |
| 8 | **pip PEP 668** | `pip install` 被拒 | 用 venv 或加 `--break-system-packages` |
| 9 | **多节点 Git 推送冲突** | 凭证仓库 push 失败 | 先 `git pull --rebase` 再 push |
| 10 | **OOM** | 4G 内存 Chrome 堆积导致沙箱重启 | 串行注册、每批 ≤ 5、及时清理孤儿进程 |

---

## 七、维护命令速查

```bash
# 手动注册 5 个（轮循节点）
cd $PROJECT_DIR && $PYTHON outlook_launcher.py run --count 5 --shuffle

# 手动注册 + 立即获取 RT
cd $PROJECT_DIR && $PYTHON outlook_launcher.py run --count 5 --shuffle --extract-rt

# 只获取 RT（补未拿到 RT 的账号）
cd $PROJECT_DIR && $PYTHON post_register_fetch_rt.py --limit 20

# 推送凭证到 GitHub
cd $PROJECT_DIR && $PYTHON sync_credentials.py --push

# 查看代理轮循状态
cat $PROJECT_DIR/runtime_outlook/proxy_rotation.json | python3 -m json.tool

# 查看注册结果
cat $PROJECT_DIR/runtime_outlook/results.jsonl | python3 -c "import sys,json; [print(json.loads(l).get('email',''), '✅' if json.loads(l).get('success') else '❌') for l in sys.stdin]"

# 查看被拉黑节点
cat $PROJECT_DIR/runtime_outlook/blocked_nodes.json | python3 -m json.tool

# 重置代理轮循（新轮次从头开始）
echo '{}' > $PROJECT_DIR/runtime_outlook/proxy_rotation.json

# 清理孤儿 Chrome
python3 -c "import sys; sys.path.insert(0,'邮箱注册'); from cdp_outlook import kill_orphan_chrome_processes; kill_orphan_chrome_processes()"

# 重启 xray 内核
python3 -c "import sys; sys.path.insert(0,'邮箱注册'); from xray_proxy import get_xray_manager; m=get_xray_manager(); m.stop(); print(m.start())"

# 查看面板
curl -s http://localhost:8765/api/status | python3 -m json.tool
```

---

## 八、目录结构

```
Email-Register/
├── 邮箱注册/                      # 核心注册库
│   ├── cdp_outlook.py             #   CDP 协议注册引擎
│   ├── cdp_browser.py             #   Chrome 启动/管理
│   ├── subscription_proxy.py      #   mihomo 代理管理器
│   ├── xray_proxy.py              #   xray 代理管理器（主内核）
│   ├── auto_proxy_subscription.py #   订阅自动注册
│   └── mihomo_runtime/            #   mihomo 运行时（.gitignore）
├── outlook_launcher.py            # 注册启动器（轮循/批量/RT）
├── outlook_daemon.py              # 守护进程（4h 循环）
├── outlook_daemon_status.py       # 守护状态管理
├── outlook_dashboard_server.py    # Web 面板 (:8765)
├── post_register_fetch_rt.py      # 批量获取 RT
├── sync_credentials.py            # 凭证同步到 GitHub
├── outlook-token-tool/            # RT 提取工具
│   └── batch_rt.py                #   批量 RT（新浏览器模式）
├── deploy/                        # 部署脚本
├── runtime_outlook/               # 运行时数据（.gitignore）
│   ├── results.jsonl              #   注册结果
│   ├── proxy_rotation.json        #   轮循状态
│   ├── blocked_nodes.json         #   节点黑名单
│   └── logs/                      #   日志
└── 云端注册邮箱/                   # 凭证仓库 clone（.gitignore）
```

---

*最后更新: 2026-06-26 | 适配 v3.1 双内核架构*
