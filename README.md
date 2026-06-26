<p align="center">   <img src="logo/logo.png" alt="邮箱注册 logo"/> </p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11-blue.svg?style=flat-square" alt="Python Badge">
  <img src="https://img.shields.io/badge/code%20style-pep8-orange.svg?style=flat-square" alt="PEP8 Badge">
  <img src="https://hits.dwyl.com/xingluoyuankong/email-register.svg?style=flat-square&show=unique&color=blue" alt="HitCount Badge">
  <img src="https://img.shields.io/github/license/xingluoyuankong/email-register?style=flat-square" alt="GitHub License Badge">
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square&color=purple" alt="PRs Welcome Badge">
  <img src="https://img.shields.io/github/actions/workflow/status/xingluoyuankong/email-register/ci.yml?style=flat-square&label=tests" alt="Test status">
  <img src="https://img.shields.io/codecov/c/github/xingluoyuankong/email-register?style=flat-square" alt="Test coverage Badge">
</p>

------

邮箱注册 is a Python library designed to streamline the process of creating email accounts across various top email provider services. With 邮箱注册, you can automate the creation of email accounts, saving time and effort. It provides an easy-to-use interface for creating accounts with customizable options.

## Features

- **Automated Account Creation:** 邮箱注册 streamlines the process of creating email accounts by automating the necessary steps.
- **Support for Major Email Providers:** 邮箱注册 supports a wide range of popular email service providers including Gmail, Outlook and Yahoo, giving you flexibility in choosing the provider that suits your needs.
- **Python Integration:** 邮箱注册 seamlessly integrates into Python projects, allowing for efficient automation of email account creation.
- **Auto-generated Account Details:** Generate random account details for username, password, first name, last name, country, and birthdate if not provided, allowing for quick creation of multiple accounts for testing or other purposes.
- **Customizable Options:** Customize account details such as username, password, first name, last name, country, and birthdate to meet your specific requirements.
- **Error Handling and Logging:** 邮箱注册 provides error handling capabilities and logs activities to facilitate debugging and tracking of account creation actions.
- **Open-Source and Extensible:** Being an open-source project, 邮箱注册 encourages contributions and allows for further extension and improvement of its functionalities.
- **Proxy Support:** 邮箱注册 includes proxy support, giving users the option to use their own proxies for account creation, including support for authenticated proxies. This feature allows for enhanced privacy, security, and flexibility during the email account creation process.
- **Free Proxy Option:** Additionally, 邮箱注册 offers an option to automatically retrieve and use free proxies. This feature provides users with a convenient solution for proxy usage, eliminating the need for purchasing or configuring proxies separately.

## Installation

To install 邮箱注册, you can follow these steps:

1. Clone the 邮箱注册 repository from GitHub using the following command:

   Copy

   ```bash
   git clone https://github.com/xingluoyuankong/email-register.git
   ```

2. Change your current directory to the cloned repository:

   Copy

   ```bash
   cd 邮箱注册
   ```

3. Install the required dependencies using pip:

   ```bash
   pip install -r requirements.txt
   ```

You can then proceed to use 邮箱注册 as described in the next instructions.

## Testing

To ensure the reliability and correctness of this project, tests have been implemented using [pytest](https://pytest.org/). The test suite covers various aspects of the codebase and helps maintain the desired functionality as the project evolves.

### Running Tests

1. Make sure you have the project's dependencies installed.

2. Navigate to the project's root directory.

3. Run the following command to execute the test suite:

   ```bash
   pytest
   ```

### Test Coverage

Comprehensive test coverage is prioritized to minimize bugs and regressions. The current code coverage can be measured using pytest-cov. To generate a coverage report, users can execute the following command:

```bash
pytest --cov
```

The coverage report will be displayed in the terminal.

### Writing Tests

When adding new features or fixing bugs, it's important to include corresponding test cases to validate the changes. Tests should be placed in the `tests/` directory, following a naming convention such as `test_module.py` or `test_class.py`. You can organize the tests based on the project's structure.

## Usage

### Importing the Library

To use 邮箱注册 in your Python script, import the `邮箱注册` class from the `邮箱注册` module:

```python
from 邮箱注册 import 邮箱注册
```

### Initializing 邮箱注册

To create an instance of 邮箱注册, call the `邮箱注册` class with optional parameters:

```python
ninja = 邮箱注册(
    	browser="firefox", 
    	captcha_keys={"capsolver": "YOUR_API_KEY", "nopecha": "YOUR_API_KEY"}, 
    	sms_keys={"service_name": {"user": "USERNAME", "token": "TOKEN"}},
    	proxies=['http://ip:port', 'http://ip2:port2'],
    	auto_proxy=True
)
```

The `browser` parameter specifies the browser to be used for automation. The default value is "firefox". Currently, 邮箱注册 supports **Firefox, Chrome and Undetected Chrome**. The acceptable values for the browser parameter are `firefox`, `chrome` and `undetected-chrome` respectively.

The `captcha_keys` parameter is a dictionary that contains the **API keys for supported captcha solving services**, based on `config.toml`. The default value is an empty dictionary. You can provide API keys for specific captcha solving services if required. Currently, the following services are supported:

- **"capsolver"**
- **"nopecha"**

To provide the API keys for these services, you can pass a dictionary to the `captcha_keys` parameter. Each key-value pair in the dictionary corresponds to a captcha solving service and its respective API key as shown in the example above.

The `sms_keys` parameter is a dictionary that contains the **API key/s for the SMS service/s**, based on `config.toml`. The default value is an empty dictionary. You can provide an API key or keys for the SMS services if required. Currently, **"getsmscode"**, **"smspool"** and **"5sim"** are supported.

The `proxies` parameter specifies the list of proxy servers to be used for the creation of email accounts. Is optional and can accept either a single proxy server or multiple proxy servers in a list. Each proxy should be provided as a string in the format "http://ip:port," where "ip" represents the IP address of the proxy server and "port" represents the port number. Additionally, support for authentication proxies is available, but exclusively for chrome and undetected-chrome for the moment. The format for authentication proxies remains the same: "http://username:password@ip:port".

The `auto_proxy` parameter is a boolean flag that determines whether 邮箱注册 should automatically obtain and rotate free proxies during automation tasks. If `auto_proxy` is set to `True`, 邮箱注册 will handle the process of acquiring and managing free proxies internally.

Please note that when `auto_proxy` is enabled, 邮箱注册 will handle the management of proxies, but the availability and reliability of free proxies may vary. It's important to consider the limitations and potential risks associated with using free proxy services.

### Creating Outlook Accounts

To create an Outlook/Hotmail account using 邮箱注册, call the `create_outlook_account` method:

```python
ninja.create_outlook_account(
    		username="", 
    		password="", 
    		first_name="", 
    		last_name="", 
    		country="", 
    		birthdate="", 
    		hotmail=False,
    		use_proxy=True
)
```

The `username` parameter is the desired username for the Outlook account. If not provided, a random username will be generated.

The `password` parameter is the desired password for the Outlook account. If not provided, a random password will be generated.

The `first_name` parameter is the first name of the account holder. If not provided, a random first name will be generated.

The `last_name` parameter is the last name of the account holder. If not provided, a random last name will be generated.

The `country` parameter is the country of residence for the account holder. If not provided, a random country will be selected.

The `birthdate` parameter is the birthdate of the account holder in the format "MM-DD-YYYY". If not provided, a random birthdate will be generated.

The `hotmail` parameter is a boolean flag indicating whether to create a Hotmail account. The default value is False (i.e., creates an Outlook account).

The `use_proxy` parameter determines whether to use a proxy for the process of creating an Outlook account. If `use_proxy` is set to `True`, a proxy will be utilized during the account creation process. Default is `True`.

The method returns the email and password of the created account.

### Creating Gmail Accounts

To create a Gmail account using 邮箱注册, call the `create_gmail_account` method:

```python
ninja.create_gmail_account(
    		username="", 
    		password="", 
    		first_name="", 
    		last_name="", 
    		birthdate="",
    		use_proxy=True
)
```

The parameters are the same as for creating an Outlook account, except there is no `country` parameter.

The method returns the email and password of the created gmail account.

### Creating Yahoo Accounts

To create a Yahoo account using 邮箱注册, call the `create_yahoo_account` method:

```python
ninja.create_yahoo_account(
    		username="", 
    		password="", 
    		first_name="", 
    		last_name="", 
    		birthdate="",
    		use_proxy=True
)
```

The parameters are the same as for creating an Outlook account, except there is no 'country' parameter. 

The method returns the email and password of the created account.

### Logging

邮箱注册 logs its activities to a file named `邮箱注册.log` in the `logs` directory. The log file has a format of `[timestamp] [log_level]: log_message`. The log levels are: DEBUG, INFO, WARNING, ERROR, and CRITICAL.

## Example

Here's an example that shows how to use 邮箱注册 to create an Outlook account with `undetected-chrome`:

```python
from 邮箱注册 import 邮箱注册

# Replace "YOUR_API_KEY", "USERNAME" and "TOKEN" with your actual keys
ninja = 邮箱注册(
    		browser="undetected-chrome",
    		captcha_keys={"capsolver": "YOUR_API_KEY"},
    		sms_keys={"getsmscode": {"user": "USERNAME", "token": "TOKEN"}},
			auto_proxy=True)
email, password = ninja.create_outlook_account(
    					username="testuser", 
    					password="testpassword", 
    					first_name="John", 
    					last_name="Doe", 
    					country="USA", 
    					birthdate="01-01-1990"
)

print(f"Email: {email}")
print(f"Password: {password}")
```

This will create an Outlook account with the provided information and print the email and password of the created account.

Here's an example that demonstrates how to use 邮箱注册 to create a Yahoo account without providing any user information. 邮箱注册 will generate all the necessary data for you, including name, birthdate, etc. This example utilizes smspool as the SMS service, chrome as the web browser and an authenticated proxy:

```python
from 邮箱注册 import 邮箱注册

# Replace "YOUR_API_KEY" and "TOKEN" with your actual API keys
ninja = 邮箱注册(
    	    browser="chrome",
    		captcha_keys={"nopecha": "YOUR_API_KEY"},
    		sms_keys={"smspool": {"token": "TOKEN"}},
			proxies=['http://username:password@ip_address:port'])
email, password = ninja.create_yahoo_account(
    					use_proxy=False
)

print(f"Email: {email}")
print(f"Password: {password}")
```

This will create a Yahoo account with auto-generated information and will print the email and password of the created account.

## Supported Providers

邮箱注册 currently supports account creation for the following email providers:

- Gmail
- Outlook/Hotmail
- Yahoo
- and more to come!

## Supported SMS Services

邮箱注册 currently supports three SMS services providers for phone verification during account creation:

**getsmscode.com**

**Required Data:**

To use getsmscode.com with 邮箱注册, you'll need to acquire the following information:

- **Username:** Your getsmscode.com username.
- **Token:** Your API token from getsmscode.com.

**Using getsmscode.com with 邮箱注册:**

1. Include the `sms_keys` argument when initializing the 邮箱注册 object:

   ```python
   ninja = 邮箱注册(sms_keys={"getsmscode": {"user": "YOUR_USERNAME", 
                              		"token": "YOUR_TOKEN"}})
   ```
   
   Replace `YOUR_USERNAME` with your getsmscode.com username and `YOUR_TOKEN` with your API token.

**[smspool.net](https://smspool.net/?refferal=aumBFOq90I)**

**Required Data:**

To use smspool with 邮箱注册, you'll need to acquire the following information:

- **Token:** Your API token from smspool.

**Using smspool.net with 邮箱注册:**

1. Include the `sms_keys` argument when initializing the 邮箱注册 object:

   ```python
   ninja = 邮箱注册(sms_keys={"smspool": {"token": "YOUR_TOKEN"}})
   ```

   Replace `token` with your smspool API key.

**[5sim](https://5sim.net/)**

**Required Data:**

To use 5sim with 邮箱注册, you'll need to acquire the following information:

- **Token:** Your API token from 5sim.

**Using 5sim with 邮箱注册:**

1. Include the `sms_keys` argument when initializing the 邮箱注册 object:

   ```python
   ninja = 邮箱注册(sms_keys={"5sim": {"token": "YOUR_TOKEN"}})
   ```

   Replace `token` with your 5sim API key.

## Contribution

Contributions are welcome! If you have ideas for new features, encounter issues, or want to improve 邮箱注册, feel free to contribute by opening issues and pull requests.

## Community

Join the 邮箱注册 community to connect with other users, ask questions, and get support. We have a Telegram group where you can actively participate in discussions related to the library.

- Telegram Group: Join the 邮箱注册 Community on Telegram [here](https://t.me/邮箱注册).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

If you find this project helpful and would like to show your support, here are a couple of things you can do:

- **Star the Project**: If you find the project useful, consider giving it a star. It helps to raise awareness of the project and encourages further development.

- **Financial Support**: Sustaining this project entails ongoing costs for essential services. If you find value in its offerings and wish to bolster its development and upkeep, your financial contribution is invaluable. You can support the project's progression through the [Support-My-Work page](https://david96182.github.io/support-my-work/).

  This project relies on various paid services that furnish APIs. To utilize the project, each user must employ their own API keys. As the project's steward, I'm tasked with maintaining sufficient balances across these services for ongoing development and enhancement. Your support is pivotal in this endeavor.

Your support is greatly appreciated and helps to ensure the continued improvement and availability of this project. 

## 浏览器实例管理与注意事项

### 幽灵浏览器清理

注册流程使用的 Chrome/Chromium 浏览器实例会在注册完成、RT 提取完成后自动清理。但以下情况可能导致幽灵浏览器残留：

- Chrome 崩溃导致 `_process` 引用丢失，主进程被杀但子进程存活
- 注册流程异常中断（OOM、超时、外部 kill）
- Playwright 启动的浏览器在异常退出时未被回收

### 自动清理机制

系统在以下节点自动清理孤儿浏览器：

1. **每次注册完成后** — `run_once()` 结束后调用 `kill_orphan_chrome_processes()`
2. **每批次完成后** — `run_batch()` 循环结束后调用
3. **守护程序注册批次后** — `outlook_daemon.py` 在注册和 RT 提取后分别清理
4. **RT 提取完成后** — `post_register_fetch_rt.py` 和 `batch_rt.py` 清理 Playwright 实例
5. **CDPBrowser.close()** — 使用 `os.killpg()` 杀整个进程组，`pkill` 兜底

### 手动清理

```bash
# 清理所有 Outlook 注册相关的幽灵 Chrome 进程（不影响 agent-browser）
python3 -c "from 邮箱注册.cdp_outlook import kill_orphan_chrome_processes; kill_orphan_chrome_processes()"
```

### ⚠️ 注意事项

- **不要用 `pkill -9 chrome`** — 这会杀掉所有 Chrome 进程，包括 Zo 的 agent-browser
- 清理函数只匹配 `outlook.*user-data|cdp_outl|cdp_reg|outlook_reg` 模式，不会误杀其他浏览器
- Modal 沙盒内存有限（通常 4GB），如果幽灵浏览器堆积会导致 OOM 循环
- 建议每台节点的守护程序配置中加入定期清理（已内置在 daemon 流程中）

## 自动化运维部署

---

## 🔑 关键注意事项（必读）

> 本章节记录了实际部署运行中踩过的坑和关键注意事项。部署前务必完整阅读。

### 1. 敏感文件保护（Git 安全）

**绝对不要推送到 Git 的内容：**

| 文件/目录 | 敏感内容 | 已加入 .gitignore |
|-----------|----------|-------------------|
| `邮箱注册/mihomo_runtime/` | 节点服务器 IP/UUID/Reality 密钥 + 订阅链接 | ✅ |
| `邮箱注册/mihomo_runtime/subscriptions.json` | 订阅 URL（含 token） | ✅ |
| `邮箱注册/mihomo_runtime/config.yaml` | clash 节点配置（含服务器+密码） | ✅ |
| `邮箱注册/mihomo_runtime/providers/sub_*.yaml` | 各订阅节点列表 | ✅ |
| `邮箱注册/mihomo_runtime/residential_proxies.json` | 住宅代理密钥 | ✅ |
| `runtime_outlook/` | 注册结果（邮箱+密码+RT）+ 日志 + 截图 | ✅ |
| `云端注册邮箱/` | GitHub 凭证仓库（三凭证/四凭证） | ✅ |
| `实验优化版本/` | 旧版实验代码 + mihomo_runtime | ✅ |
| `自动化定时注册Outlook邮箱/` | 历史凭证 | ✅ |
| `runtime_subscriptions.json` | 运行时订阅缓存 | ✅ |
| `vostuo_accounts.json` | 账号信息 | ✅ |
| `runtime_nodes_cache.json` | 节点缓存（含 IP） | ✅ |
| `*.pem` `*.key` `.env` | 密钥/环境变量 | ✅ |

**历史已清理：** 使用 `git filter-repo` 已从所有历史提交中移除上述敏感文件。如需重新清理：

```bash
pip install git-filter-repo
git filter-repo --force --invert-paths \
  --path 邮箱注册/mihomo_runtime \
  --path 云端注册邮箱 \
  --path 实验优化版本 \
  --path 自动化定时注册Outlook邮箱 \
  --path runtime_subscriptions.json \
  --path vostuo_accounts.json
git remote add origin https://github.com/xxx/outlook-auto-register.git
git push --force origin main
```

### 2. 双代理内核架构

系统支持两个代理内核并行运行，端口互不冲突：

| 内核 | 端口 | 协议支持 | 用途 |
|------|------|----------|------|
| **Xray-core** | socks `28889` / http `28890` | VLESS + Reality + XTLS | **主内核**（注册轮循用） |
| **mihomo (Clash.Meta)** | mixed `28888` / api `29090` | Clash 全协议 | 兜底内核 |
| 独立 xray VPN | `443` | VLESS | 用户独立 VPN，**不要触碰** |

**端口冲突排查：** 如果注册失败提示 "端口被占用"：
```bash
ss -tlnp | grep -E '28888|28889|28890'
# 杀残留进程（只杀注册相关的，不碰 VPN）
pkill -f 'mihomo-linux.*邮箱注册' 2>/dev/null
pkill -f 'xray.*xray_runtime' 2>/dev/null
```

### 3. 代理节点轮循机制

**轮循策略：按节点轮循（不是按 IP 去重）**

- 每次注册自动切换到下一个可用节点
- 遍历全部节点后才算一轮，之后重新开始
- `account_blocked` 时将该**节点**拉黑 4 小时（不是 IP）
- 台湾/日本节点优先排序（成功率最高）
- 状态持久化在 `runtime_outlook/proxy_rotation.json`

**⚠️ 并行模式注意：**
- 2 线程并行时，同一节点会被多个注册共享
- 如果一个线程 blocked，会拉黑该节点 → 另一线程也会受影响
- **建议串行模式（workers=1）**，成功率更高
- 并行模式适合"快速过一遍所有节点"的场景

### 4. RT（Refresh Token）获取

**两种获取路径：**

1. **注册后同浏览器获取**（注册成功后直接在当前浏览器走 OAuth 授权流程）
   - 优点：复用浏览器会话，速度快
   - 风险：注册成功后跳转到 OAuth 授权页可能卡在"unknown"状态

2. **新浏览器批量获取**（`batch_rt.py`，用 Playwright 全新实例）
   - 优点：干净环境，不受注册会话干扰
   - 用法：`post_register_fetch_rt.py --limit 10 --timeout 90`
   - 每个账号开一个全新 Chrome，带 `login_hint` 直接到密码页

**关键：** 新浏览器不需要登录态——它通过 OAuth `device-code` 或 `authorization-code` flow 重新登录获取 RT，与注册时的浏览器会话无关。

**batch_rt.py 核心流程：**
```
1. 构造 OAuth URL（含 PKCE + login_hint=email + prompt=login）
2. Playwright 开新 Chrome → goto OAuth URL
3. 自动填邮箱密码（login_hint 已预填邮箱）
4. 处理 consent 授权页（自动点 Accept）
5. 等待 localhost 回调拿到 authorization code
6. 用 code 换 token → 保存 refresh_token
```

### 5. 常见失败原因与排查

| 现象 | 根因 | 解决 |
|------|------|------|
| `account_blocked` | Outlook 检测到自动化注册 | 换节点（已自动拉黑当前节点 4h） |
| `unknown` 死循环 | 注册成功后跳转 OAuth 页，页面检测器不认识 | 快速检测 OAuth URL → 触发新浏览器获取 RT |
| RT 获取超时 | 账号选择页卡住 / 密码错误 / consent 页没点 | 新浏览器重试（batch_rt.py 已内置重试） |
| Chrome OOM (exit 137) | 内存不足，多个 Chrome 实例堆积 | 串行注册 + 每次 `kill_orphan_chrome_processes()` |
| 代理 SSL 失败 | 节点不稳定 / 订阅过期 | `ensure_mihomo_proxy.sh` 自动重新拉订阅 |
| mihomo 端口 28888 不通 | 进程崩溃但端口锁残留 | 重启 mihomo（`subscription_proxy.py` 的 `start()`） |

### 6. Xvfb 虚拟显示

- 注册必须用**可视实体浏览器**（非 headless），Outlook 会检测 headless 并拦截
- Xvfb `:98` 提供虚拟显示，所有 Chrome 子进程必须 `export DISPLAY=:98`
- **僵尸锁文件：** Xvfb 进程死后 `/tmp/.X98-lock` 仍残留 → 新 Xvfb 起不来
  ```bash
  rm -f /tmp/.X98-lock /tmp/.X11-unix/X98
  Xvfb :98 -screen 0 1366x768x24 -ac -nolisten tcp &
  ```

### 7. 凭证管理

**三凭证 → 四凭证升级：**
- 注册成功 = 三凭证（`email----password----client_id`）
- RT 获取成功 = 四凭证（`email----password----client_id----refresh_token`）
- `sync_credentials.py` 自动同步到 GitHub 私有仓库 `cloud-register-email`
- 每天 00:00 自动推送，每轮注册后也会推送

### 8. 守护进程保活

- Zo 服务器：用 `register_user_service` + supervisor 自动重启
- VPS/Gcore：用 systemd 服务
- 守护进程每 4 小时注册一批（默认 5 个），串行执行
- **调度状态残留坑：** 注册失败后 `daemon_schedule.json` 残留时间戳 → 重置：
  ```bash
  echo "{}" > runtime_outlook/daemon_schedule.json
  ```

### 9. `__pycache__` 缓存陷阱

修改 Python 代码后，`__pycache__` 中的旧 `.pyc` 可能导致修复不生效：

```bash
find 邮箱注册 -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
```

**每次修改代码后务必清理缓存再重新运行。**

### 10. 部署前置检查清单

```bash
# 1. 内存 ≥ 3GB 可用
free -m

# 2. 磁盘 ≥ 3GB 可用
df -h /

# 3. Xvfb 运行中
pgrep -f "Xvfb :98"

# 4. 代理内核运行中
ss -tlnp | grep -E '28889|28890'  # xray
ss -tlnp | grep 28888             # mihomo

# 5. 代理出口可用
curl -s --max-time 10 --proxy http://127.0.0.1:28890 https://ipinfo.io/json

# 6. 无幽灵 Chrome
pgrep -af 'google-chrome.*outlook' | grep -v agent-browser

# 7. Python 缓存已清
find 邮箱注册 -name "__pycache__" -type d | wc -l  # 应为 0
```

---

## 📚 相关文档

- [部署指南](DEPLOY_GUIDE.md) — 详细的一键部署步骤（支持 Zo/VPS/Gcore）
- [优化记录](OPTIMIZATION_LOG.md) — 历次优化要点与变更记录
- [根因分析](ROOT_CAUSE_ANALYSIS.md) — 注册失败的根本原因分析
- [运维笔记](OPERATIONS.md) — 日常运维操作手册
