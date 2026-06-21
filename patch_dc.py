import sys

path = sys.argv[1]
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

old = "            # \u2500\u2500 \u672a\u8bc6\u522b\u9875\u9762 \u2500\u2500\n            logger.info(\"[DC_RT] \u672a\u8bc6\u522b\u9875\u9762\uff0c\u7b49\u5f85...\")\n            time.sleep(2)"

new = """            # \u2500\u2500 \u8d26\u53f7\u81f4\u547d\u9519\u8bef\u5feb\u901f\u68c0\u6d4b \u2500\u2500
            fatal_keywords = ['account has been locked', 'your account or password is incorrect',
                              "that code didn't work", 'account doesn\'t exist', 'account wasn\'t found']
            is_fatal = any(kw in body for kw in fatal_keywords)
            if is_fatal:
                logger.warning("[DC_RT] \u8d26\u53f7\u81f4\u547d\u9519\u8bef\uff0c\u7acb\u5373\u8df3\u8fc7: %s", body[:200])
                return ""
            # \u2500\u2500 \u672a\u8bc6\u522b\u9875\u9762 \u2500\u2500
            logger.info("[DC_RT] \u672a\u8bc6\u522b\u9875\u9762\uff0c\u7b49\u5f85...")
            time.sleep(2)"""

if old in c:
    c = c.replace(old, new, 1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(c)
    print("PATCHED OK")
else:
    print("ERROR: target not found")
    # show context
    idx = c.find('# \u2500\u2500 \u672a\u8bc6\u522b\u9875\u9762')
    if idx >= 0:
        print("Found at idx", idx)
        print(repr(c[idx:idx+200]))
