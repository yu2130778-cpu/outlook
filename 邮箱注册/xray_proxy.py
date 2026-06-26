#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Xray 内核代理管理器 (v2ray 系内核)

将 mihomo 订阅中的 vless 节点转换为 Xray-core 配置，提供本地代理入站，
供 Outlook 注册机使用。与 mihomo 内核并存，统一纳入 outlook_daemon 保活范围。

内核选择说明:
  - Clash 系内核 = mihomo (MetaCubeX)
  - V2Ray 系内核 = Xray-core (XTLS/Xray-core)，是 v2ray-core 的超集，
    原生支持 VLESS / XTLS / Reality 协议 (v2ray-core 不支持 Reality)。
    本系统订阅节点大量使用 Reality + xtls-rprx-vision，故选用 Xray-core。

端口规划 (避开冲突):
  - mihomo:        mixed 28888 / api 29090
  - 现有 xray-vless 服务: 443 (用户独立 VPN，本管理器绝不触碰)
  - 本 xray 内核:  socks 28889 / http 28890

节点来源: 复用 mihomo_runtime/config.yaml 中已解析的 clash proxies (vless)，
避免重复拉取订阅，格式统一。
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ─── 常量 ───
HERE = Path(__file__).resolve().parent
XRAY_DIR = HERE / "xray_runtime"
XRAY_CONFIG = XRAY_DIR / "config.json"
XRAY_PID_FILE = XRAY_DIR / "xray.pid"
XRAY_LOG_FILE = XRAY_DIR / "xray.log"

# 复用 mihomo 已解析的 clash 配置（节点来源）
MIHOMO_CONFIG = HERE / "mihomo_runtime" / "config.yaml"

SOCKS_PORT = 28889
HTTP_PORT = 28890
PROXY_URL_HTTP = f"http://127.0.0.1:{HTTP_PORT}"
PROXY_URL_SOCKS = f"socks5://127.0.0.1:{SOCKS_PORT}"

# 订阅源（与 mihomo 共享同一份 subscriptions.json）
SUBS_FILE = HERE / "mihomo_runtime" / "subscriptions.json"
# xray 自有节点状态文件（持久化节点列表 + 当前选中节点，供面板读取）
XRAY_NODES_FILE = XRAY_DIR / "nodes.json"
XRAY_CURRENT_FILE = XRAY_DIR / "current_node.txt"


def _find_xray_bin() -> str:
    """定位 xray 二进制；优先 /usr/local/bin/xray。"""
    for p in ("/usr/local/bin/xray", "/usr/bin/xray"):
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    # 兜底：PATH 查找
    for d in os.environ.get("PATH", "").split(os.pathsep):
        cand = os.path.join(d, "xray")
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return "xray"


XRAY_BIN = _find_xray_bin()


def _check_port(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def _kill_our_xray() -> None:
    """精确杀掉本管理器启动的 xray 进程。

    通过 /proc 匹配命令行包含 'xray_runtime' 的进程，绝不触碰
    /etc/xray/vless.json (用户的独立 xray-vless 服务)。
    """
    killed = []
    for pid_s in os.listdir("/proc"):
        if not pid_s.isdigit():
            continue
        try:
            raw = open(f"/proc/{pid_s}/cmdline", "rb").read()
        except Exception:
            continue
        cmd = raw.replace(b"\x00", b" ").decode("utf-8", "replace")
        if "xray" in cmd and ("xray_runtime" in cmd or str(XRAY_CONFIG) in cmd):
            try:
                os.kill(int(pid_s), 15)  # SIGTERM
                killed.append(pid_s)
            except Exception:
                pass
    if killed:
        logger.info("[xray] 终止旧内核进程: %s", ", ".join(killed))
    time.sleep(0.5)


def _parse_vless_uri(uri: str) -> Optional[dict]:
    """解析 vless://uuid@server:port?params#name 链接 → clash 格式 proxy dict。
    用于 base64 编码的订阅（非 clash YAML 格式）。
    """
    try:
        from urllib.parse import urlparse, parse_qs, unquote
        if not uri.startswith("vless://"):
            return None
        # vless://uuid@host:port?query#name
        body = uri[len("vless://"):]
        frag = ""
        if "#" in body:
            body, frag = body.split("#", 1)
        name = unquote(frag) if frag else ""
        cred, _, hostport = body.partition("@")
        uuid = cred.strip()
        host, _, port = hostport.partition(":")
        if not (host and port and uuid):
            return None
        qs = parse_qs(body.split("?", 1)[1]) if "?" in body else {}
        q = {k: v[0] for k, v in qs.items()}
        proxy = {
            "type": "vless",
            "name": name or f"{host}:{port}",
            "server": host,
            "port": int(port),
            "uuid": uuid,
            "network": q.get("type") or "tcp",
            "flow": q.get("flow", ""),
            "tls": q.get("security") in ("tls", "reality"),
            "servername": q.get("sni") or q.get("servername") or host,
            "client-fingerprint": q.get("fp", "chrome"),
        }
        if q.get("security") == "reality":
            proxy["reality-opts"] = {
                "public-key": q.get("pbk", ""),
                "short-id": q.get("sid", ""),
            }
        if q.get("type") == "ws":
            proxy["network"] = "ws"
            proxy["ws-opts"] = {"path": q.get("path", "/"), "headers": {}}
        elif q.get("type") == "grpc":
            proxy["network"] = "grpc"
            proxy["grpc-opts"] = {"grpc-service-name": q.get("serviceName", "")}
        return proxy
    except Exception:
        return None


def _fetch_subscription_proxies() -> tuple[list[dict], int]:
    """直接抓取所有订阅链接，返回 clash 格式 vless proxy dict 列表 + 订阅数。
    支持 clash YAML 格式（UA=clash-verge）和 base64 vless:// 格式（UA=v2rayN）。
    """
    import base64
    try:
        import yaml
    except Exception:
        yaml = None

    if not SUBS_FILE.exists():
        return [], 0
    try:
        subs = json.loads(SUBS_FILE.read_text(encoding="utf-8"))
    except Exception:
        subs = []
    if not isinstance(subs, list):
        return [], 0

    proxies: list[dict] = []
    seen_uuid_host: set[str] = set()
    sub_count = 0
    for s in subs:
        url = s.get("url") if isinstance(s, dict) else None
        if not url:
            continue
        sub_count += 1
        text = ""
        # 优先 clash YAML 格式
        for ua in ("clash-verge/1.5", "v2rayN/6.0"):
            try:
                r = requests.get(url, timeout=15, headers={"User-Agent": ua})
                if r.status_code == 200 and r.text.strip():
                    text = r.text
                    break
            except Exception:
                continue
        if not text:
            continue
        # 尝试 clash YAML 解析
        got = False
        if yaml and ("proxies" in text or "mixed-port" in text):
            try:
                cfg = yaml.safe_load(text)
                if isinstance(cfg, dict) and isinstance(cfg.get("proxies"), list):
                    for p in cfg["proxies"]:
                        if p.get("type") == "vless":
                            key = f"{p.get('uuid','')}@{p.get('server','')}:{p.get('port','')}"
                            if key not in seen_uuid_host:
                                seen_uuid_host.add(key)
                                proxies.append(p)
                    got = True
            except Exception:
                pass
        # 兜底: base64 vless:// 列表
        if not got:
            try:
                decoded = base64.b64decode(text).decode("utf-8", errors="replace")
            except Exception:
                decoded = text
            for line in decoded.splitlines():
                line = line.strip()
                if line.startswith("vless://"):
                    p = _parse_vless_uri(line)
                    if p:
                        key = f"{p.get('uuid','')}@{p.get('server','')}:{p.get('port','')}"
                        if key not in seen_uuid_host:
                            seen_uuid_host.add(key)
                            proxies.append(p)
    logger.info("[xray] 订阅抓取: %d 个订阅, %d 个 vless 节点", sub_count, len(proxies))
    return proxies, sub_count


def _sanitize_tag(name: str) -> str:
    """节点名 → xray outbound tag (去空格/特殊字符)。"""
    tag = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return tag[:48] or "node"


def _clash_vless_to_xray_outbound(p: dict, idx: int) -> Optional[dict]:
    """clash vless proxy → xray outbound。仅支持 vless，返回 None 表示跳过。"""
    if p.get("type") != "vless":
        return None
    name = p.get("name", f"node{idx}")
    server = p.get("server")
    port = p.get("port")
    uuid = p.get("uuid")
    if not (server and port and uuid):
        return None

    network = p.get("network", "tcp") or "tcp"
    reality = p.get("reality-opts")
    tls = p.get("tls")
    flow = p.get("flow", "")
    servername = p.get("servername") or server
    fp = p.get("client-fingerprint") or "chrome"
    skip_cert = bool(p.get("skip-cert-verify"))

    user = {"id": uuid, "encryption": "none"}
    # flow (xtls-rprx-vision) 仅适用于 tcp + (reality/tls)，ws/grpc 下忽略
    if flow and network == "tcp" and (reality or tls):
        user["flow"] = flow

    outbound = {
        "tag": _sanitize_tag(name),
        "protocol": "vless",
        "settings": {"vnext": [{"address": server, "port": int(port), "users": [user]}]},
    }

    ss: dict = {"network": network}
    if reality:
        ss["security"] = "reality"
        ss["realitySettings"] = {
            "serverName": servername,
            "publicKey": reality.get("public-key", ""),
            "shortId": reality.get("short-id", ""),
            "fingerprint": fp,
        }
    elif tls:
        ss["security"] = "tls"
        ss["tlsSettings"] = {
            "serverName": servername,
            "fingerprint": fp,
            "allowInsecure": skip_cert,
        }
    else:
        ss["security"] = "none"

    if network == "ws":
        ws = p.get("ws-opts") or {}
        ss["wsSettings"] = {
            "path": ws.get("path", "/"),
            "headers": ws.get("headers", {}) or {},
        }
    elif network == "grpc":
        grpc = p.get("grpc-opts") or {}
        ss["grpcSettings"] = {"serviceName": grpc.get("grpc-service-name", "")}

    outbound["streamSettings"] = ss
    return outbound


class XrayProxyManager:
    """Xray 内核代理管理器 — 启动/保活/自愈。"""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        # 订阅缓存: 避免每次切换节点都重抓订阅（30 分钟内复用）
        self._cached_proxies: list[dict] = []
        self._cache_ts: float = 0.0
        self._nodes: list[dict] = []          # [{name, tag, server, port, country?}]
        self._current_node: Optional[str] = None
        XRAY_DIR.mkdir(parents=True, exist_ok=True)
        self._load_node_state()

    def _load_node_state(self) -> None:
        """加载持久化的节点列表 + 当前选中节点。"""
        try:
            if XRAY_NODES_FILE.exists():
                self._nodes = json.loads(XRAY_NODES_FILE.read_text(encoding="utf-8"))
        except Exception:
            self._nodes = []
        try:
            if XRAY_CURRENT_FILE.exists():
                self._current_node = XRAY_CURRENT_FILE.read_text(encoding="utf-8").strip() or None
        except Exception:
            self._current_node = None

    def clear_cache(self) -> None:
        """清空订阅缓存，强制下次重新抓取。"""
        self._cached_proxies = []
        self._cache_ts = 0.0
        logger.info("[xray] 订阅缓存已清空")

    def _save_node_state(self) -> None:
        try:
            XRAY_NODES_FILE.write_text(json.dumps(self._nodes, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        try:
            XRAY_CURRENT_FILE.write_text(self._current_node or "", encoding="utf-8")
        except Exception:
            pass

    # ─── 配置生成 ───
    def _build_config(self) -> tuple[bool, int]:
        """抓取所有订阅，生成 xray config.json。
        优先直接抓取订阅（含 clash 链接 + base64），mihomo config.yaml 作为兜底。
        """
        try:
            import yaml
        except Exception as e:
            logger.error("[xray] 缺少 pyyaml: %s", e)
            return False, 0

        proxies: list[dict] = []
        # 1. 直接抓取所有订阅链接（clash + base64），30 分钟内复用缓存
        cache_fresh = (time.time() - self._cache_ts) < 1800 and bool(self._cached_proxies)
        if cache_fresh:
            proxies = list(self._cached_proxies)
            logger.info("[xray] 订阅缓存命中: %d 个节点 (缓存剩余 %d 秒)", len(proxies), int(1800 - (time.time() - self._cache_ts)))
        else:
            try:
                fetched, _ = _fetch_subscription_proxies()
                proxies.extend(fetched)
                if proxies:
                    self._cached_proxies = list(proxies)
                    self._cache_ts = time.time()
                    logger.info("[xray] 订阅抓取并缓存: %d 个节点", len(proxies))
            except Exception as e:
                logger.warning("[xray] 订阅抓取失败，回退 mihomo 配置: %s", e)

        # 2. 兜底: 从 mihomo config.yaml 读取 vless 节点
        if not proxies and MIHOMO_CONFIG.exists():
            try:
                cfg = yaml.safe_load(MIHOMO_CONFIG.read_text(encoding="utf-8"))
                mihomo_proxies = cfg.get("proxies", []) if isinstance(cfg, dict) else []
                proxies = [p for p in mihomo_proxies if p.get("type") == "vless"]
            except Exception as e:
                logger.error("[xray] 读取 mihomo 配置失败: %s", e)

        if not proxies:
            logger.error("[xray] 无可用 vless 节点（订阅抓取 + mihomo 兜底均空）")
            return False, 0

        # 转换为 xray outbounds（node 与 outbound 配对，保持同步）
        outbounds: list[dict] = []
        nodes: list[dict] = []
        preferred = self._current_node  # 优先把上次选中节点放第一个
        preferred_pair: list | None = None  # (node, outbound)
        for i, p in enumerate(proxies):
            ob = _clash_vless_to_xray_outbound(p, i)
            if not ob:
                continue
            name = p.get("name", f"node{i}")
            nd = {"name": name, "tag": ob["tag"], "server": p.get("server", ""), "port": p.get("port", 0)}
            pair = [nd, ob]
            if preferred and name == preferred:
                preferred_pair = pair
            else:
                outbounds.append(pair[1])
                nodes.append(pair[0])

        if not outbounds and not preferred_pair:
            logger.error("[xray] 节点转换全部失败")
            return False, 0

        # 把上次选中节点放第一位 (tag=proxy)，否则用第一个
        if preferred_pair:
            preferred_pair[1]["tag"] = "proxy"
            preferred_pair[0]["tag"] = "proxy"
            ordered = [preferred_pair[1]] + outbounds
            ordered_nodes = [preferred_pair[0]] + nodes
        else:
            outbounds[0]["tag"] = "proxy"
            nodes[0]["tag"] = "proxy"
            ordered = outbounds
            ordered_nodes = nodes

        for j, ob in enumerate(ordered[1:], start=1):
            ob["tag"] = f"alt-{j}"

        ordered.append({"tag": "direct", "protocol": "freedom"})
        ordered.append({"tag": "block", "protocol": "blackhole"})

        # 当前节点 = 第一个 (tag=proxy)
        self._nodes = ordered_nodes
        # proxy 节点的真实名字
        proxy_name = next((n["name"] for n in ordered_nodes if n["tag"] == "proxy"), None)
        self._current_node = proxy_name or ordered_nodes[0]["name"]
        self._save_node_state()

        xcfg = {
            "log": {"loglevel": "warning"},
            "inbounds": [
                {
                    "tag": "socks-in",
                    "listen": "127.0.0.1",
                    "port": SOCKS_PORT,
                    "protocol": "socks",
                    "settings": {"auth": "noauth", "udp": False},
                },
                {
                    "tag": "http-in",
                    "listen": "127.0.0.1",
                    "port": HTTP_PORT,
                    "protocol": "http",
                    "settings": {},
                },
            ],
            "outbounds": ordered,
            # 无 routing 规则: xray 默认走第一个 outbound (tag=proxy)
            "routing": {"rules": []},
        }

        XRAY_DIR.mkdir(parents=True, exist_ok=True)
        XRAY_CONFIG.write_text(json.dumps(xcfg, ensure_ascii=False, indent=2), encoding="utf-8")
        node_count = len(ordered) - 2  # 去掉 direct/block
        logger.info("[xray] 配置已生成: %d 个 vless 节点, 当前=%s", node_count, self._current_node)
        return True, node_count

    # ─── 生命周期 ───
    @property
    def is_running(self) -> bool:
        return _check_port("127.0.0.1", HTTP_PORT) or _check_port("127.0.0.1", SOCKS_PORT)

    @property
    def proxy_url(self) -> Optional[str]:
        return PROXY_URL_HTTP if self.is_running else None

    def start(self) -> tuple[bool, str]:
        """启动 xray 内核子进程。"""
        if self.is_running:
            return True, f"xray 已在运行 (http {HTTP_PORT})"

        ok, n = self._build_config()
        if not ok:
            return False, "xray 配置生成失败 (无可用 vless 节点或 mihomo 配置缺失)"

        _kill_our_xray()

        if _check_port("127.0.0.1", HTTP_PORT) or _check_port("127.0.0.1", SOCKS_PORT):
            return False, f"端口 {HTTP_PORT}/{SOCKS_PORT} 仍被占用"

        log_fp = open(XRAY_LOG_FILE, "a", encoding="utf-8")
        try:
            self._process = subprocess.Popen(
                [XRAY_BIN, "run", "-c", str(XRAY_CONFIG)],
                stdout=log_fp,
                stderr=subprocess.STDOUT,
            )
        except Exception as e:
            log_fp.close()
            return False, f"xray 启动失败: {e}"

        try:
            XRAY_PID_FILE.write_text(str(self._process.pid), encoding="utf-8")
        except Exception:
            pass

        logger.info("[xray] 已启动 PID=%s", self._process.pid)

        # 等待端口就绪
        for _ in range(30):
            time.sleep(0.5)
            if self.is_running:
                break
        else:
            return False, f"xray 启动超时 (端口 {HTTP_PORT}/{SOCKS_PORT} 未监听)，查看 {XRAY_LOG_FILE}"

        time.sleep(1)
        # 验证出口（非强制：失败也认为启动成功，保活循环会持续自愈）
        try:
            t = self.test_proxy()
            if t.get("ok"):
                return True, f"xray 已启动 → {t.get('ip')} ({t.get('country')}), {n} 个节点"
            return True, f"xray 已启动，出口验证失败: {t.get('error')} (保活循环将自愈)"
        except Exception as e:
            return True, f"xray 已启动，出口验证异常: {e}"

    def ensure_running(self) -> tuple[bool, str]:
        """保活入口：未运行则启动。"""
        if self.is_running:
            return True, "xray 内核运行中"
        logger.warning("[xray] 内核未运行，自动拉起")
        return self.start()

    def stop(self) -> tuple[bool, str]:
        _kill_our_xray()
        self._process = None
        try:
            XRAY_PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        return True, "xray 已停止"

    # ─── 测试 ───
    def test_proxy(self) -> dict:
        if not self.is_running:
            return {"ok": False, "error": "xray 未运行"}
        # 保活场景：单次请求 8s，不重试 (失败由保活循环决策，避免长时间阻塞)
        try:
            os.environ["NO_PROXY"] = "127.0.0.1,localhost"
            r = requests.get(
                "https://ipinfo.io/json",
                proxies={"http": PROXY_URL_HTTP, "https": PROXY_URL_HTTP},
                timeout=8,
            )
            if r.status_code == 200:
                d = r.json()
                return {"ok": True, "ip": d.get("ip", ""), "country": d.get("country", "")}
            return {"ok": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ─── 状态 ───
    def status(self) -> dict:
        running = self.is_running
        exit_ip = None
        exit_country = None
        if running:
            t = self.test_proxy()
            if t.get("ok"):
                exit_ip = t.get("ip")
                exit_country = t.get("country")
        return {
            "running": running,
            "kernel": "xray-core",
            "proxy_url": PROXY_URL_HTTP if running else None,
            "socks_port": SOCKS_PORT,
            "http_port": HTTP_PORT,
            "config": str(XRAY_CONFIG),
            "pid": self._read_pid(),
            "node_count": len(self._nodes),
            "current_node": self._current_node,
            "exit_ip": exit_ip,
            "exit_country": exit_country,
            "nodes": self.nodes(),
        }

    # ─── 节点管理 ───
    def nodes(self) -> list[dict]:
        """返回所有节点列表 + 当前选中标记 + 延迟。"""
        out = []
        for n in self._nodes:
            nn = dict(n)
            nn["current"] = (n.get("name") == self._current_node)
            out.append(nn)
        return out

    def switch_node(self, name: str) -> tuple[bool, str]:
        """切换当前出站节点: 设为 current_node 后重建配置 + 重启内核。"""
        if not any(n.get("name") == name for n in self._nodes):
            return False, f"节点不存在: {name}"
        self._current_node = name
        self._save_node_state()
        self.stop()
        ok, msg = self.start()
        if ok:
            return True, f"已切换到 {name}: {msg}"
        return False, f"切换失败: {msg}"

    def restart(self) -> tuple[bool, str]:
        """重启 xray 内核（重新抓取订阅 + 重建配置）。"""
        self.stop()
        return self.start()

    def refresh_subscriptions(self) -> tuple[bool, str]:
        """强制重新抓取订阅并重建配置 + 重启。"""
        ok, msg = self.restart()
        if ok:
            return True, f"订阅已刷新: {msg}"
        return False, f"刷新失败: {msg}"

    def _read_pid(self) -> Optional[int]:
        try:
            if XRAY_PID_FILE.exists():
                return int(XRAY_PID_FILE.read_text().strip())
        except Exception:
            pass
        return None


# ─── 全局单例 ───
_manager: Optional[XrayProxyManager] = None


def get_xray_manager() -> XrayProxyManager:
    global _manager
    if _manager is None:
        _manager = XrayProxyManager()
    return _manager


def test_proxy() -> dict:
    return get_xray_manager().test_proxy()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    mgr = get_xray_manager()
    if action == "start":
        print(mgr.start())
    elif action == "stop":
        print(mgr.stop())
    elif action == "test":
        print(mgr.test_proxy())
    elif action == "restart":
        print(mgr.restart())
    elif action == "refresh":
        mgr.clear_cache()
        print(mgr.refresh_subscriptions())
    elif action == "nodes":
        print(json.dumps(mgr.nodes(), ensure_ascii=False, indent=2))
    elif action == "switch":
        name = sys.argv[2] if len(sys.argv) > 2 else ""
        print(mgr.switch_node(name))
    else:
        print(json.dumps(mgr.status(), ensure_ascii=False, indent=2))
