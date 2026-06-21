#!/usr/bin/env python3
"""
观察被锁定账号点击 Next 后的完整解锁流程。
"""
import sys, os, time, logging, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "邮箱注册"))
os.environ["DISPLAY"] = ":98"

SCREENSHOT_DIR = ROOT / "runtime_outlook" / "debug_screenshots2"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("debug_unlock")

from cdp_outlook import CDPBrowser, CDPLaunchConfig

def ss(browser, label, step_counter):
    step_counter[0] += 1
    fname = f"{step_counter[0]:02d}_{label}.png"
    fpath = SCREENSHOT_DIR / fname
    try:
        browser.screenshot(str(fpath))
        logger.info(f"📸 {fname}  URL: {browser.get_url()[:120]}")
    except Exception as e:
        logger.warning(f"截图失败: {e}")

def get_page_info(browser):
    url = browser.get_url()
    body = browser.get_body_text().lower()
    return url, body

def click_button(browser, keywords):
    """点击包含指定关键词的按钮"""
    result = browser.evaluate(f"""(() => {{
        const btns = document.querySelectorAll('button, input[type=submit], [role=button], a[href]');
        for (const b of btns) {{
            const t = (b.textContent || b.value || '').toLowerCase().trim();
            const keywords = {json.dumps(keywords)};
            for (const kw of keywords) {{
                if (t.includes(kw)) {{ b.click(); return 'clicked:' + t.substring(0,40); }}
            }}
        }}
        return null;
    }})()""")
    return result

def get_visible_elements(browser):
    """获取页面上所有可见的可交互元素"""
    return browser.evaluate("""(() => {
        const results = [];
        const all = document.querySelectorAll('button, a, input, select, textarea, [role=button], [role=radio], [role=checkbox], [role=listbox], [role=option], label, div[class*="tile"]');
        for (const el of all) {
            const r = el.getBoundingClientRect();
            if (r.width > 20 && r.height > 10 && r.top > 0 && r.top < 800 && el.offsetParent !== null) {
                results.push({
                    tag: el.tagName,
                    text: (el.textContent || el.value || '').trim().substring(0, 80),
                    id: el.id,
                    type: el.getAttribute('type') || '',
                    name: el.getAttribute('name') || '',
                    role: el.getAttribute('role') || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}
                });
            }
        }
        return results.slice(0, 40);
    })()""")

def main():
    test_email = "clarkharpk8qm7p96pvsj8f43@outlook.com"
    test_password = "UW4MLH5%+2!UEkeu5t"
    client_id = "14d82eec-204b-4c2f-b7e8-296a70dab67e"

    tenant = "consumers"
    scopes = "offline_access openid profile https://graph.microsoft.com/User.Read https://graph.microsoft.com/Mail.Read"
    device_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode"

    import requests
    logger.info("请求 Device Code...")
    resp = requests.post(device_url, data={"client_id": client_id, "scope": scopes}, timeout=20)
    dc = resp.json()
    user_code = dc["user_code"]
    verification_uri = dc.get("verification_uri") or "https://www.microsoft.com/link"
    verification_uri_complete = dc.get("verification_uri_complete", "")
    target_url = verification_uri_complete if verification_uri_complete else verification_uri
    logger.info(f"user_code: {user_code}")

    cfg = CDPLaunchConfig(browser_type="chrome", headless=True)
    browser = CDPBrowser(cfg)
    browser.launch()
    step = [0]

    try:
        browser.navigate(target_url, wait_for_load=True, timeout=30)
        time.sleep(3)
        ss(browser, "device_code_page", step)

        # 输入 user_code
        browser.evaluate(f"""(() => {{
            const inputs = document.querySelectorAll('input[type="text"], input[type="tel"], input[name*="code"], input[id*="code"], input[id*="otc"]');
            for (const inp of inputs) {{
                if (inp.offsetParent !== null && inp.offsetWidth > 30) {{
                    inp.focus(); inp.value = '';
                    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    nativeSetter.call(inp, '{user_code}');
                    inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                    inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return 'filled';
                }}
            }}
        }})()""")
        time.sleep(1)
        click_button(browser, ["next", "submit", "continue", "allow access", "allow"])
        time.sleep(3)
        ss(browser, "after_code", step)

        # 输入邮箱
        browser.evaluate(f"""(() => {{
            const inputs = document.querySelectorAll('input[name="loginfmt"], input[type="email"], #i0116');
            for (const inp of inputs) {{
                if (inp.offsetParent !== null && inp.offsetWidth > 30) {{
                    inp.focus(); inp.value = '';
                    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    nativeSetter.call(inp, '{test_email}');
                    inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                    inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return 'filled';
                }}
            }}
        }})()""")
        time.sleep(1)
        click_button(browser, ["next", "submit"])
        time.sleep(3)
        ss(browser, "after_email", step)

        # 输入密码
        browser.evaluate(f"""(() => {{
            const inputs = document.querySelectorAll('input[type="password"]');
            for (const inp of inputs) {{
                if (inp.offsetParent !== null && inp.offsetWidth > 30) {{
                    inp.focus(); inp.value = '';
                    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    nativeSetter.call(inp, '{test_password}');
                    inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                    inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return 'filled';
                }}
            }}
        }})()""")
        time.sleep(1)
        click_button(browser, ["sign in", "next", "登录"])
        time.sleep(5)
        ss(browser, "after_password", step)

        # 现在应该到了 Abuse 锁定页面
        url, body = get_page_info(browser)
        logger.info(f"当前页面: {url}")
        logger.info(f"Body: {body[:300]}")

        # 逐步点击 Next 深入解锁流程
        for phase in range(15):
            url, body = get_page_info(browser)
            logger.info(f"\n{'='*60}")
            logger.info(f"Phase {phase}: URL={url[:120]}")
            logger.info(f"Body(200): {body[:200]}")

            # 获取所有可交互元素
            elements = get_visible_elements(browser)
            logger.info(f"可交互元素({len(elements)}):")
            for el in elements[:15]:
                logger.info(f"  [{el['tag']}] text='{el['text']}' id='{el['id']}' type='{el['type']}' name='{el['name']}' role='{el['role']}' rect=({el['rect']['x']},{el['rect']['y']},{el['rect']['w']}x{el['rect']['h']})")

            ss(browser, f"phase_{phase}", step)

            # 自动点击下一步
            clicked = click_button(browser, ["next", "continue", "submit", "yes", "send code", "confirm", "继续", "下一步", "确认", "发送"])
            logger.info(f"点击结果: {clicked}")

            if clicked is None:
                # 没有按钮可点，检查是否有输入框
                has_input = browser.evaluate("""(() => {
                    const inputs = document.querySelectorAll('input[type="text"], input[type="tel"], input[type="email"], input[type="number"], textarea');
                    for (const inp of inputs) {
                        if (inp.offsetParent !== null && inp.offsetWidth > 30) return true;
                    }
                    return false;
                })()""")
                if has_input:
                    logger.info("有输入框但无按钮，可能需要手动输入")
                    ss(browser, f"input_needed_{phase}", step)
                    break
                else:
                    logger.info("无按钮也无输入框，等待...")
                    time.sleep(3)
                    continue

            time.sleep(4)
            url2, body2 = get_page_info(browser)
            if url2 == url and body2[:100] == body[:100]:
                logger.info("页面未变化，等待...")
                time.sleep(3)

        logger.info("\n观察完成！")

    finally:
        browser.close()

if __name__ == "__main__":
    main()
