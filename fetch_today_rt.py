#!/usr/bin/env python3
"""只为今天注册的账号获取RT (Device Code流程)"""
import sys, os, time, logging, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "邮箱注册"))
os.environ["DISPLAY"] = ":98"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("fetch_today_rt")

from cdp_outlook import _extract_refresh_token_device_code, CDPBrowser, CDPLaunchConfig

rt_dir = ROOT / "runtime_outlook" / "rt_tokens"
rt_dir.mkdir(parents=True, exist_ok=True)
results_file = ROOT / "runtime_outlook" / "results.jsonl"
TODAY = "2026-06-20"

def get_today_accounts_no_rt():
    """获取今天注册成功但没有RT的账号"""
    accounts = []
    for line in results_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except:
            continue
        if (d.get("success") and d.get("ts", "").startswith(TODAY)
                and not (d.get("refresh_token") and len(d.get("refresh_token", "")) > 20)):
            accounts.append(d)
    return accounts

def write_back_rt(email, rt):
    lines = results_file.read_text(encoding="utf-8").splitlines()
    email_lower = email.strip().lower()
    for i in range(len(lines) - 1, -1, -1):
        try:
            d = json.loads(lines[i])
        except:
            continue
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
    accounts = get_today_accounts_no_rt()
    if not accounts:
        print("今天所有账号都已有RT ✅")
        return 0

    print(f"今天有 {len(accounts)} 个账号需要获取RT")
    for a in accounts:
        print(f"  - {a['email']}")
    print()

    success = 0
    fail = 0
    failed_emails = []

    for i, acc in enumerate(accounts):
        email = acc["email"]
        password = acc.get("password", "")
        client_id = acc.get("client_id", "14d82eec-204b-4c2f-b7e8-296a70dab67e")

        print(f"\n[{i+1}/{len(accounts)}] {email} ...", flush=True)

        cfg = CDPLaunchConfig(browser_type="chrome", headless=True)
        browser = CDPBrowser(cfg)
        browser.launch()

        try:
            rt = _extract_refresh_token_device_code(
                browser, email, client_id,
                password=password, proxy_url="",
                timeout=120
            )
            if rt:
                print(f"  ✅ RT获取成功: {rt[:40]}...")
                write_back_rt(email, rt)
                save_cred(email, password, client_id, rt)
                success += 1
            else:
                print(f"  ❌ RT获取失败")
                fail += 1
                failed_emails.append(email)
        except Exception as e:
            print(f"  ❌ 异常: {e}")
            fail += 1
            failed_emails.append(email)
        finally:
            try:
                browser.close()
            except:
                pass

        # 每个账号之间等2秒
        if i < len(accounts) - 1:
            time.sleep(2)

    print(f"\n{'='*60}")
    print(f"完成: {success}/{len(accounts)} 成功, {fail} 失败")
    if failed_emails:
        print(f"失败账号: {failed_emails}")
    return 0 if success > 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
