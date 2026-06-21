#!/usr/bin/env python3
"""
观察被锁定账号的 Device Code 流程，逐步截图记录页面状态。
用来理解微软风控解除流程。
"""
import sys, os, time, logging, json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "邮箱注册"))
os.environ["DISPLAY"] = ":98"

SCREENSHOT_DIR = ROOT / "runtime_outlook" / "debug_screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("debug_dc")

from cdp_outlook import CDPBrowser, CDPLaunchConfig
from proxy_utils import parse_proxy

def main():
    # 使用一个已知被锁定的三凭证账号
    test_email = "clarkharpk8qm7p96pvsj8f43@outlook.com"
    test_password = "UW4MLH5%+2!UEkeu5t"
    client_id = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
    
    tenant = "consumers"
    scopes = "offline_access openid profile https://graph.microsoft.com/User.Read https://graph.microsoft.com/Mail.Read"
    device_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode"
    
    # Step 1: 请求 Device Code
    import requests
    logger.info("请求 Device Code...")
    resp = requests.post(device_url, data={"client_id": client_id, "scope": scopes}, timeout=20)
    dc = resp.json()
    user_code = dc["user_code"]
    device_code = dc["device_code"]
    verification_uri = dc.get("verification_uri") or dc.get("verification_url") or "https://www.microsoft.com/link"
    verification_uri_complete = dc.get("verification_uri_complete", "")
    
    logger.info(f"user_code: {user_code}")
    logger.info(f"verification_uri: {verification_uri}")
    logger.info(f"verification_uri_complete: {verification_uri_complete}")
    
    target_url = verification_uri_complete if verification_uri_complete else verification_uri
    
    # Step 2: 启动浏览器
    logger.info("启动 CDP 浏览器...")
    cfg = CDPLaunchConfig(browser_type="chrome", headless=True)
    browser = CDPBrowser(cfg)
    browser.launch()
    
    step = 0
    def screenshot(label):
        nonlocal step
        step += 1
        fname = f"{step:02d}_{label}.png"
        fpath = SCREENSHOT_DIR / fname
        try:
            browser.screenshot(str(fpath))
            logger.info(f"📸 截图: {fname}  URL: {browser.get_url()[:100]}")
        except Exception as e:
            logger.warning(f"截图失败: {e}")
    
    try:
        # 导航到验证页
        logger.info(f"导航到: {target_url}")
        browser.navigate(target_url, wait_for_load=True, timeout=30)
        time.sleep(3)
        screenshot("01_device_code_page")
        
        # 输入 user_code
        logger.info(f"输入 user_code: {user_code}")
        fill = browser.evaluate(f"""(() => {{
            const inputs = document.querySelectorAll('input[type="text"], input[type="tel"], input[name*="code"], input[id*="code"], input[id*="otc"]');
            for (const inp of inputs) {{
                if (inp.offsetParent !== null && inp.offsetWidth > 30) {{
                    inp.focus();
                    inp.value = '';
                    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    nativeSetter.call(inp, '{user_code}');
                    inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                    inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return 'filled';
                }}
            }}
            return 'no_input';
        }})()""")
        logger.info(f"code填写: {fill}")
        time.sleep(1)
        
        # 点击 Next
        browser.evaluate("""(() => {
            const btns = document.querySelectorAll('button, input[type=submit], [role=button]');
            for (const b of btns) {
                const t = (b.textContent || b.value || '').toLowerCase().trim();
                if (t.includes('next') || t.includes('submit') || t.includes('continue'))
                { b.click(); return 'clicked:' + t; }
            }
            const idBtn = document.getElementById('idSIButton9');
            if (idBtn) { idBtn.click(); return 'idSIButton9'; }
            return 'no_btn';
        })()""")
        time.sleep(3)
        screenshot("02_after_code_submit")
        
        # 检查页面状态
        body = browser.get_body_text().lower()
        url = browser.get_url()
        logger.info(f"URL: {url}")
        logger.info(f"Body(前200): {body[:200]}")
        
        # 输入邮箱
        logger.info(f"输入邮箱: {test_email}")
        fill = browser.evaluate(f"""(() => {{
            const inputs = document.querySelectorAll('input[name="loginfmt"], input[type="email"], #i0116');
            for (const inp of inputs) {{
                if (inp.offsetParent !== null && inp.offsetWidth > 30) {{
                    inp.focus();
                    inp.value = '';
                    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    nativeSetter.call(inp, '{test_email}');
                    inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                    inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return 'filled';
                }}
            }}
            return 'no_input';
        }})()""")
        logger.info(f"邮箱填写: {fill}")
        time.sleep(1)
        
        # 点击 Next
        browser.evaluate("""(() => {
            const btns = document.querySelectorAll('button, input[type=submit], [role=button]');
            for (const b of btns) {
                const t = (b.textContent || b.value || '').toLowerCase().trim();
                if (t.includes('next') || t.includes('submit'))
                { b.click(); return 'clicked:' + t; }
            }
            return 'no_btn';
        })()""")
        time.sleep(3)
        screenshot("03_after_email_submit")
        
        body = browser.get_body_text().lower()
        url = browser.get_url()
        logger.info(f"URL: {url}")
        logger.info(f"Body(前300): {body[:300]}")
        
        # 输入密码
        logger.info("输入密码...")
        fill = browser.evaluate(f"""(() => {{
            const inputs = document.querySelectorAll('input[type="password"]');
            for (const inp of inputs) {{
                if (inp.offsetParent !== null && inp.offsetWidth > 30) {{
                    inp.focus();
                    inp.value = '';
                    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    nativeSetter.call(inp, '{test_password}');
                    inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                    inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return 'filled';
                }}
            }}
            return 'no_input';
        }})()""")
        logger.info(f"密码填写: {fill}")
        time.sleep(1)
        
        # 点击 Sign in
        browser.evaluate("""(() => {
            const btns = document.querySelectorAll('button, input[type=submit], [role=button]');
            for (const b of btns) {
                const t = (b.textContent || b.value || '').toLowerCase().trim();
                if (t.includes('sign in') || t.includes('next') || t.includes('登录'))
                { b.click(); return 'clicked:' + t; }
            }
            return 'no_btn';
        })()""")
        time.sleep(5)
        screenshot("04_after_password_submit")
        
        body = browser.get_body_text().lower()
        url = browser.get_url()
        logger.info(f"URL: {url}")
        logger.info(f"Body(前500): {body[:500]}")
        
        # 现在观察微软风控页面
        # 逐帧观察，每2秒截图一次，最多60秒
        for i in range(30):
            time.sleep(2)
            body = browser.get_body_text().lower()
            url = browser.get_url()
            
            # 检测关键页面
            if "selectprooftype" in url.lower() or "proof" in url.lower():
                screenshot(f"05_prooftype_page_{i}")
                logger.info(f"🔑 发现 Proof 页面! URL: {url}")
                logger.info(f"Body: {body[:500]}")
                
                # 获取页面上所有可点击元素
                elements = browser.evaluate("""(() => {
                    const results = [];
                    const all = document.querySelectorAll('button, a, input, [role=button], [role=radio], [role=listbox], [role=option], label, div[class*="proof"], div[class*="tile"], span');
                    for (const el of all) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 20 && r.height > 10 && r.top > 0) {
                            results.push({
                                tag: el.tagName,
                                text: (el.textContent || el.value || '').trim().substring(0, 80),
                                id: el.id,
                                class: el.className.substring(0, 60),
                                role: el.getAttribute('role') || '',
                                type: el.getAttribute('type') || '',
                                rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}
                            });
                        }
                    }
                    return JSON.stringify(results.slice(0, 30));
                })()""")
                logger.info(f"页面元素: {elements[:2000]}")
                
            elif "account" in body and ("locked" in body or "suspended" in body or "verify" in body):
                screenshot(f"06_locked_or_verify_{i}")
                logger.info(f"🔒 锁定/验证页面: {body[:300]}")
                
            elif "recovery" in body or "proofs" in url.lower():
                screenshot(f"07_recovery_{i}")
                logger.info(f"🔐 恢复页面: {body[:300]}")
                
            elif "error" in body or "doesn't exist" in body or "incorrect" in body:
                screenshot(f"08_error_{i}")
                logger.info(f"❌ 错误页面: {body[:300]}")
                break
                
            elif "kmsi" in url.lower() or "stay signed" in body or "保持登录" in body:
                screenshot(f"09_kmsi_{i}")
                logger.info("✅ 保持登录页面 — 账号正常!")
                break
                
            elif "consent" in url.lower() or "permission" in body:
                screenshot(f"10_consent_{i}")
                logger.info("✅ Consent页面 — 账号正常!")
                break
            else:
                if i % 5 == 0:
                    screenshot(f"page_{i:02d}")
                    logger.info(f"页面{i}: URL={url[:80]} body={body[:100]}")
        
        logger.info("观察完成！截图保存在: runtime_outlook/debug_screenshots/")
        
    finally:
        browser.close()

if __name__ == "__main__":
    main()
