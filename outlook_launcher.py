#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Outlook 邮箱注册启动器

只负责三件事：
1) 自动获取/导入代理
2) 注册前代理轮询
3) 定时启动注册

Outlook 注册流程本身复用私仓已跑通的 `邮箱注册.cdp_outlook.register_outlook_account`。
默认使用可视实体浏览器 + 无痕模式；不使用 headless。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import random
import re
import sys
import time
import threading
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent
PKG = ROOT / "邮箱注册"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PKG))

from 邮箱注册.cdp_outlook import register_outlook_account, kill_orphan_chrome_processes, CDPBrowser, CDPLaunchConfig, _extract_refresh_token_device_code
from 邮箱注册.proxy_utils import parse_proxies, parse_proxy
from 邮箱注册.subscription_proxy import get_manager

RUN_DIR = ROOT / "runtime_outlook"
LOG_DIR = RUN_DIR / "logs"
PROXY_FILE = RUN_DIR / "proxies.txt"
RESULT_FILE = RUN_DIR / "results.jsonl"
SCHEDULE_STATE = RUN_DIR / "schedule_state.json"

LOG_DIR.mkdir(parents=True, exist_ok=True)
RUN_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "outlook_launcher.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    force=True,
)
log = logging.getLogger("outlook_launcher")

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)


def load_proxy_lines() -> list[str]:
    if not PROXY_FILE.exists():
        return []
    return [line.strip() for line in PROXY_FILE.read_text(encoding="utf-8-sig").splitlines() if line.strip() and not line.strip().startswith("#")]


def save_proxy_lines(lines: Iterable[str]) -> None:
    seen: set[str] = set()
    out: list[str] = []
    for raw in lines:
        p = parse_proxy(raw)
        if not p:
            continue
        key = p.url.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p.url)
    PROXY_FILE.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    log.info("代理文件已保存: %s (%d 个)", PROXY_FILE, len(out))


def import_proxies_from_text(text: str, append: bool = True) -> int:
    parsed = [p.url for p in parse_proxies(text)]
    existing = load_proxy_lines() if append else []
    save_proxy_lines(existing + parsed)
    return len(parsed)


def import_proxies_from_file(path: str, append: bool = True) -> int:
    text = Path(path).read_text(encoding="utf-8-sig")
    return import_proxies_from_text(text, append=append)


def import_subscription(url: str, name: str = "") -> None:
    mgr = get_manager()
    ok, msg = mgr.add(url, name=name)
    log.info("订阅导入: %s", msg)
    ok, msg = mgr.start()
    log.info("订阅代理启动: %s", msg)
    if not ok:
        raise RuntimeError(msg)


def import_auto(source: str, append: bool = True) -> None:
    src = source.strip()
    if Path(src).exists():
        count = import_proxies_from_file(src, append=append)
        log.info("已从文件导入代理 %d 个: %s", count, src)
        return
    if URL_RE.fullmatch(src):
        import_subscription(src)
        return
    count = import_proxies_from_text(src, append=append)
    log.info("已从文本导入代理 %d 个", count)


def curl_check_proxy(proxy_url: str, timeout: int = 15) -> dict:
    import subprocess
    test_proxy = proxy_url.replace("socks5://", "socks5h://")
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout), "--proxy", test_proxy, "https://ipinfo.io/json"],
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
        if r.returncode != 0:
            return {"ok": False, "error": r.stderr.strip() or r.stdout.strip() or f"curl_exit_{r.returncode}"}
        data = json.loads(r.stdout)
        return {"ok": True, "ip": data.get("ip", ""), "country": data.get("country", ""), "city": data.get("city", ""), "raw": data}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


class ProxyRotator:
    """代理轮循器：按「节点」轮循（不按 IP 去重，同一 IP 的不同节点照常轮循），
    游标遍历全部节点，每个注册取下一个「对 Outlook 可用且未被拉黑」的节点；
    遍历完一轮（全部节点都试过一遍）才算一个轮循，之后重新开始下一轮。
    account_blocked 时按节点名拉黑（4 小时不再使用该节点）。状态持久化跨批次。
    xray 为主内核，不可用时降级到 mihomo。"""

    ROTATION_FILE = RUN_DIR / "proxy_rotation.json"
    BLOCKED_NODES_FILE = RUN_DIR / "blocked_nodes.json"
    EXCLUDE = {"COMPATIBLE", "DIRECT", "PASS", "REJECT", "REJECT-DROP"}

    def __init__(self, shuffle: bool = False):
        self.manager = get_manager()
        if self.manager.subscriptions and not self.manager.is_running:
            log.info("检测到 %d 个 mihomo 订阅，尝试启动（兜底内核）...", len(self.manager.subscriptions))
            os.environ["SUB_PROXY_FAST_START"] = "1"
            ok, msg = self.manager.start()
            log.info("mihomo 启动: %s | %s", ok, msg)
        # xray 为主内核（出口 IP 各异，适合 IP 轮循）
        from 邮箱注册.xray_proxy import get_xray_manager
        self.xray = get_xray_manager()
        self.use_xray = False
        if not self.xray.is_running:
            ok, msg = self.xray.ensure_running()
            log.info("xray 内核启动: %s | %s", ok, msg)
        self.use_xray = self.xray.is_running

        self.static = load_proxy_lines()
        if shuffle:
            random.shuffle(self.static)
        self.fail_count: dict[str, int] = {}
        self._lock = threading.Lock()
        state = self._load_state()
        self.cursor = state.get("cursor", 0)
        self.blocked_nodes = self._load_blocked_nodes()
        self.round = state.get("round", 1)
        self.cycle_tested = state.get("cycle_tested", 0)
        self.used_this_round: list[str] = state.get("used_this_round", [])
        self.current_node: str = ""  # 当前正在使用的节点名（供 mark_blocked 用）
        self.nodes: list[str] = []
        self._refresh_snapshot()
        log.info("🔄 代理轮循初始化: 内核=%s, 第 %d 轮, 游标=%d, 本轮已测=%d, 已用节点=%d, 节点总数=%d, 黑名单节点=%d",
                 "xray" if self.use_xray else "mihomo", self.round, self.cursor,
                 self.cycle_tested, len(self.used_this_round), len(self.nodes), len(self.blocked_nodes))

    # ─── 持久状态 ───
    def _load_blocked_nodes(self) -> dict:
        """加载被封节点黑名单 {node_name: block_until_timestamp}。"""
        try:
            if self.BLOCKED_NODES_FILE.exists():
                data = json.loads(self.BLOCKED_NODES_FILE.read_text())
                now = time.time()
                # 清理过期条目（4 小时自动解封）
                return {n: ts for n, ts in data.items() if ts > now}
        except Exception:
            pass
        return {}

    def _save_blocked_nodes(self):
        try:
            self.BLOCKED_NODES_FILE.write_text(json.dumps(self.blocked_nodes, indent=2))
        except Exception:
            pass

    def mark_blocked(self, node_name: str, hours: float = 4) -> None:
        """将节点加入黑名单（默认 4 小时不再使用）。"""
        if not node_name:
            return
        with self._lock:
            self.blocked_nodes[node_name] = time.time() + hours * 3600
            self._save_blocked_nodes()
        log.warning("🚫 节点 [%s] 已加入黑名单（%d小时）", node_name, int(hours))

    def _load_state(self) -> dict:
        try:
            if self.ROTATION_FILE.exists():
                return json.loads(self.ROTATION_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_state(self):
        try:
            self.ROTATION_FILE.write_text(json.dumps({
                "cursor": self.cursor,
                "round": self.round,
                "cycle_tested": self.cycle_tested,
                "used_this_round": self.used_this_round[-300:],
                "current_node": self.current_node,
                "kernel": "xray" if self.use_xray else "mihomo",
                "total_nodes": len(self.nodes),
                "updated_at": dt.datetime.now().isoformat(),
            }, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _refresh_snapshot(self):
        """刷新节点快照（去重保序）。优先 xray，降级 mihomo。"""
        nodes = []
        if self.use_xray and self.xray.is_running:
            try:
                nodes = [n.get("name", "") for n in self.xray.nodes()]
            except Exception as e:
                log.warning("xray 节点快照失败: %s", e)
        if not nodes and self.manager.is_running:
            self.use_xray = False
            try:
                nodes = [n.get("name", "") for n in self.manager.get_nodes()
                         if n.get("name", "") not in self.EXCLUDE]
            except Exception as e:
                log.warning("mihomo 节点快照失败: %s", e)
        seen = set()
        self.nodes = [n for n in nodes if n and not (n in seen or seen.add(n))]
        # 节点优先级排序：台湾/日本 > AWS > 其他（基于实际成功率：TW/JP 100%, AWS 100%, DO 25%）
        def _priority(name):
            n = name.lower()
            if any(k in n for k in ["台湾", "台灣", "tw", "japan", "日本", "jp"]):
                return 0
            if any(k in n for k in ["aws", "amazon"]):
                return 1
            return 2
        self.nodes.sort(key=_priority)

    # ─── 内核统一接口 ───
    def _kernel_proxy_url(self) -> str:
        if self.use_xray and self.xray.is_running:
            return self.xray.proxy_url or ""
        if self.manager.is_running:
            return self.manager.proxy_url or ""
        return ""

    def _switch_node(self, name: str) -> tuple[bool, str]:
        if self.use_xray and self.xray.is_running:
            return self.xray.switch_node(name)
        if self.manager.is_running:
            return self.manager.switch_to_node(name)
        return False, "无可用代理内核"

    def _ensure_kernel(self):
        """保活：内核掉线则拉起。"""
        if self.use_xray:
            if not self.xray.is_running:
                log.warning("xray 内核掉线，重新拉起...")
                ok, msg = self.xray.ensure_running()
                log.info("xray 拉起: %s | %s", ok, msg)
                self.use_xray = self.xray.is_running
        else:
            if self.manager.subscriptions and not self.manager.is_running:
                log.warning("mihomo 掉线，重新拉起...")
                os.environ["SUB_PROXY_FAST_START"] = "1"
                ok, msg = self.manager.start()
                log.info("mihomo 拉起: %s | %s", ok, msg)

    @staticmethod
    def _test_outlook(proxy_url: str) -> dict:
        """curl 实测对 Outlook signup 可用性 + 取出口 IP（7s）。"""
        if not proxy_url:
            return {"ok": False, "http_code": "", "ip": "", "country": ""}
        import subprocess
        tp = proxy_url.replace("socks5://", "socks5h://")
        try:
            r = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                 "--max-time", "7", "--proxy", tp, "https://signup.live.com/"],
                capture_output=True, text=True, timeout=12,
            )
            code = (r.stdout or "").strip()
            ok = bool(code) and code[0] in "23"
        except Exception:
            code, ok = "000", False
        ip, country = "", ""
        if ok:
            ck = curl_check_proxy(proxy_url, timeout=7)
            ip = ck.get("ip", "") if ck.get("ok") else ""
            country = ck.get("country", "") if ck.get("ok") else ""
        return {"ok": ok, "http_code": code, "ip": ip, "country": country}

    # ─── 轮循核心 ───
    def next(self) -> str:
        with self._lock:
            return self._next_unlocked()

    def _next_unlocked(self) -> str:
        # ===== 自动三阶梯代理 =====
        # Tier1: 内核代理 → Tier3: 静态代理 → 自动循环
        self._ensure_kernel()
        has_kernel = (self.use_xray and self.xray.is_running) or self.manager.is_running

        # 先刷新内核节点快照
        if has_kernel and not self.nodes:
            self._refresh_snapshot()
        N = len(self.nodes) if has_kernel else 0

        # 内核节点全部被封/不可用 → 切到静态代理
        if has_kernel and self.cycle_tested >= N and len(self.used_this_round) == 0 and self.static:
            log.info("[AUTO-TIER] 内核节点全部不可用, 自动切到机场代理(Tier3)")
            has_kernel = False  # 强制走静态

        # 无可用内核 → 静态代理轮循
        if not has_kernel:
            if not self.static:
                log.warning("[AUTO-TIER] 无任何代理可用")
                return ""
            for _ in range(len(self.static)):
                proxy = self.static[self.cursor % len(self.static)]
                self.cursor += 1
                if self.fail_count.get(proxy, 0) < 3:
                    return proxy
            # 静态代理全部失败 → 尝试回内核
            log.info("[AUTO-TIER] 静态代理全部失败, 尝试切回内核")
            if has_kernel:
                self.cycle_tested = 0
                self._refresh_snapshot()
            else:
                self.fail_count.clear()
                return self.static[self.cursor % len(self.static)] if self.static else ""

        # 内核节点数为零
        if N == 0:
            return self._kernel_proxy_url()

        # 内核节点轮询
        while True:
            if self.cycle_tested >= N:
                usable = len(self.used_this_round)
                if usable == 0:
                    log.warning("[AUTO-TIER] 第 %d 轮全部 %d 节点均不可用, 切到机场代理", self.round, N)
                    self._save_state()
                    # 尝试静态代理
                    if self.static:
                        for _ in range(len(self.static)):
                            proxy = self.static[self.cursor % len(self.static)]
                            self.cursor += 1
                            if self.fail_count.get(proxy, 0) < 3:
                                return proxy
                    return self._kernel_proxy_url()
                log.info("🔄 ===== 第 %d 轮代理轮循完成: 遍历全部 %d 节点, 可用 %d 个, 开始第 %d 轮 =====",
                         self.round, N, usable, self.round + 1)
                self.round += 1
                self.used_this_round = []
                self.cycle_tested = 0
                self._refresh_snapshot()
                N = len(self.nodes)
                if N == 0:
                    return self._kernel_proxy_url()

            name = self.nodes[self.cursor % N]
            self.cursor += 1
            self.cycle_tested += 1

            # 节点在黑名单中 → 跳过
            if name in self.blocked_nodes:
                log.info("🔄 跳过 [%s]: 节点在黑名单中（剩余 %d 分钟）", name, int((self.blocked_nodes[name] - time.time()) / 60))
                continue

            ok, msg = self._switch_node(name)
            if not ok:
                log.info("🔄 跳过 [%s]: 切换失败(%s)", name, msg)
                continue

            proxy_url = self._kernel_proxy_url()
            t = self._test_outlook(proxy_url)
            if t["ok"]:
                if name not in self.used_this_round:
                    self.used_this_round.append(name)
                self.current_node = name  # 记录当前节点，供 account_blocked 拉黑用
                pos = self.cursor % N or N
                log.info("🔄 第 %d 轮 [已用 %d/%d 节点] 游标 %d/%d → 节点[%s] 出口 %s (%s) signup=%s ✅",
                         self.round, len(self.used_this_round), N, pos, N, name, t["ip"], t["country"], t["http_code"])
                self._save_state()
                return proxy_url
            else:
                log.info("🔄 跳过 [%s]: Outlook 不可用 (signup=%s ip=%s)", name, t["http_code"], t["ip"] or "无")
                continue

    def mark_failed(self, proxy: str) -> None:
        if proxy:
            self.fail_count[proxy] = self.fail_count.get(proxy, 0) + 1

    def cycle_summary(self) -> dict:
        with self._lock:
            return self._summary_unlocked()

    def _summary_unlocked(self) -> dict:
        return {
            "kernel": "xray" if self.use_xray else "mihomo",
            "round": self.round,
            "cursor": self.cursor,
            "cycle_tested": self.cycle_tested,
            "used_this_round": len(self.used_this_round),
            "blocked_nodes": len(self.blocked_nodes),
            "total_nodes": len(self.nodes),
            "current_node": self.current_node,
            "used_names": self.used_this_round[-20:],
        }


def write_result(record: dict) -> None:
    with RESULT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _retry_fetch_rt_with_fresh_browser(email: str, password: str, client_id: str, timeout: int = 120) -> str:
    """注册成功但未拿到RT时，用全新干净的浏览器通过 Device Code 补获取 refresh_token。

    注册流程内嵌的RT获取复用同一个（可能已腐化的）浏览器，成功率低；
    这里每次新开一个干净的 CDPBrowser，与手动 batch 同款配置，成功率更高。
    """
    log.info("[RT-RETRY] 注册成功但未拿到RT，用全新浏览器补获取: %s", email)
    cfg = CDPLaunchConfig(browser_type="chrome", proxy="", headless=True)
    browser = CDPBrowser(cfg)
    browser.launch()
    try:
        rt = _extract_refresh_token_device_code(
            browser, email, client_id,
            password=password, proxy_url="",
            timeout=timeout,
        )
        if rt and len(rt) > 20:
            log.info("[RT-RETRY] ✅ %s: RT 补获取成功", email)
            return rt
        log.warning("[RT-RETRY] ❌ %s: RT 补获取失败", email)
        return ""
    except Exception as e:
        log.warning("[RT-RETRY] ❌ %s: 补获取异常: %s", email, e)
        return ""
    finally:
        try:
            browser.close()
        except Exception:
            pass
        try:
            kill_orphan_chrome_processes()
        except Exception:
            pass


def run_once(proxy: str, browser: str = "chrome", extract_rt: bool = True, slot_index: int = 0) -> dict:
    if proxy:
        check = curl_check_proxy(proxy)
        if check.get("ok"):
            log.info("代理预检通过: %s %s %s", check.get("ip"), check.get("country"), proxy)
        else:
            raise RuntimeError(f"代理预检失败: {proxy} -> {check.get('error')}")
    else:
        log.warning("本次注册未使用代理")

    result = register_outlook_account(
        browser_type=browser,
        proxy=proxy or "",
        headless=False,
        extract_rt=extract_rt,
        keep_browser_open=False,
        slot_index=slot_index,
    )
    record = {
        "ts": dt.datetime.now().isoformat(),
        "success": bool(result.success),
        "email": result.email,
        "password": result.password,
        "client_id": result.client_id,
        "refresh_token": result.refresh_token,
        "error": result.error,
        "final_url": result.final_url,
        "final_state": result.final_state,
        "challenge_type": result.challenge_type,
        "challenge_cleared": result.challenge_cleared,
        "proxy": proxy,
        "screenshot_path": result.screenshot_path,
    }
    # ── 注册成功但未拿到RT时，立即用全新浏览器补获取RT（趁密码还在内存里直接出四凭证）──
    if record.get("success") and not (record.get("refresh_token") and len(record["refresh_token"]) > 20):
        retry_rt = _retry_fetch_rt_with_fresh_browser(
            record.get("email", ""),
            record.get("password", ""),
            record.get("client_id") or "14d82eec-204b-4c2f-b7e8-296a70dab67e",
            timeout=120,
        )
        if retry_rt and len(retry_rt) > 20:
            record["refresh_token"] = retry_rt
    write_result(record)
    # ── 每次注册后清理孤儿 Chrome 进程 ──
    try:
        kill_orphan_chrome_processes()
    except Exception as e:
        log.warning("孤儿清理失败: %s", e)
    return record


def _register_one(idx: int, count: int, proxy: str, rotator: ProxyRotator, browser: str, extract_rt: bool, max_proxy_attempts: int) -> dict:
    """单个账号注册任务（可在独立线程中运行）。proxy 由调用方提供，
    分批并行模式下同批 workers 个线程共享同一 proxy（同一节点出口）。
    代理失败时重试同一 proxy（浏览器操作级重试），不在此函数内切换节点。"""
    last_error = ""
    recorded = False
    result = None
    for attempt in range(1, max_proxy_attempts + 1):
        try:
            log.info("[T%d] 开始第 %d/%d 个注册，尝试 %d/%d，proxy=%s", idx, idx + 1, count, attempt, max_proxy_attempts, proxy or "none")
            record = run_once(proxy, browser=browser, extract_rt=False, slot_index=idx)
            result = record
            recorded = True
            if record.get("success"):
                log.info("[T%d] 注册成功: %s", idx, record.get("email"))
                last_error = ""
                # ── 获取 RT：新浏览器账号密码登录方式（batch_rt.py 思路，独立浏览器实例）──
                if extract_rt and not record.get("refresh_token"):
                    rt = _fetch_rt_via_new_browser(record, port=20000 + idx * 1000)
                    if rt:
                        record["refresh_token"] = rt
                        log.info("[T%d] 新浏览器获取 RT 成功: %s... (%s)", idx, rt[:30], record.get("email"))
                    else:
                        log.warning("[T%d] 新浏览器获取 RT 失败: %s", idx, record.get("email"))
                break
            last_error = str(record.get("error") or "unknown_failure")
            log.warning("[T%d] 注册失败: %s | %s", idx, record.get("email"), last_error)
            # account_blocked → 将当前节点加入黑名单（4 小时）
            if "account_blocked" in last_error and rotator.current_node:
                rotator.mark_blocked(rotator.current_node)
        except Exception as exc:
            last_error = str(exc)
            log.exception("[T%d] 注册异常: %s", idx, exc)
        if _is_proxy_related_error(last_error) and attempt < max_proxy_attempts:
            log.warning("[T%d] 代理相关失败，重试同一节点: %s", idx, last_error)
            time.sleep(2)
            continue
        break
    if last_error and not recorded:
        result = {"success": False, "error": last_error, "ts": dt.datetime.now().isoformat()}
    return result or {"success": False, "error": "no_result", "ts": dt.datetime.now().isoformat()}


def run_batch(count: int, browser: str, extract_rt: bool, shuffle: bool, max_proxy_attempts: int = 8, workers: int = 1) -> list[dict]:
    rotator = ProxyRotator(shuffle=shuffle)
    log.info("📦 本轮注册开始: 目标 %d 个 | 并行线程 %d | 代理轮循: %s", count, workers, rotator.cycle_summary())
    results: list[dict] = []

    if workers <= 1:
        # ── 串行模式：每个账号独立切换节点 ──
        for i in range(count):
            proxy = rotator.next()
            result = _register_one(i, count, proxy, rotator, browser, extract_rt, max_proxy_attempts)
            results.append(result)
            try:
                kill_orphan_chrome_processes()
            except Exception:
                pass
    else:
        # ── 分批并行模式：每批 workers 个账号共享同一节点 ──
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import math
        batch_count = math.ceil(count / workers)
        log.info("📦 分批并行: %d 批 × %d 线程 = %d 个账号", batch_count, workers, count)
        done = 0
        for batch_idx in range(batch_count):
            # 每批切换 1 次节点（避免多线程同时操作 xray）
            proxy = rotator.next()
            log.info("📦 第 %d/%d 批: 节点已切换, proxy=%s", batch_idx + 1, batch_count, proxy or "none")
            # 本批 workers 个账号
            batch_idxs = [batch_idx * workers + w for w in range(workers) if batch_idx * workers + w < count]
            with ThreadPoolExecutor(max_workers=len(batch_idxs)) as pool:
                futures = {pool.submit(_register_one, idx, count, proxy, rotator, browser, extract_rt, max_proxy_attempts): idx for idx in batch_idxs}
                for fut in as_completed(futures):
                    idx = futures[fut]
                    done += 1
                    try:
                        result = fut.result()
                        results.append(result)
                        log.info("[T%d] 任务完成(%d/%d): success=%s", idx, done, count, result.get("success"))
                    except Exception as exc:
                        log.exception("[T%d] 任务异常: %s", idx, exc)
                        results.append({"success": False, "error": str(exc), "ts": dt.datetime.now().isoformat()})
            # 每批结束后清理 Chrome
            try:
                kill_orphan_chrome_processes()
            except Exception:
                pass
            log.info("📦 第 %d/%d 批完成, 累计 %d/%d", batch_idx + 1, batch_count, done, count)

    ok = sum(1 for r in results if r.get("success"))
    rt_ok = sum(1 for r in results if r.get("success") and r.get("refresh_token"))
    log.info("📦 本轮注册结束: 成功 %d/%d | RT %d/%d | 代理轮循: %s",
             ok, len(results), rt_ok, ok, rotator.cycle_summary())
    return results


def _is_proxy_related_error(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in [
        "代理预检失败", "proxy_error", "chrome-error", "curl_exit", "connection", "timeout", "err_tunnel", "err_proxy",
    ])


def parse_run_at(value: str) -> dt.datetime:
    if not value:
        return dt.datetime.now()
    text = value.strip()
    if re.fullmatch(r"\d{1,2}:\d{2}", text):
        hour, minute = map(int, text.split(":"))
        now = dt.datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += dt.timedelta(days=1)
        return target
    return dt.datetime.fromisoformat(text)


def schedule_loop(at: str, interval_minutes: int, count: int, browser: str, extract_rt: bool, shuffle: bool, max_proxy_attempts: int, workers: int = 1) -> None:
    next_run = parse_run_at(at)
    while True:
        state = {"next_run": next_run.isoformat(), "interval_minutes": interval_minutes, "count": count}
        SCHEDULE_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        sleep_s = max(0, (next_run - dt.datetime.now()).total_seconds())
        log.info("定时器等待到 %s 后启动注册，count=%d", next_run.isoformat(), count)
        time.sleep(sleep_s)
        run_batch(count=count, browser=browser, extract_rt=extract_rt, shuffle=shuffle, max_proxy_attempts=max_proxy_attempts, workers=workers)
        if interval_minutes <= 0:
            break
        next_run = dt.datetime.now() + dt.timedelta(minutes=interval_minutes)


def main() -> int:
    parser = argparse.ArgumentParser(description="Outlook 注册启动器：代理导入/轮询/定时启动")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_import = sub.add_parser("import-proxies", help="导入代理；参数可为 txt 文件、订阅 URL 或多行代理文本")
    p_import.add_argument("source")
    p_import.add_argument("--replace", action="store_true", help="替换现有静态代理文件")

    p_run = sub.add_parser("run", help="立即启动注册")
    p_run.add_argument("--count", type=int, default=1)
    p_run.add_argument("--browser", default="chrome")
    p_run.add_argument("--no-rt", action="store_true", help="不提取 refresh token")
    p_run.add_argument("--shuffle", action="store_true")
    p_run.add_argument("--max-proxy-attempts", type=int, default=8, help="单个账号最多轮询尝试的代理/节点数")
    p_run.add_argument("--workers", type=int, default=1, help="并行注册线程数（建议 1-2，Chrome 内存约 300MB/实例）")

    p_schedule = sub.add_parser("schedule", help="定时启动注册")
    p_schedule.add_argument("--at", default="", help="启动时间：HH:MM 或 ISO 时间；为空=立即")
    p_schedule.add_argument("--interval-minutes", type=int, default=0, help="循环间隔；0=只跑一次")
    p_schedule.add_argument("--count", type=int, default=1)
    p_schedule.add_argument("--browser", default="chrome")
    p_schedule.add_argument("--no-rt", action="store_true")
    p_schedule.add_argument("--shuffle", action="store_true")
    p_schedule.add_argument("--max-proxy-attempts", type=int, default=8, help="单个账号最多轮询尝试的代理/节点数")
    p_schedule.add_argument("--workers", type=int, default=1, help="并行注册线程数")

    p_status = sub.add_parser("status", help="查看代理/结果状态")

    args = parser.parse_args()
    if args.cmd == "import-proxies":
        import_auto(args.source, append=not args.replace)
        return 0
    if args.cmd == "run":
        run_batch(count=args.count, browser=args.browser, extract_rt=not args.no_rt, shuffle=args.shuffle, max_proxy_attempts=args.max_proxy_attempts, workers=args.workers)
        return 0
    if args.cmd == "schedule":
        schedule_loop(args.at, args.interval_minutes, args.count, args.browser, not args.no_rt, args.shuffle, args.max_proxy_attempts, args.workers)
        return 0
    if args.cmd == "status":
        mgr = get_manager()
        status = {
            "static_proxy_count": len(load_proxy_lines()),
            "force_static": (RUN_DIR / "force_static").exists(),
            "proxy_file": str(PROXY_FILE),
            "subscription_proxy": mgr.status(),
            "result_file": str(RESULT_FILE),
            "schedule_state": json.loads(SCHEDULE_STATE.read_text(encoding="utf-8")) if SCHEDULE_STATE.exists() else {},
        }
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
