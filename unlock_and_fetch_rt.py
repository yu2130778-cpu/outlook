#!/usr/bin/env python3
"""
风控解除获取RT — 复用注册流程的 CAPTCHA 处理方案
核心：monkey-patch _extract_refresh_token_device_code，在 fatal_keywords 检测前插入 Abuse+CAPTCHA 处理
"""
import sys, os, time, logging, json, threading, re, random
from pathlib import Path
from datetime import datetime
import argparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "邮箱注册"))
os.environ["DISPLAY"] = ":98"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("unlock_rt")

# 导入原始模块
from cdp_outlook import (
    CDPBrowser, CDPLaunchConfig,
    _extract_refresh_token_device_code,
    _handle_hsprotect_captcha, _detect_captcha,
    _cdp_touch_long_press
)

# Monkey-patch: force press_hold for unknown_cross_origin
import cdp_outlook as _cdp
_orig_locate = _cdp._locate_hsprotect_challenge
def _patched_locate(browser):
    result = _orig_locate(browser)
    if result and result.get("type") == "unknown_cross_origin":
        result["type"] = "press_hold"
        result["x"] = result.get("x", 640)
        result["y"] = result.get("y", 536)
    return result
_cdp._locate_hsprotect_challenge = _patched_locate
from proxy_utils import parse_proxy

THREE_DIR = ROOT / "云端注册邮箱" / "三凭证"
FOUR_DIR = ROOT / "云端注册邮箱" / "四凭证"
UNLOCK_DIR = ROOT / "云端注册邮箱" / "解锁凭证"
KNOWN_CID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
RT_DIR = ROOT / "runtime_outlook" / "rt_tokens"
RESULTS_FILE = ROOT / "runtime_outlook" / "results.jsonl"


def parse_three_cred(f):
    """解析三凭证文件"""
    content = f.read_text(encoding="utf-8").strip()
    suffix = "----" + KNOWN_CID
    if content.endswith(suffix):
        email_pw = content[:-len(suffix)]
        ep = email_pw.split("----", 1)
        if len(ep) == 2:
            return ep[0].strip(), ep[1].strip(), KNOWN_CID
    parts = content.split("----")
    if len(parts) >= 3:
        return parts[0].strip(), parts[1].strip(), parts[2].strip().lstrip("-")
    return None


def get_locked_accounts():
    """从三凭证目录收集所有待解锁账号"""
    accounts = []
    for day_dir in sorted(THREE_DIR.iterdir(), reverse=True):
        if not day_dir.is_dir():
            continue
        day = day_dir.name
        for f in sorted(day_dir.glob("*.txt")):
            parsed = parse_three_cred(f)
            if not parsed:
                continue
            email, password, client_id = parsed
            rt_file = RT_DIR / (email.replace("@", "_").replace(".", "_") + ".txt")
            if rt_file.exists():
                content = rt_file.read_text(encoding="utf-8").strip()
                parts = content.split("----")
                if len(parts) >= 4 and len(parts[3]) > 20:
                    continue
            accounts.append({
                "email": email, "password": password, "client_id": client_id,
                "day": day, "source_file": f,
            })
    return accounts


def get_check_account():
    """获取一个四凭证账号作为检验号"""
    for day_dir in sorted(FOUR_DIR.iterdir(), reverse=True):
        if not day_dir.is_dir():
            continue
        for f in sorted(day_dir.glob("*.txt")):
            content = f.read_text(encoding="utf-8").strip()
            parts = content.split("----")
            if len(parts) >= 4 and parts[2].strip() == KNOWN_CID and len(parts[3]) > 20:
                return parts[0].strip(), parts[1].strip(), KNOWN_CID
    return None


# ═══════════════════════════════════════════════════════════════
# Monkey-patch: 扩展 _extract_refresh_token_device_code 的 Abuse 处理
# ═══════════════════════════════════════════════════════════════

import cdp_outlook as _cdp_mod

# 保存原始函数
_original_dc_func = _extract_refresh_token_device_code

def _patched_extract_refresh_token_device_code(browser, email, client_id="14d82eec-204b-4c2f-b7e8-296a70dab67e",
                                                timeout=60, password="", proxy_url=""):
    """
    增强版 Device Code 流程：
    - 正常账号：行为与原始函数完全一致
    - 被锁定账号：检测 Abuse 页面 → 点 Next → 处理 CAPTCHA → 继续正常流程
    """
    import json as _json
    import urllib.parse, urllib.request
    import threading as _thr

    tenant = "consumers"
    scopes = "offline_access openid profile https://graph.microsoft.com/User.Read https://graph.microsoft.com/Mail.Read"
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    device_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode"

    def _post_form(url, form_data, use_proxy=True):
        try:
            import requests as _req
            proxies = None
            if use_proxy and proxy_url:
                proxies = {"http": proxy_url, "https": proxy_url}
            resp = _req.post(url, data=form_data, proxies=proxies, timeout=20)
            if resp.status_code >= 400:
                try:
                    payload = resp.json()
                except Exception:
                    payload = {"error": "http_error", "error_description": resp.text[:500]}
                return None, payload
            return resp.json(), None
        except Exception as exc:
            return None, {"error": "network_error", "error_description": str(exc)}

    # Step 1: 请求 Device Code
    _cdp_mod.logger.info("[DC_RT] 请求 Device Code: email=%s, client_id=%s", email, client_id)
    dc_data, dc_err = _post_form(device_url, {"client_id": client_id, "scope": scopes})
    if dc_err or not dc_data:
        _cdp_mod.logger.warning("[DC_RT] 请求 Device Code 失败: %s", dc_err)
        return ""
    user_code = dc_data.get("user_code", "")
    device_code = dc_data.get("device_code", "")
    verification_uri = dc_data.get("verification_uri") or dc_data.get("verification_url") or "https://www.microsoft.com/link"
    verification_uri_complete = dc_data.get("verification_uri_complete", "")
    expires_in = int(dc_data.get("expires_in", 900))
    poll_interval = max(1, int(dc_data.get("interval", 5)))

    if not user_code or not device_code:
        _cdp_mod.logger.warning("[DC_RT] 微软未返回 device_code/user_code")
        return ""

    _cdp_mod.logger.info("[DC_RT] Device Code 获取成功: user_code=%s", user_code)

    target_url = verification_uri_complete if verification_uri_complete else verification_uri

    # 轮询
    _poll_result = {"tokens": None, "error": None, "done": False}
    _poll_lock = _thr.Lock()

    def _poll_worker():
        deadline = time.time() + expires_in
        interval = poll_interval
        while time.time() < deadline:
            time.sleep(interval)
            with _poll_lock:
                if _poll_result["done"]:
                    return
            resp, err = _post_form(token_url, {
                "client_id": client_id,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
            })
            if resp and resp.get("refresh_token"):
                with _poll_lock:
                    _poll_result["tokens"] = resp
                    _poll_result["done"] = True
                _cdp_mod.logger.info("[DC_RT] 轮询获取到 tokens!")
                return
            if resp and resp.get("access_token"):
                with _poll_lock:
                    _poll_result["tokens"] = resp
                    _poll_result["done"] = True
                return
            if err:
                err_code = err.get("error", "")
                if err_code == "authorization_pending":
                    pass
                elif err_code == "slow_down":
                    interval += 5
                elif err_code in ("expired_token", "authorization_declined"):
                    with _poll_lock:
                        _poll_result["error"] = err_code
                        _poll_result["done"] = True
                    return
        with _poll_lock:
            _poll_result["error"] = "timeout"
            _poll_result["done"] = True

    poll_thread = _thr.Thread(target=_poll_worker, daemon=True)
    poll_thread.start()

    _cdp_mod.logger.info("[DC_RT] 导航到验证页: %s", target_url)

    try:
        browser.navigate(target_url, wait_for_load=True, timeout=30)
        time.sleep(3)

        deadline = time.time() + timeout
        _abuse_handled = False
        _ms_error_count = 0

        while time.time() < deadline:
            with _poll_lock:
                if _poll_result["done"]:
                    break

            url = browser.get_url()
            url_lower = url.lower()
            body = browser.get_body_text().lower()
            url_host = urllib.parse.urlparse(url).hostname or ""
            _cdp_mod.logger.info("[DC_RT] 页面: URL=%s body_len=%d", url[:120], len(body))

            # ── Abuse/locked 页面处理 ──
            if "account.live.com/abuse" in url_lower or "account has been locked" in body:
                if not _abuse_handled:
                    _cdp_mod.logger.info("[DC_RT] ⚡ 检测到账号锁定页面！尝试解除风控...")

                    # 点 Next 按钮
                    next_clicked = browser.evaluate("""(() => {
                        const btns = document.querySelectorAll('button, input[type=submit], [role=button], a[role=button]');
                        for (const b of btns) {
                            const t = (b.textContent || b.value || '').toLowerCase().trim();
                            if (t === 'next' || t === '下一步' || t === 'continue' || t === '继续')
                            { b.click(); return 'clicked:' + t; }
                        }
                        const idBtn = document.getElementById('idSIButton9');
                        if (idBtn) { idBtn.click(); return 'idSIButton9'; }
                        return null;
                    })()""")
                    _cdp_mod.logger.info("[DC_RT] Abuse Next 按钮: %s", next_clicked)
                    time.sleep(5)

                    # 检测 CAPTCHA
                    captcha = _detect_captcha(browser)
                    if captcha:
                        _cdp_mod.logger.info("[DC_RT] 🎯 检测到 CAPTCHA: type=%s", captcha.get("type"))
                        if captcha["type"] == "hsprotect":
                            success = _handle_hsprotect_captcha(browser, timeout=120)
                            if success:
                                _cdp_mod.logger.info("[DC_RT] ✅ CAPTCHA 通过！")
                                _abuse_handled = True
                                time.sleep(5)
                                continue
                            else:
                                _cdp_mod.logger.warning("[DC_RT] ❌ CAPTCHA 未通过")
                                return ""
                        else:
                            _cdp_mod.logger.info("[DC_RT] 非 hsprotect CAPTCHA: %s", captcha)
                            return ""
                    else:
                        _cdp_mod.logger.info("[DC_RT] 未检测到 CAPTCHA，页面可能已前进")
                        _abuse_handled = True
                        time.sleep(3)
                        continue
                else:
                    # Abuse 已处理，但还在 abuse 页面 → 可能需要处理后续验证
                    _cdp_mod.logger.info("[DC_RT] Abuse 页面仍在，检查后续验证...")
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                    screenshot_path = ROOT / "runtime_outlook" / "abuse_screenshots" / f"abuse_{timestamp}.png"
                    browser.screenshot(str(screenshot_path))
                    body_text = browser.get_body_text()
                    button_texts = browser.evaluate("""(() => {
                        const btns = document.querySelectorAll('button, input[type=submit], [role=button], a[role=button]');
                        return Array.from(btns).map(b => b.textContent || b.value || '').filter(t => t.trim()).join('\n');
                    })()""")
                    iframe_srcs = browser.evaluate("""(() => {
                        const iframes = document.querySelectorAll('iframe');
                        return Array.from(iframes).map(i => i.src || '').filter(s => s.trim()).join('\n');
                    })()""")
                    _cdp_mod.logger.info("[DC_RT] Abuse 页面截图已保存至: %s", screenshot_path)
                    _cdp_mod.logger.info("[DC_RT] Abuse 页面 body text: %s", body_text[:500])
                    _cdp_mod.logger.info("[DC_RT] Abuse 页面按钮文本: %s", button_texts[:500])
                    _cdp_mod.logger.info("[DC_RT] Abuse 页面 iframe srcs: %s", iframe_srcs[:500])
                    time.sleep(3)
                    continue

            # ── Device Code 输入页 ──
            if "microsoft.com/link" in url_lower or "devicelogin" in url_lower or "oauth20_remoteconnect" in url_lower:
                has_code_input = browser.evaluate("""(() => {
                    const inputs = document.querySelectorAll('input[type="text"], input[type="tel"], input[name*="code"], input[id*="code"], input[id*="otc"]');
                    for (const inp of inputs) { if (inp.offsetParent !== null && inp.offsetWidth > 30) return true; }
                    return false;
                })()""")
                if has_code_input and user_code:
                    _cdp_mod.logger.info("[DC_RT] 填入 user_code: %s", user_code)
                    browser.evaluate(f"""(() => {{
                        const inputs = document.querySelectorAll('input[type="text"], input[type="tel"], input[name*="code"], input[id*="code"], input[id*="otc"]');
                        for (const inp of inputs) {{
                            if (inp.offsetParent !== null && inp.offsetWidth > 30) {{
                                inp.scrollIntoView({{block: 'center'}});
                                inp.focus();
                                inp.value = '';
                                const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                                ns.call(inp, '{user_code}');
                                inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                                inp.dispatchEvent(new Event('change', {{bubbles: true}}));
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
                            if (t.includes('next') || t.includes('submit') || t.includes('continue') || t.includes('allow access'))
                            { b.click(); return 'clicked:' + t; }
                        }
                        const idBtn = document.getElementById('idSIButton9');
                        if (idBtn) { idBtn.click(); return 'idSIButton9'; }
                        return 'no_btn';
                    })()""")
                    time.sleep(3)
                    continue

            # ── 账号选择页 ──
            is_account_picker = False
            if url_host in ("login.live.com", "login.microsoftonline.com"):
                if any(kw in body for kw in ["pick an account", "choose account", "选择帐户"]):
                    is_account_picker = True
                elif browser.evaluate('(() => document.querySelectorAll("[data-email], [data-upn]").length > 0)()'):
                    is_account_picker = True
            if is_account_picker and email:
                _cdp_mod.logger.info("[DC_RT] 账号选择页")
                email_prefix = email.split('@')[0].lower()
                pos = browser.evaluate(
                    f'(() => {{ '
                    f' const email = "{email.lower()}";'
                    f' const emailPrefix = "{email_prefix}";'
                    f' const els = [...document.querySelectorAll("div, button, a, tr, td, span, li, p, [role=listitem], [role=option]")];'
                    f' let best = null; let bestArea = Infinity;'
                    f' for (const el of els) {{'
                    f'  const t = (el.textContent || "").trim().toLowerCase();'
                    f'  if (!t || (!t.includes(email) && !t.includes(emailPrefix))) continue;'
                    f'  const r = el.getBoundingClientRect();'
                    f'  if (r.width < 30 || r.height < 10) continue;'
                    f'  const area = r.width * r.height;'
                    f'  if (area < bestArea) {{ bestArea = area; best = el; }}'
                    f' }}'
                    f' if (best) {{'
                    f'  const r = best.getBoundingClientRect();'
                    f'  return JSON.stringify({{x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), text: best.textContent.trim().substring(0,40)}});'
                    f' }}'
                    f' return null; }})()')
                if pos:
                    try:
                        pos_data = _json.loads(pos)
                        browser.click_at(pos_data['x'], pos_data['y'])
                    except Exception:
                        pass
                time.sleep(3)
                continue

            # ── 邮箱输入页 ──
            if (url_host in ("login.live.com", "login.microsoftonline.com", "login.live-int.com")) and email:
                has_email_field = browser.evaluate("""(() => {
                    const inputs = document.querySelectorAll('input[name="loginfmt"], input[type="email"], #i0116');
                    for (const inp of inputs) { if (inp.offsetParent !== null && inp.offsetWidth > 30) return true; }
                    return false;
                })()""")
                has_pwd_field = browser.evaluate("""(() => {
                    const inputs = document.querySelectorAll('input[type="password"]');
                    for (const inp of inputs) { if (inp.offsetParent !== null && inp.offsetWidth > 30) return true; }
                    return false;
                })()""")
                if has_email_field and not has_pwd_field:
                    _cdp_mod.logger.info("[DC_RT] 邮箱输入页")
                    browser.evaluate(f"""(() => {{
                        const inputs = document.querySelectorAll('input[name="loginfmt"], input[type="email"], #i0116');
                        for (const inp of inputs) {{
                            if (inp.offsetParent !== null && inp.offsetWidth > 30) {{
                                inp.scrollIntoView({{block: 'center'}});
                                inp.focus(); inp.value = '';
                                const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                                ns.call(inp, '{email}');
                                inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                                inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                                const btns = document.querySelectorAll('button, input[type=submit], [role=button]');
                                for (const b of btns) {{
                                    const t = (b.textContent || b.value || '').toLowerCase().trim();
                                    if (t.includes('next') || t.includes('下一步') || t.includes('submit'))
                                    {{ b.click(); return 'btn:' + t.substring(0,30); }}
                                }}
                                const idBtn = document.getElementById('idSIButton9');
                                if (idBtn) {{ idBtn.click(); return 'idSIButton9'; }}
                                return 'filled_no_btn';
                            }}
                        }}
                        return 'no_input';
                    }})()""")
                    time.sleep(3)
                    continue

            # ── 密码输入页 ──
            if url_host in ("login.live.com", "login.microsoftonline.com") and password:
                has_password_field = browser.evaluate("""(() => {
                    const inputs = document.querySelectorAll('input[type="password"]');
                    for (const inp of inputs) { if (inp.offsetParent !== null && inp.offsetWidth > 30) return true; }
                    return false;
                })()""")
                if has_password_field:
                    _cdp_mod.logger.info("[DC_RT] 密码输入页")
                    pwd_escaped = password.replace("'", "\\'").replace("\\", "\\\\")
                    fill_result = browser.evaluate(f"""(() => {{
                        const inputs = document.querySelectorAll('input[type="password"]');
                        for (const inp of inputs) {{
                            if (inp.offsetParent !== null && inp.offsetWidth > 30) {{
                                inp.scrollIntoView({{block: 'center'}});
                                inp.focus(); inp.value = '';
                                const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                                ns.call(inp, '{pwd_escaped}');
                                inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                                inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                                const btns = document.querySelectorAll('button, input[type=submit], [role=button]');
                                for (const b of btns) {{
                                    const t = (b.textContent || b.value || '').toLowerCase().trim();
                                    if (t.includes('sign in') || t.includes('next') || t.includes('登录'))
                                    {{ b.click(); return 'btn:' + t.substring(0,30); }}
                                }}
                                const idBtn = document.getElementById('idSIButton9');
                                if (idBtn) {{ idBtn.click(); return 'idSIButton9'; }}
                                return 'filled_no_btn';
                            }}
                        }}
                        return 'no_input';
                    }})()""")
                    if fill_result == 'filled_no_btn':
                        try:
                            browser._send_cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})
                            browser._send_cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})
                        except Exception:
                            pass
                    time.sleep(3)
                    continue

            # ── 保持登录页 ──
            if "/kmsi" in url_lower or "keepsignin" in body.replace(" ", "") or "stay signed" in body or "保持登录" in body:
                _cdp_mod.logger.info("[DC_RT] 保持登录页面")
                browser.evaluate("""(() => {
                    const btn9 = document.getElementById('idSIButton9');
                    if (btn9) { btn9.click(); return 'idSIButton9'; }
                    const btns = document.querySelectorAll('button, input[type=submit], [role=button]');
                    for (const b of btns) {
                        const t = (b.textContent || b.value || '').toLowerCase().trim();
                        if (t==='yes' || t==='是' || t.includes('stay signed') || t.includes('保持登录'))
                        { b.click(); return 'text:' + t.substring(0,20); }
                    }
                    return null;
                })()""")
                time.sleep(3)
                continue

            # ── Consent 页 ──
            is_consent = ("account.live.com/consent" in url_lower or
                         ("login.microsoftonline.com" in url_lower and ("/consent" in url_lower or "/authorize" in url_lower)) or
                         any(kw in body for kw in ["permission", "permissions requested", "请求的权限"]))
            if is_consent:
                _cdp_mod.logger.info("[DC_RT] Consent 页面")
                browser.evaluate("""(() => {
                    for (const id of ['idBtn_Accept','idSIButton9','acceptButton','nextButton','primaryButton']) {
                        const el = document.getElementById(id);
                        if (el && el.offsetWidth > 0) { el.click(); return 'id:' + id; }
                    }
                    const btns = document.querySelectorAll('button, input[type=submit], [role=button]');
                    for (const b of btns) {
                        const t = (b.textContent || b.value || '').toLowerCase().trim();
                        if (t.includes('accept')||t.includes('agree')||t.includes('allow')||t.includes('continue')||
                            t.includes('next')||t.includes('ok')||t.includes('yes')||t.includes('确认')||
                            t.includes('同意')||t.includes('接受')||t.includes('继续'))
                        { b.click(); return 'text:' + t.substring(0,30); }
                    }
                    return null;
                })()""")
                time.sleep(3)
                continue

            # ── 恢复信息/添加邮箱页 ──
            if "proofs" in url_lower or any(kw in body for kw in ["add a recovery", "recovery email", "添加恢复"]):
                _cdp_mod.logger.info("[DC_RT] 恢复信息页")
                browser.evaluate("""(() => {
                    const btns = document.querySelectorAll('button, a, [role=button]');
                    for (const b of btns) { const t=(b.textContent||'').toLowerCase();
                        if (t.includes('skip')||t.includes('暂不')||t.includes('跳过')||t.includes('not now')||t.includes('cancel'))
                        { b.click(); return t.substring(0,30); } }
                    return null;
                })()""")
                time.sleep(3)
                continue

            # ── Passkey 页 ──
            if any(kw in body for kw in ["选择保存通行密钥", "windows 安全中心", "passkey setup", "passkey creation"]):
                _cdp_mod.logger.info("[DC_RT] Passkey 弹窗")
                browser.evaluate("""(() => {
                    const btns = document.querySelectorAll('button, [role=button], input[type=submit]');
                    for (const b of btns) {
                        const t = (b.textContent || b.value || '').toLowerCase().trim();
                        if (t === 'next' || t === '下一步' || t === 'continue' || t === 'sign in')
                        { b.click(); return 'next:' + t; }
                    }
                    const idBtn = document.getElementById('idSIButton9');
                    if (idBtn) { idBtn.click(); return 'idSIButton9'; }
                    return null;
                })()""")
                time.sleep(3)
                continue

            # ── chrome-error ──
            if "chromewebdata" in url_lower:
                _cdp_mod.logger.warning("[DC_RT] chrome-error")
                time.sleep(3)
                try:
                    browser.navigate(target_url, wait_for_load=True, timeout=20)
                except Exception:
                    pass
                time.sleep(2)
                continue

            # ── 未识别页面 ──
            _cdp_mod.logger.info("[DC_RT] 未识别页面，等待...")
            time.sleep(2)
            browser.evaluate("""(() => {
                const btns = document.querySelectorAll('button, input[type=submit], [role=button]');
                for (const b of btns) {
                    const t = (b.textContent || b.value || '').toLowerCase().trim();
                    if (t.includes('accept')||t.includes('agree')||t.includes('allow')||t.includes('continue')||
                        t.includes('next')||t.includes('ok')||t.includes('yes')||t.includes('submit')||t.includes('confirm'))
                    { b.click(); return 'auto:' + t.substring(0,30); }
                }
                return null;
            })()""")

        # 循环结束
        with _poll_lock:
            if _poll_result["done"] and _poll_result["tokens"]:
                tokens = _poll_result["tokens"]
                rt = tokens.get("refresh_token", "")
                if rt:
                    _cdp_mod.logger.info("[DC_RT] ✅ refresh_token: %s...", rt[:30])
                return rt
            elif _poll_result["error"]:
                _cdp_mod.logger.warning("[DC_RT] 流程失败: %s", _poll_result["error"])
                return ""
            else:
                return ""

    except Exception as e:
        _cdp_mod.logger.warning("[DC_RT] 异常: %s", e)
        return ""
    finally:
        with _poll_lock:
            _poll_result["done"] = True


def write_back_rt(email, rt):
    """写回 RT 到 results.jsonl"""
    if not RESULTS_FILE.exists():
        return
    lines = RESULTS_FILE.read_text(encoding="utf-8").splitlines()
    email_lower = email.strip().lower()
    for i in range(len(lines) - 1, -1, -1):
        try:
            d = json.loads(lines[i])
        except Exception:
            continue
        if d.get("email", "").strip().lower() == email_lower and not d.get("refresh_token"):
            d["refresh_token"] = rt
            lines[i] = json.dumps(d, ensure_ascii=False)
            break
    RESULTS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_unlock_cred(email, password, client_id, rt):
    """保存解锁凭证到 解锁凭证/ 目录"""
    UNLOCK_DIR.mkdir(parents=True, exist_ok=True)
    fname = email.replace("/", "_") + ".txt"
    f = UNLOCK_DIR / fname
    f.write_text(f"{email}----{password}----{client_id}----{rt}\n", encoding="utf-8")
    # 也写入 rt_tokens
    RT_DIR.mkdir(parents=True, exist_ok=True)
    rt_fname = email.replace("@", "_").replace(".", "_") + ".txt"
    (RT_DIR / rt_fname).write_text(f"{email}----{password}----{client_id}----{rt}", encoding="utf-8")
    return f


def main():
    # 检验号测试
    check = get_check_account()
    if check:
        email, password, client_id = check
        logger.info("检验号: %s", email)
    else:
        logger.warning("找不到四凭证检验号")

    # 获取锁定账号
    accounts = get_locked_accounts()
    logger.info("=" * 60)
    logger.info("找到 %d 个待解锁账号", len(accounts))
    logger.info("=" * 60)

    success = 0
    fail = 0
    failed_list = []

    for i, acc in enumerate(accounts):
        email = acc["email"]
        password = acc["password"]
        client_id = acc["client_id"]
        day = acc["day"]

        logger.info("\n[%d/%d] %s (日期: %s)", i + 1, len(accounts), email, day)

        cfg = CDPLaunchConfig(browser_type="chrome", proxy="", headless=True)
        browser = CDPBrowser(cfg)
        browser.launch()

        try:
            rt = _patched_extract_refresh_token_device_code(
                browser, email, client_id,
                password=password, proxy_url="",
                timeout=180
            )
            if rt:
                logger.info("✅ RT: %s...", rt[:30])
                save_unlock_cred(email, password, client_id, rt)
                write_back_rt(email, rt)
                success += 1
            else:
                logger.info("❌ 未获取到 RT")
                fail += 1
                failed_list.append(f"{email} ({day})")
        except Exception as e:
            logger.error("❌ 异常: %s", e)
            fail += 1
            failed_list.append(f"{email} ({day}): {e}")
        finally:
            try:
                browser.close()
            except Exception:
                pass

    logger.info("=" * 60)
    logger.info("完成! 成功=%d, 失败=%d", success, fail)
    if failed_list:
        logger.info("失败列表:")
        for f in failed_list:
            logger.info("  %s", f)
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
