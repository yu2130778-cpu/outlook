#!/usr/bin/env python3
"""批量用 Device Code 流程获取所有无RT账号"""
import sys, os, time, logging, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "邮箱注册"))
os.environ["DISPLAY"] = ":98"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

from cdp_outlook import _extract_refresh_token_device_code, CDPBrowser, CDPLaunchConfig
from proxy_utils import parse_proxy
from subscription_proxy import get_manager

rt_dir = ROOT / "runtime_outlook" / "rt_tokens"
rt_dir.mkdir(parents=True, exist_ok=True)
results_file = ROOT / "runtime_outlook" / "results.jsonl"

def have_rt_set():
    s = set()
    for f in rt_dir.glob("*.txt"):
        parts = f.read_text(encoding="utf-8").strip().split("----")
        if len(parts) >= 4 and parts[3].strip() and len(parts[3].strip()) > 20:
            s.add(parts[0].strip().lower())
    return s

def get_accounts(limit=999):
    have = have_rt_set()
    # Also check results.jsonl for embedded RT
    rows = []
    for line in reversed(results_file.read_text().splitlines()):
        if not line.strip(): continue
        try: d = json.loads(line)
        except: continue
        if d.get("success") and d.get("email"):
            email = d["email"].strip().lower()
            if email in have: continue
            if d.get("refresh_token") and len(d["refresh_token"]) > 20: continue
            rows.append(d)
        if len(rows) >= limit: break
    return rows

def write_back_rt(email, rt):
    lines = results_file.read_text(encoding="utf-8").splitlines()
    email_lower = email.strip().lower()
    for i in range(len(lines) - 1, -1, -1):
        try: d = json.loads(lines[i])
        except: continue
        if d.get("email", "").strip().lower() == email_lower and not d.get("refresh_token"):
            d["refresh_token"] = rt
            lines[i] = json.dumps(d, ensure_ascii=False)
            break
    results_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

def save_cred(email, password, client_id, rt):
    fname = email.replace("@", "_").replace(".", "_") + ".txt"
    f = rt_dir / fname
    f.write_text(f"{email}----{password}----{client_id}----{rt}", encoding="utf-8")
    return f

def main():
    accounts = get_accounts()
    if not accounts:
        print("所有账号已有RT")
        return 0

    print(f"找到 {len(accounts)} 个账号需要获取RT\n")

    proxy_url = ""
    try:
        pm = get_manager()
        if pm:
            proxy_url = pm.proxy_url or ""
            pm.switch_to_next_node()
    except: pass

    pi = parse_proxy(proxy_url) if proxy_url else None
    chrome_proxy = pi.chrome_proxy if pi else ""
    auth_proxy = pi.url if pi and pi.has_auth else ""

    success = 0
    fail = 0
    for i, acc in enumerate(accounts):
        email = acc["email"]
        password = acc.get("password", "")
        client_id = acc.get("client_id", "14d82eec-204b-4c2f-b7e8-296a70dab67e")

        print(f"[{i+1}/{len(accounts)}] {email} ...", end=" ", flush=True)

        cfg = CDPLaunchConfig(browser_type="chrome", proxy=chrome_proxy, headless=True)
        browser = CDPBrowser(cfg)
        browser.launch()

        try:
            rt = _extract_refresh_token_device_code(
                browser, email, client_id,
                password=password, proxy_url=auth_proxy or chrome_proxy,
                timeout=120
            )
            if rt:
                print(f"✅ RT: {rt[:30]}...")
                write_back_rt(email, rt)
                save_cred(email, password, client_id, rt)
                success += 1
            else:
                print(f"❌ 失败")
                fail += 1
        except Exception as e:
            print(f"❌ {e}")
            fail += 1
        finally:
            try: browser.close()
            except: pass

    print(f"\n完成: {success}/{len(accounts)} 成功, {fail} 失败")
    return 0 if success > 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
