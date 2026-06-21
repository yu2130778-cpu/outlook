#!/usr/bin/env python3
"""Test Device Code flow for a single account"""
import sys, os, time, logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '邮箱注册')
os.environ['DISPLAY'] = ':98'
os.environ['SUB_PROXY_FAST_START'] = '1'

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

from cdp_outlook import _extract_refresh_token_device_code, CDPBrowser, CDPLaunchConfig
from proxy_utils import parse_proxy
from subscription_proxy import get_manager

# Get proxy
pm = get_manager()
proxy_url = pm.proxy_url if pm and pm.is_running else ""
print(f"Proxy: {proxy_url[:60] if proxy_url else 'none'}")

proxy_info = parse_proxy(proxy_url) if proxy_url else None
chrome_proxy = proxy_info.chrome_proxy if proxy_info else ""
auth_proxy = proxy_info.url if proxy_info and proxy_info.has_auth else ""

# Get first account without RT
import json
from pathlib import Path
results_file = Path('runtime_outlook/results.jsonl')
accounts = []
for line in results_file.read_text().splitlines():
    if not line.strip(): continue
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        continue
    if d.get('success') and d.get('email') and not d.get('refresh_token'):
        accounts.append(d)
if not accounts:
    print("No accounts without RT")
    sys.exit(1)

acct = accounts[0]
email = acct['email']
password = acct['password']
client_id = acct.get('client_id', '14d82eec-204b-4c2f-b7e8-296a70dab67e')

print(f"\nTesting: {email}")
print(f"Password: {password[:15]}...")

cfg = CDPLaunchConfig(browser_type='chrome', proxy=chrome_proxy, headless=False)
browser = CDPBrowser(cfg)
browser.launch()

try:
    rt = _extract_refresh_token_device_code(
        browser, email, client_id,
        password=password, proxy_url=auth_proxy or chrome_proxy,
        timeout=120
    )
    if rt:
        print(f"\n✅ RT获取成功: {rt[:40]}...")
    else:
        print(f"\n❌ RT获取失败")
finally:
    browser.close()
