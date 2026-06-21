#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
注册后自动获取 RT — 从 results.jsonl 找没有 RT 的邮箱，用 Playwright 自动获取。
设计为 outlook_daemon.py 在每轮注册后调用。
"""
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOL_DIR = ROOT / "outlook-token-tool"
sys.path.insert(0, str(TOOL_DIR))

RT_DIR = ROOT / "runtime_outlook" / "rt_tokens"
RT_DIR.mkdir(parents=True, exist_ok=True)
RESULTS = ROOT / "runtime_outlook" / "results.jsonl"


def find_emails_without_rt(limit: int = 10) -> list[dict]:
    """从 results.jsonl 中找成功注册但没有 RT 的邮箱。"""
    if not RESULTS.exists():
        return []
    # 已有 RT 的邮箱
    have_rt: set[str] = set()
    for f in RT_DIR.glob("*.txt"):
        content = f.read_text(encoding="utf-8").strip()
        parts = content.split("----")
        if len(parts) >= 4 and parts[3].strip() and len(parts[3].strip()) > 20:
            have_rt.add(parts[0].strip().lower())

    rows: list[dict] = []
    for line in RESULTS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not d.get("success") or not d.get("email"):
            continue
        email = d["email"].strip().lower()
        if email in have_rt:
            continue
        if d.get("refresh_token") and len(d["refresh_token"]) > 20:
            continue
        rows.append(d)
    return rows[:limit]


def write_back_rt(email: str, rt: str) -> None:
    """把 RT 回写到 results.jsonl。"""
    if not RESULTS.exists() or not rt:
        return
    lines = RESULTS.read_text(encoding="utf-8").splitlines()
    email_lower = email.strip().lower()
    for i in range(len(lines) - 1, -1, -1):
        try:
            d = json.loads(lines[i])
        except json.JSONDecodeError:
            continue
        if d.get("email", "").strip().lower() == email_lower and not d.get("refresh_token"):
            d["refresh_token"] = rt
            lines[i] = json.dumps(d, ensure_ascii=False)
            break
    RESULTS.write_text("\n".join(lines), encoding="utf-8")


def prepare_input_files(emails: list[dict], input_dir: Path) -> None:
    """为 batch_rt.py 准备输入文件。"""
    input_dir.mkdir(parents=True, exist_ok=True)
    for f in input_dir.iterdir():
        f.unlink()
    for d in emails:
        email = d["email"]
        password = d.get("password", "")
        client_id = d.get("client_id", "14d82eec-204b-4c2f-b7e8-296a70dab67e")
        fname = f"{re.sub(r'[^a-z0-9@._-]+', '_', email.lower())}.txt"
        (input_dir / fname).write_text(
            f"{email}----{password}----{client_id}", encoding="utf-8"
        )


def fetch_rt_batch(
    emails: list[dict],
    timeout_per_account: int = 90,
    start_port: int = 20000,
    display: str = ":98",
) -> dict:
    """使用 Device Code 流程批量获取 RT（更可靠，不需要 localhost 回调）。"""
    if not emails:
        return {"total": 0, "success": 0, "fail": 0}

    import sys
    sys.path.insert(0, str(ROOT / "邮箱注册"))
    from cdp_outlook import _extract_refresh_token_device_code, CDPBrowser, CDPLaunchConfig

    success = 0
    fail = 0
    timeout_count = 0

    for d in emails:
        email = d["email"]
        password = d.get("password", "")
        client_id = d.get("client_id", "14d82eec-204b-4c2f-b7e8-296a70dab67e")
        print(f"[POST-RT] Device Code 获取 RT: {email}")

        cfg = CDPLaunchConfig(browser_type="chrome", proxy="", headless=True)
        browser = CDPBrowser(cfg)
        browser.start()
        try:
            rt = _extract_refresh_token_device_code(
                browser, email, client_id,
                password=password, proxy_url="",
                timeout=timeout_per_account,
            )
            if rt and len(rt) > 20:
                write_back_rt(email, rt)
                # Save to RT_DIR
                fname = re.sub(r'[^a-z0-9@._-]+', '_', email.lower()) + ".txt"
                (RT_DIR / fname).write_text(
                    f"{email}----{password}----{client_id}----{rt}",
                    encoding="utf-8"
                )
                success += 1
                print(f"[POST-RT] ✅ {email}: RT 获取成功")
            else:
                fail += 1
                print(f"[POST-RT] ❌ {email}: RT 获取失败")
        except Exception as e:
            fail += 1
            print(f"[POST-RT] ❌ {email}: {e}")
        finally:
            try:
                browser.stop()
            except Exception:
                pass

    return {
        "total": len(emails),
        "success": success,
        "timeout": timeout_count,
        "fail": fail,
        "output": f"Device Code flow: {success}/{len(emails)} succeeded",
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="注册后自动获取 RT")
    parser.add_argument("--limit", type=int, default=20, help="最多处理几个")
    parser.add_argument("--timeout", type=int, default=90, help="每个邮箱超时秒数")
    parser.add_argument("--start-port", type=int, default=20000)
    parser.add_argument("--display", default=":98")
    args = parser.parse_args()

    emails = find_emails_without_rt(args.limit)
    if not emails:
        print("[POST-RT] 所有邮箱已有 RT，无需处理")
        return 0

    print(f"[POST-RT] 找到 {len(emails)} 个邮箱需要获取 RT")
    result = fetch_rt_batch(emails, args.timeout, args.start_port, args.display)
    print(f"[POST-RT] 完成: {result['success']}/{result['total']} 成功, "
          f"{result.get('timeout', 0)} 超时, {result.get('fail', 0)} 失败")
    # 清理 RT 提取过程中残留的浏览器孤儿进程
    return 0 if result["success"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
