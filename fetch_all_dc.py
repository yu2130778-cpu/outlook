#!/usr/bin/env python3
"""批量 Device Code 获取RT（跳过被锁账号）"""
import sys, os, json, time, logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "邮箱注册"))
os.environ.setdefault("DISPLAY", ":98")
os.environ["SUB_PROXY_FAST_START"] = "1"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", force=True)
log = logging.getLogger()

from cdp_outlook import _extract_refresh_token_device_code, _extract_refresh_token, CDPBrowser, CDPLaunchConfig, kill_orphan_chrome_processes
from proxy_utils import parse_proxy

def get_proxy():
    try:
        from subscription_proxy import get_manager
        m = get_manager()
        m.start()
        time.sleep(2)
        return m.proxy_url or ""
    except:
        return ""

def find_accounts(limit=50):
    rt_dir = ROOT / "runtime_outlook" / "rt_tokens"
    have = set()
    for f in rt_dir.glob("*.txt"):
        parts = f.read_text(encoding="utf-8").strip().split("----")
        if len(parts) >= 4 and parts[3].strip() and len(parts[3].strip()) > 20:
            have.add(parts[0].strip().lower())

    results_f = ROOT / "runtime_outlook" / "results.jsonl"
    accounts = []
    for line in results_f.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except:
            continue
        if not d.get("success") or not d.get("email"):
            continue
        if d["email"].strip().lower() in have:
            continue
        if d.get("refresh_token") and len(d["refresh_token"]) > 20:
            continue
        accounts.append(d)
    return accounts[-limit:]  # newest last

def save_credential(email, pwd, cid, rt):
    cred_dir = ROOT / "runtime_outlook" / "rt_tokens"
    cred_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "@._-" else "_" for c in email.lower())
    path = cred_dir / f"{safe}.txt"
    path.write_text(f"{email}----{pwd}----{cid}----{rt}", encoding="utf-8")
    return str(path)

def write_back(email, rt):
    p = ROOT / "runtime_outlook" / "results.jsonl"
    lines = p.read_text(encoding="utf-8").splitlines()
    for i in range(len(lines)-1, -1, -1):
        try:
            d = json.loads(lines[i])
        except:
            continue
        if d.get("email","").strip().lower() == email.strip().lower() and not d.get("refresh_token"):
            d["refresh_token"] = rt
            lines[i] = json.dumps(d, ensure_ascii=False)
            break
    p.write_text("\n".join(lines), encoding="utf-8")

def fetch_one(acct, proxy_url):
    email = acct["email"]
    pwd = acct.get("password","")
    cid = acct.get("client_id","14d82eec-204b-4c2f-b7e8-296a70dab67e")

    pi = parse_proxy(proxy_url) if proxy_url else None
    chrome_p = pi.chrome_proxy if pi else ""
    auth_p = pi.url if pi and pi.has_auth else ""

    cfg = CDPLaunchConfig(browser_type="chrome", proxy=chrome_p, headless=True)
    browser = CDPBrowser(cfg)
    browser.launch()
    try:
        rt = _extract_refresh_token_device_code(browser, email, cid, password=pwd, proxy_url=auth_p or chrome_p)
        if not rt:
            rt = _extract_refresh_token(browser, email, cid, password=pwd, proxy_url=auth_p or chrome_p)
        if rt:
            save_credential(email, pwd, cid, rt)
            write_back(email, rt)
            return rt
        return None
    finally:
        browser.close()

def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    proxy = get_proxy()
    if proxy:
        log.info("代理: %s...", proxy[:40])

    accts = find_accounts(limit)
    if not accts:
        log.info("所有账号已有RT")
        return 0

    log.info("找到 %d 个账号需要获取RT", len(accts))
    ok = 0
    for i, a in enumerate(accts):
        log.info("\n[%d/%d] %s", i+1, len(accts), a["email"])
        try:
            rt = fetch_one(a, proxy)
            if rt:
                ok += 1
                log.info("  ✅ RT: %s...", rt[:30])
            else:
                log.info("  ❌ 失败")
        except Exception as e:
            log.info("  ❌ 异常: %s", str(e)[:100])
        # Clean orphan browsers between accounts
        try:
            kill_orphan_chrome_processes()
        except:
            pass

    log.info("\n完成: %d/%d 成功", ok, len(accts))
    return 0 if ok > 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
