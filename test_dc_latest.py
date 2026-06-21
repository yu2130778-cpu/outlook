#!/usr/bin/env python3
"""测试最新注册账号的 Device Code RT 获取"""
import sys, os, time, logging, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "邮箱注册"))
os.environ["DISPLAY"] = ":98"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

from cdp_outlook import _extract_refresh_token_device_code, _extract_refresh_token, CDPBrowser, CDPLaunchConfig
from proxy_utils import parse_proxy
from subscription_proxy import get_manager

# 获取代理
proxy_url = ""
try:
    pm = get_manager()
    if pm:
        proxy_url = pm.proxy_url or ""
        pm.switch_to_next_node()
except Exception as e:
    print(f"代理获取失败: {e}")

# 读取最新无RT的账号
results_file = ROOT / "runtime_outlook" / "results.jsonl"
have_rt = set()
rt_dir = ROOT / "runtime_outlook" / "rt_tokens"
rt_dir.mkdir(parents=True, exist_ok=True)
for f in rt_dir.glob("*.txt"):
    parts = f.read_text(encoding="utf-8").strip().split("----")
    if len(parts) >= 4 and parts[3].strip() and len(parts[3].strip()) > 20:
        have_rt.add(parts[0].strip().lower())

accounts = []
for line in reversed(results_file.read_text().splitlines()):
    if not line.strip(): continue
    try: d = json.loads(line)
    except: continue
    if d.get("success") and d.get("email") and not d.get("refresh_token"):
        email = d["email"].strip().lower()
        if email not in have_rt:
            accounts.append(d)
        if len(accounts) >= 3:
            break

if not accounts:
    print("所有账号已有RT")
    sys.exit(0)

print(f"代理: {proxy_url[:50]}...")
print(f"准备测试 {len(accounts)} 个最新注册账号\n")

success = 0
for i, acc in enumerate(accounts):
    email = acc["email"]
    password = acc.get("password", "")
    client_id = acc.get("client_id", "14d82eec-204b-4c2f-b7e8-296a70dab67e")

    print(f"{'='*60}")
    print(f"[{i+1}/{len(accounts)}] {email}")
    print(f"  密码: {password[:15]}...")

    pi = parse_proxy(proxy_url) if proxy_url else None
    chrome_proxy = pi.chrome_proxy if pi else ""
    auth_proxy = pi.url if pi and pi.has_auth else ""

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
            print(f"  ✅ Device Code RT: {rt[:30]}...")
            success += 1
            # 写回 results.jsonl
            lines = results_file.read_text().splitlines()
            for j in range(len(lines) - 1, -1, -1):
                try: d = json.loads(lines[j])
                except: continue
                if d.get("email", "").strip().lower() == email.strip().lower() and not d.get("refresh_token"):
                    d["refresh_token"] = rt
                    lines[j] = json.dumps(d, ensure_ascii=False)
                    break
            results_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            # 保存四凭证
            cred_file = rt_dir / f"{email.replace('@','_').replace('.','_')}.txt"
            cred_file.write_text(f"{email}----{password}----{client_id}----{rt}", encoding="utf-8")
            print(f"  四凭证已保存: {cred_file}")
        else:
            print(f"  ❌ Device Code 未获取到RT")
            # 尝试 Authorization Code
            print(f"  尝试 Authorization Code...")
            rt = _extract_refresh_token(
                browser, email, client_id,
                password=password, proxy_url=auth_proxy or chrome_proxy,
                timeout=60
            )
            if rt:
                print(f"  ✅ AuthCode RT: {rt[:30]}...")
                success += 1
                lines = results_file.read_text().splitlines()
                for j in range(len(lines) - 1, -1, -1):
                    try: d = json.loads(lines[j])
                    except: continue
                    if d.get("email", "").strip().lower() == email.strip().lower() and not d.get("refresh_token"):
                        d["refresh_token"] = rt
                        lines[j] = json.dumps(d, ensure_ascii=False)
                        break
                results_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
                cred_file = rt_dir / f"{email.replace('@','_').replace('.','_')}.txt"
                cred_file.write_text(f"{email}----{password}----{client_id}----{rt}", encoding="utf-8")
            else:
                print(f"  ❌ 两种方法都失败")
    except Exception as e:
        print(f"  ❌ 异常: {e}")
    finally:
        try: browser.close()
        except: pass

print(f"\n{'='*60}")
print(f"完成: {success}/{len(accounts)} 成功获取RT")
