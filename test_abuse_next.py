#!/usr/bin/env python3
"""快速测试：Abuse 页面点 Next 后截图观察"""
import sys, os, time, logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "邮箱注册"))
os.environ["DISPLAY"] = ":98"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

from cdp_outlook import CDPBrowser, CDPLaunchConfig
from unlock_and_fetch_rt import _patched_extract_refresh_token_device_code

SHOT_DIR = ROOT / "runtime_outlook" / "abuse_screenshots"
SHOT_DIR.mkdir(parents=True, exist_ok=True)

# 用第一个锁定账号测试
test_email = "brookshaze1zil97f7qv5j342a@outlook.com"
test_password = "test123"  # 密码不重要，关键是观察 Abuse 页面
test_cid = "14d82eec-204b-4c2f-b7e8-296a70dab67e"

import requests
tenant = "consumers"
scopes = "offline_access openid profile https://graph.microsoft.com/User.Read https://graph.microsoft.com/Mail.Read"
device_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode"

resp = requests.post(device_url, data={"client_id": test_cid, "scope": scopes}, timeout=20)
dc = resp.json()
user_code = dc.get("user_code", "")
print(f"user_code: {user_code}")

cfg = CDPLaunchConfig(browser_type="chrome", headless=True)
browser = CDPBrowser(cfg)
browser.launch()

try:
    browser.navigate("https://www.microsoft.com/link", wait_for_load=True, timeout=30)
    time.sleep(3)
    
    # 填入 user_code
    browser.evaluate(f"""(() => {{
        const inputs = document.querySelectorAll('input[type="text"], input[type="tel"], input[name*="code"], input[id*="code"]');
        for (const inp of inputs) {{
            if (inp.offsetParent !== null && inp.offsetWidth > 30) {{
                inp.focus(); inp.value = '';
                const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                ns.call(inp, '{user_code}');
                inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                return 'filled';
            }}
        }}
        return 'no_input';
    }})()""")
    time.sleep(1)
    browser.evaluate("""(() => {
        const btns = document.querySelectorAll('button, input[type=submit], [role=button]');
        for (const b of btns) {
            const t = (b.textContent || b.value || '').toLowerCase().trim();
            if (t.includes('allow') || t.includes('next') || t.includes('submit'))
            { b.click(); return 'clicked'; }
        }
        return 'no_btn';
    })()""")
    time.sleep(3)
    
    # 填入邮箱
    browser.evaluate(f"""(() => {{
        const inp = document.querySelector('input[name="loginfmt"], input[type="email"], #i0116');
        if (inp && inp.offsetParent !== null) {{
            inp.focus(); inp.value = '';
            const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            ns.call(inp, '{test_email}');
            inp.dispatchEvent(new Event('input', {{bubbles: true}}));
            const btns = document.querySelectorAll('button, input[type=submit], [role=button]');
            for (const b of btns) {{
                const t = (b.textContent || b.value || '').toLowerCase().trim();
                if (t.includes('next') || t.includes('submit')) {{ b.click(); return 'clicked'; }}
            }}
            return 'filled';
        }}
        return 'no_input';
    }})()""")
    time.sleep(3)
    
    # 填入密码（任意密码，目的是触发 Abuse 页面）
    browser.evaluate(f"""(() => {{
        const inp = document.querySelector('input[type="password"]');
        if (inp && inp.offsetParent !== null) {{
            inp.focus(); inp.value = '';
            const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            ns.call(inp, '{test_password}');
            inp.dispatchEvent(new Event('input', {{bubbles: true}}));
            const btns = document.querySelectorAll('button, input[type=submit], [role=button]');
            for (const b of btns) {{
                const t = (b.textContent || b.value || '').toLowerCase().trim();
                if (t.includes('sign in') || t.includes('next')) {{ b.click(); return 'clicked'; }}
            }}
            return 'filled';
        }}
        return 'no_input';
    }})()""")
    time.sleep(5)
    
    # 检查是否到达 Abuse 页面
    url = browser.get_url().lower()
    print(f"URL after password: {url[:120]}")
    
    if "abuse" in url:
        print("✅ 到达 Abuse 页面！截图...")
        browser.save_screenshot(str(SHOT_DIR / "01_abuse_page.png"))
        
        # 点击 Next 按钮
        result = browser.evaluate("""(() => {
            const btns = document.querySelectorAll('button, input[type=submit], [role=button]');
            for (const b of btns) {
                const t = (b.textContent || b.value || '').toLowerCase().trim();
                if (t === 'next' || t === '下一步' || t.includes('continue'))
                { b.click(); return 'clicked:' + t; }
            }
            const idBtn = document.getElementById('idSIButton9');
            if (idBtn) { idBtn.click(); return 'idSIButton9'; }
            return 'no_btn';
        })()""")
        print(f"Next 按钮结果: {result}")
        time.sleep(5)
        
        # 截图 Next 后的页面
        browser.save_screenshot(str(SHOT_DIR / "02_after_next.png"))
        url2 = browser.get_url().lower()
        body2 = browser.get_body_text()[:500]
        print(f"URL after Next: {url2[:120]}")
        print(f"Body preview: {body2[:300]}")
        
        # 再等 5 秒看是否有变化
        time.sleep(5)
        browser.save_screenshot(str(SHOT_DIR / "03_after_wait.png"))
        url3 = browser.get_url().lower()
        body3 = browser.get_body_text()[:500]
        print(f"URL after wait: {url3[:120]}")
        print(f"Body preview: {body3[:300]}")
    else:
        print(f"❌ 未到达 Abuse 页面，当前 URL: {url[:100]}")
        browser.save_screenshot(str(SHOT_DIR / "00_not_abuse.png"))

finally:
    browser.close()
    print(f"\n截图保存在: {SHOT_DIR}")
