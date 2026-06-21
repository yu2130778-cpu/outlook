import urllib.parse

path = '/home/workspace/Email-Register/邮箱注册/cdp_outlook.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0
patched_host = False
patched_email = False
patched_proofs = False

while i < len(lines):
    line = lines[i]
    
    # Patch 1: Add url_host after url_lower in DC_RT loop
    if not patched_host and '            url_lower = url.lower()' in line:
        # Check if we're in the DC_RT function (check context)
        context = ''.join(lines[max(0,i-30):i])
        if 'DC_RT' in context:
            new_lines.append(line)
            if i+1 < len(lines) and 'body = browser.get_body_text' in lines[i+1]:
                new_lines.append(lines[i+1])
                new_lines.append('            url_host = urllib.parse.urlparse(url).hostname or ""\n')
                i += 2
                patched_host = True
                continue
    
    # Patch 2: Add proofs page handler before 邮箱输入页
    if not patched_proofs and patched_host and '# ── 邮箱输入页（Device Code' in line:
        new_lines.append('            # ── 恢复信息页（proofs/Add） ──\n')
        new_lines.append('            if "proofs" in url_lower and "add" in url_lower:\n')
        new_lines.append('                logger.info("[DC_RT] 恢复信息页，尝试跳过...")\n')
        new_lines.append('                skip_btn = browser.evaluate("""(() => {\n')
        new_lines.append('                    const btns = document.querySelectorAll(\'button, a, [role=button]\');\n')
        new_lines.append('                    for (const b of btns) { const t=(b.textContent||\'\').toLowerCase();\n')
        new_lines.append('                        if (t.includes(\'skip\')||t.includes(\'暂不\')||t.includes(\'跳过\')||t.includes(\'not now\')||t.includes(\'cancel\')||t.includes(\'取消\'))\n')
        new_lines.append('                        { b.click(); return t.substring(0,30); } }\n')
        new_lines.append('                    return null;\n')
        new_lines.append('                })()""")\n')
        new_lines.append('                if not skip_btn:\n')
        new_lines.append('                    logger.warning("[DC_RT] 恢复页无法跳过，立即返回")\n')
        new_lines.append('                    return ""\n')
        new_lines.append('                time.sleep(3)\n')
        new_lines.append('                continue\n')
        new_lines.append('\n')
        patched_proofs = True
    
    # Patch 3: Fix email page URL check to use url_host
    if not patched_email and patched_host and '# ── 邮箱输入页（Device Code' in line:
        new_lines.append(line)
        i += 1
        if i < len(lines):
            old = lines[i]
            fixed = old.replace(
                '("login.live.com" in url_lower or "login.microsoftonline.com" in url_lower)',
                '(url_host in ("login.live.com", "login.microsoftonline.com", "login.live-int.com"))'
            )
            new_lines.append(fixed)
            patched_email = True
        continue
    
    new_lines.append(line)
    i += 1

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"Patched: url_host={patched_host}, proofs={patched_proofs}, email={patched_email}")
