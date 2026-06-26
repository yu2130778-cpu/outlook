# Outlook 自动注册系统 — 全新服务器部署指南

> **给 AI 的说明**：将本文件完整阅读后，按照步骤执行部署。适配 Zo 服务器、Gcore/普通 VPS、本地开发机三种环境。

---

## 一、系统架构

```
┌─────────────────────────────────────────────────────┐
│  Xvfb :98 (虚拟显示, Chrome 必须 non-headless)       │
│    └── Chrome 浏览器 (CDP 协议)                       │
│                                                       │
│  Xray-core 内核 (:28889 socks / :28890 http)         │
│    └── 直接抓订阅 → 解析 vless节点(reality/tls/ws)    │
│    └── 按节点轮循, blocked自动拉黑4h                  │
│                                                       │
│  mihomo 内核 (:28888 mixed) — 兜底                    │
│    └── clash格式节点 (全部类型)                       │
│                                                       │
│  outlook_daemon.py (守护进程)                         │
│    ├── 保活: Xvfb + xray + mihomo + dashboard         │
│    ├── 每 4 小时串行注册 5 个 Outlook 账号            │
│    ├── 注册后新浏览器获取 refresh_token               │
│    └── 每天 00:00 推送凭证到 GitHub 私有仓库          │
│                                                       │
│  outlook_dashboard_server.py (:8765)                  │
│    └── 前端面板: 状态 + 手动操作 + 双内核控制          │
└─────────────────────────────────────────────────────┘
```

---

## 二、环境检测（部署前必须执行）

```bash
#!/bin/bash
# 检测服务器类型
echo "=== 1. 操作系统 ==="
cat /etc/os-release | grep -E "^ID=|^VERSION="

echo "=== 2. 当前用户 ==="
whoami
id -u  # 0=root, 非0需要sudo

echo "=== 3. 内存 ==="
free -h | grep Mem

echo "=== 4. 磁盘 ==="
df -h / | tail -1

echo "=== 5. 架构 ==="
uname -m  # x86_64 / aarch64

echo "=== 6. Python ==="
python3 --version 2>/dev/null || echo "未安装"
python3 -m venv --help >/dev/null 2>&1 && echo "venv 可用" || echo "venv 缺失(需安装 python3-venv)"

echo "=== 7. 部署目标判断 ==="
if [[ -f /etc/zo/supervisord-user.conf ]] || grep -q "zocomputer" /etc/hostname 2>/dev/null; then
  echo "→ Zo 服务器 (用 register_user_service 保活)"
elif [[ "$(whoami)" == "ubuntu" ]]; then
  echo "→ Gcore/Ubuntu VPS (用 systemd 保活)"
else
  echo "→ 通用 VPS (用 systemd 保活)"
fi
```

---

## 三、路径适配（致命，必须正确）

不同服务器项目路径不同，**所有脚本已改为动态路径**，但部署时仍需确认：

| 服务器类型 | 项目路径 | Python venv | 用户 |
|-----------|----------|-------------|------|
| Zo 服务器 | `/home/workspace/Email-Register` | `/home/workspace/email-register-venv` | root |
| Gcore/Ubuntu VPS | `/home/ubuntu/Email-Register` | `/home/ubuntu/email-register-venv` | ubuntu |
| 通用 VPS | `~/Email-Register` | `~/email-register-venv` | 当前用户 |

**检查代码中是否有残留的硬编码路径**：
```bash
cd $PROJECT_DIR
grep -rn "/home/workspace" 邮箱注册/*.py
# 如果有输出，必须替换为动态路径:
#   Path(__file__).resolve().parents[1]  (项目根目录)
#   Path.home()  (用户家目录)
```

---

## 四、逐步部署

### 4.1 安装系统依赖

```bash
# 检测是否需要 sudo
SUDO=""
[[ "$(id -u)" -ne 0 ]] && SUDO="sudo"

$SUDO apt-get update -qq

# 基础依赖
$SUDO apt-get install -y -qq \
  python3 python3-pip python3-venv \
  git curl wget xvfb \
  chromium chromium-driver \
  libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
  libgbm1 libxshmfence1 libxcomposite1 \
  libxrandr2 libxdamage1 libpango-1.0-0 libcairo2 \
  libatspi2.0-0 libgtk-3-0 libx11-xcb1

# Google Chrome (优先，兼容性更好)
if ! command -v google-chrome-stable &>/dev/null; then
  wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  $SUDO dpkg -i /tmp/chrome.deb 2>/dev/null || $SUDO apt-get install -f -y -qq
fi
```

### 4.2 克隆代码

```bash
# 设置项目路径（根据服务器类型调整）
if [[ "$(whoami)" == "ubuntu" ]]; then
  PROJECT_DIR="/home/ubuntu/Email-Register"
else
  PROJECT_DIR="/home/workspace/Email-Register"
fi

git clone https://github.com/xingluoyuankong/outlook-auto-register.git "$PROJECT_DIR"
cd "$PROJECT_DIR"
```

### 4.3 Python 虚拟环境

```bash
# venv 缺失时先安装
python3 -m venv --help >/dev/null 2>&1 || $SUDO apt-get install -y python3-venv 2>/dev/null || $SUDO apt-get install -y python3.13-venv

# 创建虚拟环境
VENV_DIR="$(dirname "$PROJECT_DIR")/email-register-venv"
python3 -m venv "$VENV_DIR"
PYTHON="$VENV_DIR/bin/python3"

# 安装依赖
$PYTHON -m pip install --upgrade pip
$PYTHON -m pip install \
  playwright requests aiohttp pyyaml toml \
  fake-useragent undetected-chromedriver \
  ddddocr httpx sqlalchemy PySocks

# Playwright 浏览器
$PYTHON -m playwright install chromium
$SUDO $PYTHON -m playwright install-deps chromium 2>/dev/null || true
```

### 4.4 安装 Xray-core 内核

```bash
ARCH=$(uname -m)
XRAY_DIR="$PROJECT_DIR/邮箱注册/xray_runtime"
mkdir -p "$XRAY_DIR"

# 下载 Xray-core (必须用 Xray, 不是 v2ray-core)
case "$ARCH" in
  x86_64)
    URL="https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip"
    ;;
  aarch64)
    URL="https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-arm64-v8a.zip"
    ;;
  *)
    echo "不支持的架构: $ARCH"; exit 1 ;;
esac

curl -fsSL "$URL" -o /tmp/xray.zip
cd /tmp && unzip -o xray.zip xray -d "$XRAY_DIR/"
chmod +x "$XRAY_DIR/xray"

# 也可以装到系统路径（推荐）
$SUDO cp "$XRAY_DIR/xray" /usr/local/bin/xray
$SUDO chmod +x /usr/local/bin/xray
cd "$PROJECT_DIR"
```

### 4.5 安装 mihomo 内核（兜底）

```bash
MIHOMO_DIR="$PROJECT_DIR/邮箱注册/mihomo_runtime"
mkdir -p "$MIHOMO_DIR"

case "$ARCH" in
  x86_64) URL="https://github.com/MetaCubeX/mihomo/releases/download/v1.19.12/mihomo-linux-amd64-v1.19.12.gz" ;;
  aarch64) URL="https://github.com/MetaCubeX/mihomo/releases/download/v1.19.12/mihomo-linux-arm64-v1.19.12.gz" ;;
esac

curl -fsSL "$URL" -o /tmp/mihomo.gz
gunzip -f /tmp/mihomo.gz
mv /tmp/mihomo "$MIHOMO_DIR/mihomo-linux"
chmod +x "$MIHOMO_DIR/mihomo-linux"
```

### 4.6 配置订阅链接

```bash
# ⚠️ 订阅链接是私密的，不要提交到 git
# 写入订阅配置（支持多个订阅）
$PYTHON -c "
import json
subs = [
    {'url': 'YOUR_SUBSCRIPTION_URL_1', 'name': 'default'},
    # {'url': 'YOUR_SUBSCRIPTION_URL_2', 'name': 'backup'},
]
json.dump(subs, open('$MIHOMO_DIR/subscriptions.json', 'w'), indent=2)
print('订阅已配置:', len(subs), '个')
"

# 确保 .gitignore 已忽略 subscriptions.json
# （仓库 .gitignore 已包含此规则）
```

### 4.7 配置 GitHub 凭证仓库

```bash
CLOUD_DIR="$PROJECT_DIR/云端注册邮箱"

# 方式1: SSH clone（需配置 SSH key）
git clone git@github.com:你的用户名/cloud-register-email.git "$CLOUD_DIR"

# 方式2: HTTPS + Token
GITHUB_TOKEN="ghp_xxxxxxxxxxxx"
git clone "https://${GITHUB_TOKEN}@github.com/你的用户名/cloud-register-email.git" "$CLOUD_DIR"

# 方式3: 跳过（注册功能正常，后续手动配置）
mkdir -p "$CLOUD_DIR"
```

### 4.8 创建运行时目录

```bash
mkdir -p "$PROJECT_DIR/runtime_outlook/logs"
mkdir -p "$PROJECT_DIR/runtime_outlook/rt_tokens"
mkdir -p "$PROJECT_DIR/runtime_outlook/rt_input"
mkdir -p "$PROJECT_DIR/runtime_outlook/fail_dumps"
chmod -R u+rwX,g+rwX "$PROJECT_DIR/runtime_outlook"

# 清除 Python 缓存（避免旧 .pyc 导致修复不生效）
find "$PROJECT_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
```

### 4.9 启动 Xvfb 虚拟显示

```bash
# 清理僵尸锁
rm -f /tmp/.X98-lock /tmp/.X11-unix/X98
# 启动
Xvfb :98 -screen 0 1366x768x24 -ac -nolisten tcp &
sleep 2
export DISPLAY=:98
# 验证
xdpyinfo -display :98 >/dev/null 2>&1 && echo "✅ Xvfb 就绪" || echo "❌ Xvfb 失败"
```

---

## 五、保活配置（按服务器类型）

### 5.1 Zo 服务器

```bash
# Zo 用 register_user_service（不要用 systemd）
# 在 Zo 界面或通过 API 创建服务:
# mode: process
# entrypoint: /path/to/venv/bin/python3 -u outlook_daemon.py
# workdir: /home/workspace/Email-Register
# env_vars: DISPLAY=:98, PYTHONUNBUFFERED=1
```

### 5.2 Gcore / 普通 VPS (systemd)

```bash
USER=$(whoami)
PROJECT_DIR=$(pwd)
PYTHON=$(which python3)  # 或 venv 路径

$SUDO tee /etc/systemd/system/outlook-auto-register.service << EOF
[Unit]
Description=Outlook Auto Register Daemon
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
Environment=DISPLAY=:98
Environment=PYTHONUNBUFFERED=1
ExecStartPre=/bin/bash -c 'rm -f /tmp/.X98-lock /tmp/.X11-unix/X98; Xvfb :98 -screen 0 1366x768x24 -ac -nolisten tcp &'
ExecStart=$PYTHON -u $PROJECT_DIR/outlook_daemon.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

$SUDO systemctl daemon-reload
$SUDO systemctl enable outlook-auto-register
$SUDO systemctl start outlook-auto-register
$SUDO systemctl status outlook-auto-register
```

### 5.3 本地开发 (nohup)

```bash
export DISPLAY=:98
export PYTHONUNBUFFERED=1
nohup python3 -u outlook_daemon.py > /dev/shm/outlook_daemon.log 2>&1 &
```

---

## 六、部署后验证

```bash
PROJECT_DIR=$(pwd)

echo "=== 1. Xvfb ==="
pgrep -f "Xvfb :98" && echo "✅" || echo "❌"

echo "=== 2. daemon 运行中 ==="
pgrep -f "outlook_daemon.py" && echo "✅" || echo "❌"

echo "=== 3. xray 内核 ==="
ss -tlnp | grep -q ":28890" && echo "✅ 28890 监听中" || echo "❌"
curl -s --max-time 10 --proxy http://127.0.0.1:28890 https://ipinfo.io/json | jq -r '.ip // "失败"'

echo "=== 4. 前端面板 ==="
curl -s http://localhost:8765/ | head -3 && echo "✅" || echo "❌"

echo "=== 5. 订阅节点数 ==="
$PYTHON -c "
import sys; sys.path.insert(0, '邮箱注册')
from xray_proxy import get_xray_manager
m = get_xray_manager()
ok, n = m._build_config()
print(f'xray 节点: {n}' if ok else '❌ xray 配置生成失败')
"

echo "=== 6. 手动注册测试 ==="
echo "  cd $PROJECT_DIR"
echo "  $PYTHON outlook_launcher.py run --count 5 --shuffle"
```

---

## 七、日常运维

### 7.1 查看状态

```bash
# daemon 日志
tail -f runtime_outlook/logs/outlook_daemon.log

# 注册日志
tail -f /dev/shm/outlook_launcher.log

# 前端面板
# 浏览器访问 http://服务器IP:8765/

# 注册结果
python3 -c "
import json
lines = open('runtime_outlook/results.jsonl').readlines()
ok = sum(1 for l in lines if l.strip() and json.loads(l).get('success'))
print(f'成功: {ok}/{len([l for l in lines if l.strip()])}')
"
```

### 7.2 手动操作

```bash
# 注册 5 个
python3 outlook_launcher.py run --count 5 --shuffle

# 注册 10 个（2线程并行，谨慎使用）
python3 outlook_launcher.py run --count 10 --workers 2 --shuffle

# 只注册不获取 RT
python3 outlook_launcher.py run --count 5 --no-rt

# 获取 RT
python3 post_register_fetch_rt.py --limit 20 --timeout 120

# 推送凭证到 GitHub
python3 sync_credentials.py --push
```

### 7.3 代理管理

```bash
# xray 状态
python3 邮箱注册/xray_proxy.py status

# xray 节点列表
python3 邮箱注册/xray_proxy.py nodes

# xray 切换节点
python3 邮箱注册/xray_proxy.py switch "节点名"

# xray 重启
python3 邮箱注册/xray_proxy.py restart

# xray 刷新订阅
python3 邮箱注册/xray_proxy.py refresh

# 清除节点黑名单
echo '{}' > runtime_outlook/blocked_nodes.json

# 重置轮循游标
echo '{}' > runtime_outlook/proxy_rotation.json
```

### 7.4 故障恢复

```bash
# daemon 挂了 → supervisor/systemd 自动重启
# 如果没自动重启:
kill $(pgrep -f outlook_daemon.py)  # Zo: supervisor 会拉起
# 或
sudo systemctl restart outlook-auto-register  # VPS

# Chrome 残留导致 OOM
pkill -9 -f 'cdp_outl\|cdp_reg\|outlook.*user-data'
# ⚠️ 不要 pkill -9 chrome（会杀 agent-browser）

# 调度状态残留（跳过注册）
echo '{}' > runtime_outlook/daemon_schedule.json

# 清除 Python 缓存
find . -name __pycache__ -exec rm -rf {} +
```

---

## 八、不同服务器适配要点

### 8.1 Zo 服务器

- 用户: root，无需 sudo
- 保活: `register_user_service` (mode=process)
- 路径: `/home/workspace/Email-Register`
- 特殊: 不能用 systemd，用 supervisor
- 浏览器: 已预装 Google Chrome + Chromium
- 日志: `/dev/shm/` (tmpfs)

### 8.2 Gcore VPS (Ubuntu 22.04)

- 用户: ubuntu，需要 sudo
- 保活: systemd
- 路径: `/home/ubuntu/Email-Register`
- ⚠️ python3-venv 缺失: `sudo apt install python3.13-venv || sudo apt install python3-venv`
- ⚠️ pip 限制: 用 venv 或 `--break-system-packages`
- ⚠️ libasound2 包名: `libasound2t64` 或 `libasound2`
- 内存: 4GB，串行注册，每批最多 5 个
- 磁盘: 14GB，注意日志不要写满

### 8.3 普通 VPS (Debian 12)

- 用户: root 或普通用户
- 保活: systemd
- 路径: `~/Email-Register`
- 基本同 Gcore，包名更标准

### 8.4 本地开发机

- 保活: nohup + 手动管理
- 可直接用系统 Python
- 注意 DISPLAY 环境变量

---

## 九、关键注意事项

### 9.1 内核选型

| 需求 | 内核 | 原因 |
|------|------|------|
| reality 协议节点 | **Xray-core** | v2ray-core 不支持 reality |
| clash 格式订阅 | mihomo | xray 不直接解析 clash YAML |
| 通用兜底 | mihomo | 支持全部 clash 节点类型 |

**本系统**：xray 为主内核（直接抓订阅解析 vless），mihomo 为兜底。

### 9.2 不要做的事

1. ❌ 不要 `pkill -9 chrome`（杀掉 agent-browser）
2. ❌ 不要用 headless 浏览器（Outlook 检测并拦截）
3. ❌ 不要用 v2ray-core（不支持 Reality）
4. ❌ 不要多线程同时 switch_node（互相覆盖）
5. ❌ 不要推送 subscriptions.json / config.yaml / 凭证目录
6. ❌ 不要用 `ClashForAndroid` User-Agent 抓订阅（返回空壳）
7. ❌ 不要忘记清 `__pycache__`（旧缓存导致修复不生效）

### 9.3 必须做的事

1. ✅ Xvfb :98 必须先启动，所有子进程 `export DISPLAY=:98`
2. ✅ 注册后清理 Chrome 孤儿进程
3. ✅ 修改代码后清除 `__pycache__`
4. ✅ account_blocked 后拉黑节点 4h
5. ✅ RT 用新浏览器获取（无登录态）
6. ✅ 订阅 User-Agent 用 `v2rayN/6.0`（不是 ClashForAndroid）
7. ✅ xray routing.rules 设为空数组（走第一个 outbound）

---

*文档版本: v1.0 | 最后更新: 2026-06-26*
