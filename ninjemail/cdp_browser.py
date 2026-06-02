"""
CDP (Chrome DevTools Protocol) Browser Module

Launches a clean Chrome browser without automation flags and connects via CDP.
Uses the browser extension's detection logic for element finding.
Replaces Selenium WebDriver to avoid anti-bot detection.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
import socket
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Chrome Launch Configuration ──
DEFAULT_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
]

# 多浏览器路径配置（均为 Chromium 内核，支持 CDP）
BROWSER_PATHS = {
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    ],
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "brave": [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.expanduser(r"~\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ],
    "chromium": [
        r"C:\Program Files\Chromium\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Chromium\Application\chrome.exe"),
    ],
    "vivaldi": [
        r"C:\Program Files\Vivaldi\Application\vivaldi.exe",
        os.path.expanduser(r"~\AppData\Local\Vivaldi\Application\vivaldi.exe"),
    ],
    "thorium": [
        r"C:\Program Files\Thorium\Application\thorium.exe",
        os.path.expanduser(r"~\AppData\Local\Thorium\Application\thorium.exe"),
    ],
    "opera": [
        r"C:\Program Files\Opera\opera.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Opera\opera.exe"),
        os.path.expanduser(r"~\AppData\Local\Programs\Opera GX\opera.exe"),
    ],
    "ungoogled": [
        r"C:\Program Files\ungoogled-chromium\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\ungoogled-chromium\Application\chrome.exe"),
    ],
    "cent": [
        r"C:\Program Files\CentBrowser\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\CentBrowser\Application\chrome.exe"),
    ],
    "360": [
        r"C:\Program Files (x86)\360\360se\360se.exe",
        r"C:\Program Files\360\360se\360se.exe",
        r"C:\Program Files (x86)\360\360chrome\360chrome.exe",
        r"C:\Program Files\360\360chrome\360chrome.exe",
    ],
    "qq": [
        r"C:\Program Files (x86)\Tencent\QQBrowser\QQBrowser.exe",
        r"C:\Program Files\Tencent\QQBrowser\QQBrowser.exe",
    ],
    "sogou": [
        r"C:\Program Files (x86)\SogouExplorer\SogouExplorer.exe",
        r"C:\Program Files\SogouExplorer\SogouExplorer.exe",
    ],
    "maxthon": [
        r"C:\Program Files\Maxthon\Bin\Maxthon.exe",
        os.path.expanduser(r"~\AppData\Local\Maxthon\Application\Maxthon.exe"),
    ],
    "yandex": [
        r"C:\Program Files (x86)\Yandex\YandexBrowser\Application\browser.exe",
        os.path.expanduser(r"~\AppData\Local\Yandex\YandexBrowser\Application\browser.exe"),
    ],
    "srware": [
        r"C:\Program Files\SRWare Iron\iron.exe",
        os.path.expanduser(r"~\AppData\Local\SRWare Iron\Application\iron.exe"),
    ],
    "slimjet": [
        r"C:\Program Files\Slimjet\slimjet.exe",
        os.path.expanduser(r"~\AppData\Local\Slimjet\Application\slimjet.exe"),
    ],
}

CDP_CHECK_TIMEOUT = 30  # seconds to wait for CDP to be ready
CDP_CHECK_INTERVAL = 0.3


def _find_browser(browser_type: str = "chrome") -> str:
    """Find browser executable path by type. All Chromium-based browsers with CDP support."""
    browser_type = (browser_type or "chrome").strip().lower()
    # 别名映射
    aliases = {
        "google-chrome": "chrome", "googlechrome": "chrome",
        "msedge": "edge", "microsoft-edge": "edge", "microsoftedge": "edge",
        "brave-browser": "brave", "bravebrowser": "brave",
        "opera-gx": "opera", "operagx": "opera",
        "ungoogled-chromium": "ungoogled", "ungoogledchromium": "ungoogled",
        "centbrowser": "cent", "cent-browser": "cent",
        "360se": "360", "360chrome": "360", "360-browser": "360", "360安全浏览器": "360", "360极速浏览器": "360",
        "qqbrowser": "qq", "qq-browser": "qq", "qq浏览器": "qq",
        "sogou-browser": "sogou", "sogoubrowser": "sogou", "搜狗浏览器": "sogou",
        "maxthon-browser": "maxthon", "傲游": "maxthon",
        "yandex-browser": "yandex", "yandexbrowser": "yandex",
        "srware-iron": "srware", "iron": "srware",
        "slimjet-browser": "slimjet",
    }
    browser_type = aliases.get(browser_type, browser_type)

    paths = BROWSER_PATHS.get(browser_type, BROWSER_PATHS["chrome"])
    for path in paths:
        if os.path.isfile(path):
            return path
    # Try PATH
    import shutil
    exe_names = {
        "chrome": ["chrome", "google-chrome"],
        "edge": ["msedge", "microsoft-edge"],
        "brave": ["brave", "brave-browser"],
        "chromium": ["chromium"],
        "vivaldi": ["vivaldi"],
        "thorium": ["thorium"],
        "opera": ["opera"],
        "ungoogled": ["chrome"],
        "cent": ["chrome"],
        "360": ["360se", "360chrome"],
        "qq": ["QQBrowser"],
        "sogou": ["SogouExplorer"],
        "maxthon": ["Maxthon"],
        "yandex": ["browser"],
        "srware": ["iron"],
        "slimjet": ["slimjet"],
    }
    for name in exe_names.get(browser_type, ["chrome"]):
        found = shutil.which(name)
        if found:
            return found
    # 回退到 Chrome
    if browser_type != "chrome":
        logger.warning("[CDP] Browser '%s' not found, falling back to Chrome", browser_type)
        return _find_browser("chrome")
    raise FileNotFoundError(f"Browser '{browser_type}' not found. Install it or set the correct path.")

def _find_chrome() -> str:
    """Find Chrome executable path (legacy compatibility)."""
    return _find_browser("chrome")


def _find_free_port() -> int:
    """Find a free TCP port for CDP."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_cdp(port: int, timeout: float = CDP_CHECK_TIMEOUT) -> dict:
    """Wait for Chrome CDP to be ready and return the WebSocket debug URL."""
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/json/version"
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read())
                ws_url = data.get("webSocketDebuggerUrl", "")
                if ws_url:
                    logger.info("[CDP] Chrome ready, ws=%s", ws_url[:80])
                    return data
        except Exception:
            pass
        time.sleep(CDP_CHECK_INTERVAL)
    raise TimeoutError(f"Chrome CDP not ready after {timeout}s on port {port}")


def _get_page_ws_url(port: int) -> str:
    """Get the WebSocket URL for the first page tab."""
    url = f"http://127.0.0.1:{port}/json"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            tabs = json.loads(resp.read())
            for tab in tabs:
                if tab.get("type") == "page":
                    return tab["webSocketDebuggerUrl"]
    except Exception as e:
        logger.warning("[CDP] Failed to get page WS URL: %s", e)
    return ""


@dataclass
class CDPLaunchConfig:
    """Configuration for launching Chrome/Chromium browser with CDP."""
    chrome_path: str = ""
    browser_type: str = "chrome"  # chrome, edge, brave, chromium, vivaldi, thorium
    debug_port: int = 0
    user_data_dir: str = ""
    proxy: str = ""           # No-auth proxy URL for --proxy-server
    proxy_auth_url: str = ""  # Full proxy URL with credentials for Fetch auth
    headless: bool = False
    window_size: tuple[int, int] = (1280, 900)
    extra_args: list[str] = field(default_factory=list)
    extensions: list[str] = field(default_factory=list)


class CDPBrowser:
    """
    Clean Chrome browser controlled via CDP.
    
    Key differences from Selenium:
    - No automation flags (no --enable-automation, no navigator.webdriver)
    - Uses CDP directly for DOM queries and input dispatch
    - OS-level input for clicks (bypasses JS-level detection)
    - Touch events for CAPTCHA long-press
    """

    def __init__(self, config: CDPLaunchConfig | None = None):
        self.config = config or CDPLaunchConfig()
        self._process: subprocess.Popen | None = None
        self._ws: Any = None
        self._ws_url: str = ""
        self._port: int = 0
        self._msg_id: int = 0
        self._callbacks: dict[int, Any] = {}
        self._events: list[dict] = []
        self._event_handlers: dict[str, list] = {}
        self._listen_thread: Any = None
        self._connected: bool = False
        self._temp_dir: str = ""

    def launch(self) -> "CDPBrowser":
        """Launch Chrome and connect via CDP."""
        chrome_path = self.config.chrome_path or _find_browser(self.config.browser_type)
        self._port = self.config.debug_port or _find_free_port()

        # Create temp user data dir if not specified
        if not self.config.user_data_dir:
            self._temp_dir = tempfile.mkdtemp(prefix="ninjemail_chrome_")
            user_data_dir = self._temp_dir
        else:
            user_data_dir = self.config.user_data_dir

        # ── Resolve proxy: start relay if auth needed ──
        effective_proxy = self.config.proxy  # protocol://host:port (no auth)
        proxy_auth_url = self.config.proxy_auth_url
        if proxy_auth_url:
            try:
                from .proxy_utils import parse_proxy
                proxy_info = parse_proxy(proxy_auth_url)
                if proxy_info and proxy_info.has_auth:
                    relay_port = self._start_proxy_relay(
                        proxy_info.host, proxy_info.port,
                        proxy_info.username, proxy_info.password,
                        proxy_info.protocol
                    )
                    if relay_port:
                        effective_proxy = f"http://127.0.0.1:{relay_port}"
                        self._relay_port = relay_port
                        logger.info("[CDP] Using local relay proxy: %s -> %s:%d", effective_proxy, proxy_info.host, proxy_info.port)
            except Exception as exc:
                logger.warning("[CDP] Failed to start relay, using direct proxy: %s", exc)

        # Build Chrome args - NO automation flags
        args = [
            chrome_path,
            f"--remote-debugging-port={self._port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-default-apps",
            "--disable-popup-blocking",
            "--disable-translate",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-features=TranslateUI",
            "--disable-hang-monitor",
            "--remote-allow-origins=*",
            f"--window-size={self.config.window_size[0]},{self.config.window_size[1]}",
            "--incognito",
            # 关键：禁用 Chrome 内置 DNS，强制用系统 DNS 解析
            # Chrome 内置 DNS 在 SOCKS5 代理下可能卡死
            "--disable-features=BuiltInDnsClient",
        ]

        if self.config.headless:
            args.append("--headless=new")

        if effective_proxy:
            args.append(f"--proxy-server={effective_proxy}")
            # 不设 bypass list，让所有流量走代理（包括 localhost 的 CDP 调试端口也走代理会导致问题）
            # 所以只排除 CDP 调试端口
            args.append(f"--proxy-bypass-list=127.0.0.1:{self._port}")

        # Load extensions (the browser extension for enhanced detection)
        if self.config.extensions:
            ext_paths = ",".join(self.config.extensions)
            args.append(f"--load-extension={ext_paths}")
            args.append("--disable-extensions-except=" + ext_paths)

        args.extend(self.config.extra_args)

        logger.info("[CDP] Launching Chrome on port %d", self._port)
        logger.debug("[CDP] Args: %s", " ".join(args[:10]) + "...")

        self._process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for CDP to be ready
        _wait_for_cdp(self._port)

        # Connect WebSocket
        self._connect_ws()

        # Enable necessary CDP domains
        self._send_cmd("Runtime.enable")
        self._send_cmd("DOM.enable")
        self._send_cmd("Page.enable")

        # Set up proxy auth if proxy has credentials (Fetch domain fallback)
        # Only needed if relay didn't start
        if not getattr(self, '_relay_port', None):
            self._setup_proxy_auth_fallback()

        # Remove webdriver flag via CDP
        self._hide_automation()

        self._connected = True
        logger.info("[CDP] Browser launched and connected")
        return self

    def _connect_ws(self):
        """Connect to Chrome via WebSocket."""
        ws_url = _get_page_ws_url(self._port)
        if not ws_url:
            # If no page tab, create one
            self._send_cmd_via_http("Target.createTarget", {"url": "about:blank"})
            time.sleep(0.5)
            ws_url = _get_page_ws_url(self._port)
        if not ws_url:
            raise RuntimeError("Cannot find Chrome page tab for CDP")

        import websocket
        self._ws = websocket.create_connection(ws_url, timeout=30, ping_interval=20, ping_timeout=10)
        self._ws_url = ws_url
        logger.info("[CDP] WebSocket connected to %s", ws_url[:80])

        # Start listening thread
        import threading
        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listen_thread.start()

    def _listen_loop(self):
        """Background thread to receive CDP messages."""
        while self._ws:
            try:
                msg = self._ws.recv()
                if not msg:
                    continue
                data = json.loads(msg)
                if "id" in data:
                    # Response to a command
                    cb = self._callbacks.pop(data["id"], None)
                    if cb:
                        cb(data)
                elif "method" in data:
                    # Event
                    self._events.append(data)
                    handlers = self._event_handlers.get(data["method"], [])
                    for handler in handlers:
                        try:
                            handler(data)
                        except Exception as e:
                            logger.warning("[CDP] Event handler error: %s", e)
            except Exception as e:
                if self._ws:
                    logger.debug("[CDP] Listen error: %s", e)
                break

    def _send_cmd(self, method: str, params: dict | None = None, timeout: float = 15) -> dict:
        """Send a CDP command and wait for response. Auto-reconnects if WebSocket is closed."""
        import websocket as _ws_mod

        for attempt in range(2):
            self._msg_id += 1
            msg_id = self._msg_id
            msg = {"id": msg_id, "method": method}
            if params:
                msg["params"] = params

            result = {}
            event = __import__("threading").Event()

            def callback(data):
                nonlocal result
                result = data
                event.set()

            self._callbacks[msg_id] = callback

            try:
                self._ws.send(json.dumps(msg))
            except (_ws_mod.WebSocketConnectionClosedException, BrokenPipeError, OSError) as e:
                self._callbacks.pop(msg_id, None)
                if attempt == 0:
                    # First attempt: try to reconnect
                    logger.warning("[CDP] WebSocket closed, attempting reconnect...")
                    try:
                        self._connect_ws()
                        logger.info("[CDP] Reconnected successfully")
                        continue
                    except Exception as re:
                        raise RuntimeError(f"CDP send failed (reconnect also failed): {re}") from e
                raise RuntimeError(f"CDP send failed: {e}") from e
            except Exception as e:
                self._callbacks.pop(msg_id, None)
                raise RuntimeError(f"CDP send failed: {e}") from e

            if not event.wait(timeout):
                self._callbacks.pop(msg_id, None)
                raise TimeoutError(f"CDP command timeout: {method}")

            if "error" in result:
                raise RuntimeError(f"CDP error: {result['error']}")

            return result.get("result", {})

    def _send_cmd_via_http(self, method: str, params: dict | None = None):
        """Send a CDP command via HTTP (for pre-WebSocket commands)."""
        url = f"http://127.0.0.1:{self._port}/json/protocol"
        # Use the browser-level WS
        browser_ws_url = ""
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{self._port}/json/version")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                browser_ws_url = data.get("webSocketDebuggerUrl", "")
        except Exception:
            pass

        if not browser_ws_url:
            return

        import websocket
        ws = websocket.create_connection(browser_ws_url, timeout=10)
        try:
            self._msg_id += 1
            msg = {"id": self._msg_id, "method": method}
            if params:
                msg["params"] = params
            ws.send(json.dumps(msg))
            ws.recv()
        finally:
            ws.close()

    def _setup_proxy_auth_fallback(self):
        """Fallback: Set up proxy auth via CDP Fetch domain (when relay is not available)."""
        proxy_url = self.config.proxy_auth_url or self.config.proxy
        if not proxy_url:
            return
        
        username = ""
        password = ""
        try:
            from .proxy_utils import parse_proxy
            proxy_info = parse_proxy(proxy_url)
            if proxy_info:
                username = proxy_info.username
                password = proxy_info.password
        except Exception:
            pass
        
        if not username:
            return
        
        try:
            self._send_cmd("Fetch.enable", {
                "handleAuthRequests": True
            })
            logger.info("[CDP] Fetch.enable fallback activated for proxy auth (user=%s)", username)
            self._proxy_username = username
            self._proxy_password = password
            self._event_handlers.setdefault("Fetch.authRequired", []).append(
                self._handle_proxy_auth
            )
        except Exception as exc:
            logger.warning("[CDP] Failed to set up Fetch auth fallback: %s", exc)
    
    def _start_proxy_relay(self, upstream_host: str, upstream_port: int,
                           username: str, password: str, protocol: str = "http") -> int | None:
        """Start a local HTTP CONNECT proxy relay.
        
        Returns the local port number, or None if failed.
        The relay handles upstream proxy authentication transparently.
        """
        import socket
        import threading
        import base64
        
        # Find a free port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            local_port = s.getsockname()[1]
        
        auth_b64 = base64.b64encode(f"{username}:{password}".encode()).decode()
        
        def _handle_client(client_sock):
            try:
                request = b""
                while b"\r\n\r\n" not in request:
                    chunk = client_sock.recv(4096)
                    if not chunk:
                        return
                    request += chunk
                
                first_line = request.split(b"\r\n")[0].decode("utf-8", errors="replace")
                
                if not first_line.upper().startswith("CONNECT"):
                    # Plain HTTP request
                    upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    upstream.settimeout(15)
                    try:
                        upstream.connect((upstream_host, upstream_port))
                        modified = request.replace(b"\r\n", f"\r\nProxy-Authorization: Basic {auth_b64}\r\n".encode(), 1)
                        upstream.sendall(modified)
                        while True:
                            data = upstream.recv(8192)
                            if not data:
                                break
                            client_sock.sendall(data)
                    except Exception:
                        pass
                    finally:
                        try: client_sock.close()
                        except: pass
                        try: upstream.close()
                        except: pass
                    return
                
                # CONNECT method
                parts = first_line.split()
                target = parts[1] if len(parts) >= 2 else ""
                host_part, _, port_part = target.rpartition(":")
                target_port = int(port_part) if port_part else 443
                
                upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                upstream.settimeout(15)
                try:
                    upstream.connect((upstream_host, upstream_port))
                    connect_req = (
                        f"CONNECT {target} HTTP/1.1\r\n"
                        f"Host: {target}\r\n"
                        f"Proxy-Authorization: Basic {auth_b64}\r\n"
                        f"\r\n"
                    )
                    upstream.sendall(connect_req.encode())
                    
                    resp = b""
                    while b"\r\n\r\n" not in resp:
                        chunk = upstream.recv(4096)
                        if not chunk:
                            break
                        resp += chunk
                    
                    if b"200" in resp.split(b"\r\n")[0]:
                        client_sock.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                        # Bidirectional relay
                        def _forward(src, dst):
                            try:
                                while True:
                                    data = src.recv(65536)
                                    if not data:
                                        break
                                    dst.sendall(data)
                            except Exception:
                                pass
                            try: src.close()
                            except: pass
                            try: dst.close()
                            except: pass
                        t1 = threading.Thread(target=_forward, args=(client_sock, upstream), daemon=True)
                        t2 = threading.Thread(target=_forward, args=(upstream, client_sock), daemon=True)
                        t1.start()
                        t2.start()
                    else:
                        client_sock.sendall(resp)
                        client_sock.close()
                        upstream.close()
                except Exception as e:
                    logger.warning("[RELAY] Upstream connect failed: %s", e)
                    try: client_sock.sendall(b"HTTP/502 Connection failed\r\n\r\n")
                    except: pass
                    try: client_sock.close()
                    except: pass
                    try: upstream.close()
                    except: pass
            except Exception as e:
                logger.warning("[RELAY] Handler error: %s", e)
                try: client_sock.close()
                except: pass
        
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("127.0.0.1", local_port))
            server.listen(20)
        except Exception as exc:
            server.close()
            raise exc
        
        self._relay_server = server
        
        def _accept_loop():
            while True:
                try:
                    client, addr = server.accept()
                    threading.Thread(target=_handle_client, args=(client,), daemon=True).start()
                except OSError:
                    break
                except Exception as e:
                    logger.warning("[RELAY] Accept error: %s", e)
        
        self._relay_thread = threading.Thread(target=_accept_loop, daemon=True)
        self._relay_thread.start()
        
        return local_port

    def _handle_proxy_auth(self, event):
        """Handle proxy 407 auth challenge via CDP Fetch domain.
        
        IMPORTANT: This runs on the WebSocket listen thread. We must NOT call
        _send_cmd() here because it waits for a response that can only be
        received by the listen thread → deadlock.
        Instead, spawn a separate thread to send the auth response.
        """
        import threading as _thr
        request_id = event.get("params", {}).get("requestId", "")
        username = getattr(self, "_proxy_username", "")
        password = getattr(self, "_proxy_password", "")
        
        def _respond():
            try:
                self._send_cmd("Fetch.continueWithAuth", {
                    "requestId": request_id,
                    "authChallengeResponse": {
                        "response": "ProvideCredentials",
                        "username": username,
                        "password": password,
                    }
                })
                logger.info("[CDP] Proxy auth challenge responded (user=%s)", username)
            except Exception as exc:
                logger.warning("[CDP] Proxy auth handler error: %s", exc)
        
        _thr.Thread(target=_respond, daemon=True).start()

    def _hide_automation(self):
        """Remove automation markers via CDP Runtime.evaluate."""
        js = """
        // Remove webdriver flag
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        
        // Remove chrome automation info
        if (window.chrome) {
            delete window.chrome.csi;
            delete window.chrome.loadTimes;
            delete window.chrome.app;
        }
        
        // Override permissions query
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        
        // Override plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
        
        // Override languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });
        """
        try:
            self._send_cmd("Runtime.evaluate", {"expression": js, "returnByValue": True})
            logger.info("[CDP] Automation markers hidden")
        except Exception as e:
            logger.warning("[CDP] Failed to hide automation: %s", e)

    def navigate(self, url: str, wait_for_load: bool = True, timeout: float = 30):
        """Navigate to a URL."""
        logger.info("[CDP] Navigating to %s", url[:100])
        self._send_cmd("Page.navigate", {"url": url}, timeout=timeout)
        if wait_for_load:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                result = self._send_cmd("Runtime.evaluate", {
                    "expression": "document.readyState",
                    "returnByValue": True
                })
                state = result.get("result", {}).get("value", "")
                if state in ("complete", "interactive"):
                    return
                time.sleep(0.3)
            logger.warning("[CDP] Page load timeout after %ss", timeout)

    def get_url(self) -> str:
        """Get current page URL."""
        result = self._send_cmd("Runtime.evaluate", {
            "expression": "window.location.href",
            "returnByValue": True
        })
        return result.get("result", {}).get("value", "")

    def get_title(self) -> str:
        """Get current page title."""
        result = self._send_cmd("Runtime.evaluate", {
            "expression": "document.title",
            "returnByValue": True
        })
        return result.get("result", {}).get("value", "")

    def evaluate(self, expression: str, return_by_value: bool = True) -> Any:
        """Evaluate JavaScript expression."""
        result = self._send_cmd("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": return_by_value,
            "awaitPromise": True,
        })
        return result.get("result", {}).get("value")

    def query_selector(self, selector: str) -> int | None:
        """Query a single element, return node ID."""
        try:
            doc = self._send_cmd("DOM.getDocument", {"depth": 0})
            node_id = doc["root"]["nodeId"]
            result = self._send_cmd("DOM.querySelector", {
                "nodeId": node_id,
                "selector": selector
            })
            nid = result.get("nodeId", 0)
            return nid if nid > 0 else None
        except Exception:
            return None

    def query_selector_all(self, selector: str) -> list[int]:
        """Query all matching elements, return node IDs."""
        try:
            doc = self._send_cmd("DOM.getDocument", {"depth": 0})
            node_id = doc["root"]["nodeId"]
            result = self._send_cmd("DOM.querySelectorAll", {
                "nodeId": node_id,
                "selector": selector
            })
            return result.get("nodeIds", [])
        except Exception:
            return []

    def get_element_rect(self, node_id: int) -> dict | None:
        """Get element bounding rectangle via CDP."""
        try:
            result = self._send_cmd("DOM.getBoxModel", {"nodeId": node_id})
            model = result.get("model", {})
            content = model.get("content", [])
            if len(content) >= 8:
                # content is [x1,y1, x2,y2, x3,y3, x4,y4]
                xs = [content[i] for i in range(0, 8, 2)]
                ys = [content[i] for i in range(1, 8, 2)]
                return {
                    "x": min(xs),
                    "y": min(ys),
                    "width": max(xs) - min(xs),
                    "height": max(ys) - min(ys),
                    "center_x": (min(xs) + max(xs)) / 2,
                    "center_y": (min(ys) + max(ys)) / 2,
                }
        except Exception:
            pass
        return None

    def get_element_rect_js(self, selector: str) -> dict | None:
        """Get element bounding rect via JS (fallback)."""
        escaped_sel = selector.replace("'", "\\'")
        js = f"""
        (() => {{
            const el = document.querySelector('{escaped_sel}');
            if (!el) return null;
            const rect = el.getBoundingClientRect();
            return {{
                x: rect.x, y: rect.y,
                width: rect.width, height: rect.height,
                center_x: rect.x + rect.width / 2,
                center_y: rect.y + rect.height / 2,
            }};
        }})()
        """
        result = self.evaluate(js)
        return result if isinstance(result, dict) else None

    def is_element_visible(self, node_id: int) -> bool:
        """Check if element is visible."""
        rect = self.get_element_rect(node_id)
        if not rect:
            return False
        return rect["width"] > 0 and rect["height"] > 0

    def click_at(self, x: float, y: float, button: str = "left"):
        """Click at screen coordinates using CDP Input.dispatchMouseEvent."""
        # Mouse pressed
        self._send_cmd("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x, "y": y,
            "button": button,
            "clickCount": 1,
        })
        time.sleep(0.05 + __import__("random").uniform(0, 0.05))
        # Mouse released
        self._send_cmd("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x, "y": y,
            "button": button,
            "clickCount": 1,
        })

    def touch_tap(self, x: float, y: float):
        """Touch tap at coordinates (for CAPTCHA bypass)."""
        self._send_cmd("Input.dispatchTouchEvent", {
            "type": "touchStart",
            "touchPoints": [{"x": x, "y": y}],
        })
        time.sleep(0.08)
        self._send_cmd("Input.dispatchTouchEvent", {
            "type": "touchEnd",
            "touchPoints": [],
        })

    def touch_long_press(self, x: float, y: float, duration: float = 3.5):
        """
        Touch long-press at coordinates.
        This is the key technique for hsprotect CAPTCHA bypass.
        Uses Input.dispatchTouchEvent with touchStart/touchEnd.
        """
        import random
        actual_duration = duration + random.uniform(-0.3, 0.5)
        actual_duration = max(2.0, actual_duration)

        logger.info("[CDP] Touch long-press at (%.0f, %.0f) for %.1fs", x, y, actual_duration)

        # Touch start
        self._send_cmd("Input.dispatchTouchEvent", {
            "type": "touchStart",
            "touchPoints": [{"x": x, "y": y}],
        })

        # Hold for duration
        time.sleep(actual_duration)

        # Touch end
        self._send_cmd("Input.dispatchTouchEvent", {
            "type": "touchEnd",
            "touchPoints": [],
        })

        logger.info("[CDP] Touch long-press completed")

    def touch_drag(self, start_x: float, start_y: float, end_x: float, end_y: float, duration_ms: int = 800):
        """
        Touch drag from (start_x, start_y) to (end_x, end_y).
        Used for slider CAPTCHA. Simulates human-like drag with intermediate steps.
        """
        import random
        steps = random.randint(15, 25)
        logger.info("[CDP] Touch drag (%.0f,%.0f) -> (%.0f,%.0f) in %dms", start_x, start_y, end_x, end_y, duration_ms)

        # Touch start
        self._send_cmd("Input.dispatchTouchEvent", {
            "type": "touchStart",
            "touchPoints": [{"x": start_x, "y": start_y}],
        })
        time.sleep(random.uniform(0.05, 0.15))

        # Move with easing (ease-out: fast start, slow end)
        for i in range(1, steps + 1):
            t = i / steps
            # Ease-out cubic
            eased = 1.0 - (1.0 - t) ** 3
            cx = start_x + (end_x - start_x) * eased
            cy = start_y + (end_y - start_y) * eased
            # Add slight random jitter
            cx += random.uniform(-1.5, 1.5)
            cy += random.uniform(-0.8, 0.8)
            self._send_cmd("Input.dispatchTouchEvent", {
                "type": "touchMove",
                "touchPoints": [{"x": cx, "y": cy}],
            })
            step_delay = duration_ms / steps / 1000.0
            time.sleep(step_delay + random.uniform(-0.005, 0.01))

        # Touch end
        self._send_cmd("Input.dispatchTouchEvent", {
            "type": "touchEnd",
            "touchPoints": [],
        })
        logger.info("[CDP] Touch drag completed")

    def mouse_drag(self, start_x: float, start_y: float, end_x: float, end_y: float, duration_ms: int = 800):
        """
        Mouse drag from (start_x, start_y) to (end_x, end_y).
        Fallback for touch drag.
        """
        import random
        steps = random.randint(15, 25)

        self._send_cmd("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": start_x, "y": start_y,
            "button": "left", "clickCount": 1,
        })
        time.sleep(random.uniform(0.05, 0.1))

        for i in range(1, steps + 1):
            t = i / steps
            eased = 1.0 - (1.0 - t) ** 3
            cx = start_x + (end_x - start_x) * eased + random.uniform(-1, 1)
            cy = start_y + (end_y - start_y) * eased + random.uniform(-0.5, 0.5)
            self._send_cmd("Input.dispatchMouseEvent", {
                "type": "mouseMoved", "x": cx, "y": cy,
            })
            time.sleep(duration_ms / steps / 1000.0)

        self._send_cmd("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": end_x, "y": end_y,
            "button": "left", "clickCount": 1,
        })

    def type_text(self, text: str, delay_ms: int = 80):
        """Type text character by character using CDP Input.dispatchKeyEvent."""
        import random
        for char in text:
            self._send_cmd("Input.dispatchKeyEvent", {
                "type": "keyDown",
                "text": char,
                "key": char,
                "code": f"Key{char.upper()}" if char.isalpha() else "",
                "windowsVirtualKeyCode": ord(char.upper()) if char.isalpha() else 0,
            })
            self._send_cmd("Input.dispatchKeyEvent", {
                "type": "keyUp",
                "key": char,
                "code": f"Key{char.upper()}" if char.isalpha() else "",
            })
            time.sleep(random.uniform(delay_ms * 0.5, delay_ms * 1.5) / 1000)

    def press_key(self, key: str):
        """Press a special key (Enter, Tab, etc.)."""
        key_map = {
            "Enter": {"key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
            "Tab": {"key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9},
            "Escape": {"key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27},
            "Backspace": {"key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8},
        }
        params = key_map.get(key, {"key": key, "code": key})
        self._send_cmd("Input.dispatchKeyEvent", {"type": "keyDown", **params})
        time.sleep(0.05)
        self._send_cmd("Input.dispatchKeyEvent", {"type": "keyUp", **params})

    def focus_element(self, selector: str) -> bool:
        """Focus an element via JS."""
        escaped_sel = selector.replace("'", "\\'")
        js = f"""
        (() => {{
            const el = document.querySelector('{escaped_sel}');
            if (!el) return false;
            el.focus();
            return true;
        }})()
        """
        return bool(self.evaluate(js))

    def set_input_value(self, selector: str, value: str) -> bool:
        """Set input value via JS (without triggering input events that reveal automation)."""
        escaped_sel = selector.replace("'", "\\'")
        escaped_val = value.replace("'", "\\'")
        js = f"""
        (() => {{
            const el = document.querySelector('{escaped_sel}');
            if (!el) return false;
            // Use native setter to bypass React/Vue wrappers
            const nativeSet = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            nativeSet.call(el, '{escaped_val}');
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return true;
        }})()
        """
        return bool(self.evaluate(js))

    def get_body_text(self) -> str:
        """Get visible body text."""
        return str(self.evaluate("document.body ? document.body.innerText : ''") or "")

    def get_page_html(self) -> str:
        """Get page HTML."""
        return str(self.evaluate("document.documentElement.outerHTML") or "")

    def wait_for_element(self, selector: str, timeout: float = 15) -> bool:
        """Wait for element to appear."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            nid = self.query_selector(selector)
            if nid and self.is_element_visible(nid):
                return True
            time.sleep(0.3)
        return False

    def wait_for_text(self, text: str, timeout: float = 15) -> bool:
        """Wait for text to appear in page body."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            body = self.get_body_text().lower()
            if text.lower() in body:
                return True
            time.sleep(0.3)
        return False

    def screenshot(self, path: str = "") -> str:
        """Take a screenshot, return base64 or save to path."""
        result = self._send_cmd("Page.captureScreenshot", {"format": "png"})
        import base64
        data = base64.b64decode(result.get("data", ""))
        if path:
            Path(path).write_bytes(data)
            return path
        return base64.b64encode(data).decode()

    def close(self):
        """Close the browser."""
        self._connected = False
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass
        try:
            if self._process:
                self._process.terminate()
                self._process.wait(timeout=5)
        except Exception:
            try:
                if self._process:
                    self._process.kill()
            except Exception:
                pass
        # Clean up relay server
        if hasattr(self, '_relay_server') and self._relay_server:
            try:
                self._relay_server.close()
            except Exception:
                pass
        if self._temp_dir:
            try:
                import shutil
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            except Exception:
                pass
        logger.info("[CDP] Browser closed")

    def __enter__(self):
        return self.launch()

    def __exit__(self, *args):
        self.close()

    @property
    def current_url(self) -> str:
        return self.get_url()

    @property
    def title(self) -> str:
        return self.get_title()
