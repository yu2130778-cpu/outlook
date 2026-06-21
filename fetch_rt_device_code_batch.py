#!/usr/bin/env python3
"""使用 Device Code 流程批量获取 refresh_token"""
import json, sys, os, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "邮箱注册"))
os.environ["SUB_PROXY_FAST_START"] = "1"

from cdp_outlook import _extract_refresh_token_device_code, _extract_refresh_token, CDPBrowser, CDPLaunchConfig
from proxy_utils import parse_proxy

RESULTS_FILE = ROOT / "runtime_outlook" / "results.jsonl"


def get_proxy():
    """获取代理"""
    try:
        from subscription_proxy import get_manager
        m = get_manager()
        if m and m.is_running:
            return m.proxy_url or ""
    except:
        pass
    return ""


def find_accounts_without_rt(limit=5):
    """找没有RT的账号"""
    if not RESULTS_FILE.exists():
        return []
    have_rt = set()
    for f in (ROOT / "runtime_outlook" / "rt_tokens").glob("*.txt"):
        content = f.read_text(encoding="utf-8").strip()
        parts = content.split("----")
        if len(parts) >= 4 and parts[3].strip() and len(parts[3].strip()) > 20:
            have_rt.add(parts[0].strip().lower())

    rows = []
    for line in RESULTS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except:
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


def write_back_rt(email, rt):
    """把RT写回results.jsonl"""
    if not RESULTS_FILE.exists() or not rt:
        return
    lines = RESULTS_FILE.read_text(encoding="utf-8").splitlines()
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
    RESULTS_FILE.write_text("\n".join(lines), encoding="utf-8")


def save_credential(email, password, client_id, rt):
    """保存四凭证到文件"""
    cred_dir = ROOT / "runtime_outlook" / "rt_tokens"
    cred_dir.mkdir(parents=True, exist_ok=True)
    safe_name = email.replace("@", "_at_").replace(".", "_")
    cred_file = cred_dir / f"{safe_name}.txt"
    line = f"{email}----{password}----{client_id}----{rt}"
    cred_file.write_text(line, encoding="utf-8")
    return str(cred_file)


def fetch_rt_for_account(account, proxy_url=""):
    """为单个账号获取RT"""
    email = account["email"]
    password = account.get("password", "")
    client_id = account.get("client_id", "14d82eec-204b-4c2f-b7e8-296a70dab67e")
    
    print(f"\n{'='*60}")
    print(f">>> 获取RT: {email}")
    print(f"    密码: {password[:15]}...")
    
    # 解析代理
    proxy_info = parse_proxy(proxy_url) if proxy_url else None
    chrome_proxy = proxy_info.chrome_proxy if proxy_info else ""
    auth_proxy = proxy_info.url if proxy_info and proxy_info.has_auth else ""
    
    cfg = CDPLaunchConfig(browser_type="chrome", proxy=chrome_proxy, headless=True)
    browser = CDPBrowser(cfg)
    browser.launch()
    
    try:
        # 方法1: Device Code
        print(f"    尝试方法1: Device Code...")
        rt = _extract_refresh_token_device_code(
            browser, email, client_id,
            password=password, proxy_url=auth_proxy or chrome_proxy
        )
        
        # 方法2: Authorization Code (如果Device Code失败)
        if not rt:
            print(f"    Device Code未获取到RT，尝试方法2: Authorization Code...")
            rt = _extract_refresh_token(
                browser, email, client_id,
                password=password, proxy_url=auth_proxy or chrome_proxy
            )
        
        if rt:
            print(f"    ✅ RT获取成功: {rt[:30]}...")
            # 写回results.jsonl
            write_back_rt(email, rt)
            # 保存四凭证文件
            cred_path = save_credential(email, password, client_id, rt)
            print(f"    四凭证已保存: {cred_path}")
            return True
        else:
            print(f"    ❌ RT获取失败（两种方法都不行）")
            return False
    except Exception as e:
        print(f"    ❌ 异常: {e}")
        return False
    finally:
        browser.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Device Code 批量获取RT")
    parser.add_argument("--limit", type=int, default=5, help="最多处理几个")
    parser.add_argument("--proxy", type=str, default="", help="代理URL")
    args = parser.parse_args()
    
    proxy = args.proxy or get_proxy()
    if proxy:
        print(f"使用代理: {proxy[:50]}...")
    
    accounts = find_accounts_without_rt(args.limit)
    if not accounts:
        print("所有账号已有RT，无需处理")
        return 0
    
    print(f"找到 {len(accounts)} 个账号需要获取RT")
    
    success = 0
    for account in accounts:
        if fetch_rt_for_account(account, proxy):
            success += 1
    
    print(f"\n{'='*60}")
    print(f"完成: {success}/{len(accounts)} 成功获取RT")
    return 0 if success > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
