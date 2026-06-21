#!/usr/bin/env python3
"""
尝试通过 Arkose Labs press-and-hold CAPTCHA，观察后续页面。
步骤:
1. 请求 Device Code
2. 填入验证码、邮箱、密码
3. 到达 Abuse/locked 页面点 Next
4. 到达 "Press and hold" CAPTCHA 页面
5. 模拟人类行为按压按钮
6. 观察后续页面（可能是 selectProofType / 绑定邮箱 / 输入验证码）
"""
import sys, os, time, logging, json, random, math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "邮箱注册"))
os.environ["DISPLAY"] = ":98"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("press_hold")

from cdp_outlook import CDPBrowser, CDPLaunchConfig

SHOT_DIR = ROOT / "runtime_outlook" / "debug_screenshots3"
SHOT_DIR.mkdir(parents=True, exist_ok=True)
_shot_count = [0]

def screenshot(browser, name):
    _shot_count[0] += 1
    f = SHOT_DIR / f"{_shot_count[0]:02d}_{name}.png"
    browser.screenshot(str(f))
    logger.info("📸 %s  URL: %s", f.name, browser.get_url())
    return f

def get_page_info(browser):
    url = browser.get_url()
    body = browser.get_body_text()
    return url, body

def click_button(browser, keywords):
    return browser.evaluate(f"""(() => {{
        const btns = document.querySelectorAll('button, input[type=submit], [role=button], a');
        for (const b of btns) {{
            const t = (b.textContent || b.value || '').toLowerCase().trim();
            for (const kw of {json.dumps(keywords)}) {{
                if (t.includes(kw)) {{ b.click(); return 'clicked:' + t.substring(0,40); }}
            }}
        }}
        return null;
    }})()""")

def human_mouse_move(browser, target_x, target_y, duration=1.5):
    """模拟人类鼠标移动到目标位置"""
    # 从随机起点开始
    start_x = random.randint(100, 400)
    start_y = random.randint(100, 300)
    
    steps = random.randint(20, 35)
    for i in range(steps + 1):
        t = i / steps
        # 贝塞尔曲线模拟自然移动
        ease = t * t * (3 - 2 * t)  # smoothstep
        x = start_x + (target_x - start_x) * ease + random.uniform(-2, 2)
        y = start_y + (target_y - start_y) * ease + random.uniform(-2, 2)
        browser._send_cmd("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": int(x), "y": int(y),
            "button": "none",
        })
        time.sleep(duration / steps + random.uniform(-0.01, 0.02))

def press_and_hold(browser, x, y, hold_seconds=8):
    """模拟人类按压按钮"""
    logger.info("🖱️ 开始按压 (%d, %d), 持续 %d 秒", x, y, hold_seconds)
    
    # 先移动鼠标到按钮位置
    human_mouse_move(browser, x, y, duration=1.0)
    time.sleep(random.uniform(0.2, 0.5))
    
    # 按下
    browser._send_cmd("Input.dispatchMouseEvent", {
        "type": "mousePressed",
        "x": x, "y": y,
        "button": "left",
        "clickCount": 1,
        "buttons": 1,
    })
    
    # 按压期间微微移动（模拟人类手抖）
    steps = hold_seconds * 4
    for i in range(steps):
        jitter_x = x + random.uniform(-1.5, 1.5)
        jitter_y = y + random.uniform(-1.5, 1.5)
        browser._send_cmd("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": int(jitter_x), "y": int(jitter_y),
            "button": "left",
            "buttons": 1,
        })
        time.sleep(0.25 + random.uniform(-0.05, 0.1))
    
    # 松开
    browser._send_cmd("Input.dispatchMouseEvent", {
        "type": "mouseReleased",
        "x": x, "y": y,
        "button": "left",
        "clickCount": 1,
        "buttons": 0,
    })
    logger.info("🖱️ 按压完成")

def find_press_button(browser):
    """查找按压按钮的位置"""
    # 查找所有可能的按钮元素
    result = browser.evaluate("""(() => {
        // 查找 canvas 元素
        const canvases = document.querySelectorAll('canvas');
        for (const c of canvases) {
            const r = c.getBoundingClientRect();
            if (r.width > 50 && r.height > 50) {
                return JSON.stringify({
                    type: 'canvas',
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                });
            }
        }
        // 查找 iframe
        const iframes = document.querySelectorAll('iframe');
        for (const f of iframes) {
            const r = f.getBoundingClientRect();
            if (r.width > 50 && r.height > 50) {
                return JSON.stringify({
                    type: 'iframe',
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    src: f.src || '',
                });
            }
        }
        // 查找 div 中带特定 class 或 style 的元素
        const allEls = document.querySelectorAll('div, button, span, [class*=button], [class*=press], [class*=hold], [id*=challenge]');
        for (const el of allEls) {
            const style = window.getComputedStyle(el);
            const r = el.getBoundingClientRect();
            // 圆形大按钮 (大约 200x200 像素)
            if (r.width > 100 && r.height > 100 && r.width < 400 && 
                style.borderRadius && parseFloat(style.borderRadius) > 50) {
                return JSON.stringify({
                    type: 'round_div',
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    cls: el.className.substring(0, 80),
                });
            }
        }
        // 查找包含 press/hold 文本附近的元素
        const body = document.body.innerText.toLowerCase();
        if (body.includes('press') && body.includes('hold')) {
            // 找到文本附近的大元素
            const els = document.querySelectorAll('[class*=fun], [class*=captcha], [class*=challenge], [class*=arkose], [class*=game]');
            for (const el of els) {
                const r = el.getBoundingClientRect();
                if (r.width > 50 && r.height > 50) {
                    return JSON.stringify({
                        type: 'captcha_container',
                        x: Math.round(r.x + r.width/2),
                        y: Math.round(r.y + r.height/2),
                        w: Math.round(r.width),
                        h: Math.round(r.height),
                        cls: el.className.substring(0, 80),
                    });
                }
            }
        }
        return null;
    })()""")
    if result:
        return json.loads(result)
    return None

def main():
    # 测试账号 (被锁定的)
    email = "clarkharpk8qm7p96pvsj8f43@outlook.com"
    password = "UW4MLH5%+2!UEkeu5t"
    client_id = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
    
    import requests
    logger.info("请求 Device Code...")
    resp = requests.post(
        "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode",
        data={"client_id": client_id, "scope": "offline_access openid profile https://graph.microsoft.com/User.Read https://graph.microsoft.com/Mail.Read"},
        timeout=20
    )
    dc = resp.json()
    user_code = dc["user_code"]
    device_code = dc["device_code"]
    logger.info("user_code: %s", user_code)
    
    cfg = CDPLaunchConfig(browser_type="chrome", headless=True)
    browser = CDPBrowser(cfg)
    browser.launch()
    
    try:
        browser.navigate("https://www.microsoft.com/link", wait_for_load=True, timeout=30)
        time.sleep(3)
        
        # Step 1: 填入验证码
        browser.evaluate(f"""(() => {{
            const inp = document.querySelector('input[name="otc"], input#otc');
            if (inp) {{
                inp.focus();
                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                nativeSetter.call(inp, '{user_code}');
                inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                inp.dispatchEvent(new Event('change', {{bubbles: true}}));
            }}
        }})()""")
        time.sleep(1)
        click_button(browser, ["allow access", "next", "submit", "continue"])
        time.sleep(4)
        screenshot(browser, "after_code")
        
        # Step 2: 填入邮箱
        browser.evaluate(f"""(() => {{
            const inp = document.querySelector('input[name="loginfmt"], input[type="email"], input#i0116');
            if (inp) {{
                inp.focus();
                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                nativeSetter.call(inp, '{email}');
                inp.dispatchEvent(new Event('input', {{bubbles: true}}));
            }}
        }})()""")
        time.sleep(0.5)
        click_button(browser, ["next", "sign in"])
        time.sleep(4)
        screenshot(browser, "after_email")
        
        # Step 3: 填入密码
        browser.evaluate(f"""(() => {{
            const inp = document.querySelector('input[type="password"]');
            if (inp) {{
                inp.focus();
                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                nativeSetter.call(inp, '{password}');
                inp.dispatchEvent(new Event('input', {{bubbles: true}}));
            }}
        }})()""")
        time.sleep(0.5)
        click_button(browser, ["sign in", "next"])
        time.sleep(5)
        screenshot(browser, "after_password")
        
        url, body = get_page_info(browser)
        logger.info("当前页面: %s", url[:100])
        logger.info("Body: %s", body[:300])
        
        # Step 4: 如果是 locked 页面，点 Next
        if "abuse" in url.lower() or "locked" in body.lower():
            logger.info("🔒 到达锁定页面，点击 Next")
            screenshot(browser, "locked_page")
            click_button(browser, ["next"])
            time.sleep(4)
            screenshot(browser, "after_next")
            url, body = get_page_info(browser)
        
        # Step 5: 到达 press-and-hold 页面
        if "press" in body.lower() and "hold" in body.lower():
            logger.info("🎯 到达 press-and-hold CAPTCHA 页面")
            screenshot(browser, "captcha_page")
            
            # 详细分析页面 DOM
            dom_info = browser.evaluate("""(() => {
                const result = {elements: [], iframes: [], canvases: []};
                // 所有可见元素
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 30 && r.height > 30 && r.width < 500 && r.height < 500) {
                        const tag = el.tagName;
                        const cls = (el.className || '').toString().substring(0, 60);
                        const id = el.id || '';
                        const style = el.getAttribute('style') || '';
                        result.elements.push({
                            tag, cls, id, 
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            style: style.substring(0, 100),
                        });
                    }
                }
                // iframes
                document.querySelectorAll('iframe').forEach(f => {
                    const r = f.getBoundingClientRect();
                    result.iframes.push({src: f.src, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)});
                });
                // canvases
                document.querySelectorAll('canvas').forEach(c => {
                    const r = c.getBoundingClientRect();
                    result.canvases.push({x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)});
                });
                return JSON.stringify(result);
            })()""")
            
            info = json.loads(dom_info)
            logger.info("DOM 分析: %d elements, %d iframes, %d canvases", 
                       len(info['elements']), len(info['iframes']), len(info['canvases']))
            
            for e in info['elements'][:30]:
                logger.info("  %s class='%s' id='%s' (%d,%d %dx%d)", 
                           e['tag'], e['cls'][:30], e['id'][:20], e['x'], e['y'], e['w'], e['h'])
            for f in info['iframes']:
                logger.info("  iframe: src=%s (%d,%d %dx%d)", f['src'][:60], f['x'], f['y'], f['w'], f['h'])
            for c in info['canvases']:
                logger.info("  canvas: (%d,%d %dx%d)", c['x'], c['y'], c['w'], c['h'])
            
            # 尝试找到按压按钮
            btn = find_press_button(browser)
            
            # 从 DOM 分析中获取 IMG 按钮位置
            img_pos = browser.evaluate("""(() => {
                const imgs = document.querySelectorAll('img');
                for (const img of imgs) {
                    const r = img.getBoundingClientRect();
                    if (r.width > 100 && r.height > 100 && r.width < 300) {
                        return JSON.stringify({
                            type: 'img',
                            x: Math.round(r.x + r.width/2),
                            y: Math.round(r.y + r.height/2),
                            w: Math.round(r.width),
                            h: Math.round(r.height),
                        });
                    }
                }
                return null;
            })()""")
            if img_pos:
                img_data = json.loads(img_pos)
                logger.info("找到 IMG 按钮: %s", json.dumps(img_data))
                # 使用 IMG 按钮的中心坐标进行按压
                press_and_hold(browser, img_data['x'], img_data['y'], hold_seconds=10)
            elif btn:
                logger.info("找到按压按钮: %s", json.dumps(btn))
                # 尝试按压
                press_and_hold(browser, btn['x'], btn['y'], hold_seconds=10)
            else:
                logger.warning("未找到按压按钮")
                # 最后尝试按压页面中间区域
                logger.info("尝试按压页面中间区域 (640, 500)")
                press_and_hold(browser, 640, 500, hold_seconds=10)
            time.sleep(5)
            screenshot(browser, "after_press_hold")
            
            url2, body2 = get_page_info(browser)
            logger.info("按压后页面: URL=%s", url2[:120])
            logger.info("Body: %s", body2[:400])
            
            # 继续观察后续页面
            for phase in range(10):
                url_c, body_c = get_page_info(browser)
                if url_c != url2 or body_c != body2:
                    logger.info("Phase %d: URL=%s", phase, url_c[:120])
                    logger.info("Body: %s", body_c[:400])
                    screenshot(browser, f"phase_{phase}")
                    url2, body2 = url_c, body_c
                    
                    # 如果有输入框或按钮，尝试交互
                    if any(kw in body_c.lower() for kw in ["select proof", "selectproof", "choose how", "verify", "email", "phone"]):
                        logger.info("🎯 可能是选择验证方式页面!")
                        # 详细截图
                        screenshot(browser, f"proof_selection_{phase}")
                        
                    if "enter" in body_c.lower() and ("code" in body_c.lower() or "验证码" in body_c.lower()):
                        logger.info("🎯 可能是输入验证码页面!")
                        screenshot(browser, f"verify_code_{phase}")
                        
                time.sleep(3)
        else:
            logger.info("未到达 press-and-hold 页面，当前: %s", body[:200])
            screenshot(browser, "unexpected_page")
            
    finally:
        browser.close()
    
    logger.info("观察完成！截图: %s", SHOT_DIR)

if __name__ == "__main__":
    main()
