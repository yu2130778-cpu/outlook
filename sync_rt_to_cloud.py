#!/usr/bin/env python3
"""清理有四凭证的三凭证文件，并确保日期正确。
1. 四凭证中已有RT的账号 -> 删除三凭证中对应文件
2. 检查本地rt_tokens中新获取的RT -> 更新/新增四凭证文件
3. 确保文件名用@而非_at_（已修复）
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLOUD = ROOT / "云端注册邮箱"
RT_DIR = ROOT / "runtime_outlook" / "rt_tokens"
RESULTS = ROOT / "runtime_outlook" / "results.jsonl"

# 1. 读取 results.jsonl 获取注册日期
reg_dates = {}  # email -> date_str (YYYY-MM-DD)
if RESULTS.exists():
    for line in RESULTS.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except:
            continue
        email = d.get("email", "").strip().lower()
        ts = d.get("ts", "")
        if email and ts:
            reg_dates[email] = ts[:10]  # YYYY-MM-DD

# 2. 读取本地四凭证 rt_tokens
local_4 = {}  # email -> (password, client_id, rt)
for f in RT_DIR.glob("*.txt"):
    parts = f.read_text("utf-8").strip().split("----")
    if len(parts) >= 4:
        email = parts[0].strip().lower()
        local_4[email] = (parts[1], parts[2], parts[3])

# 3. 读取云端已有四凭证
cloud_4 = {}  # email -> (date_dir, file_path)
four_dir = CLOUD / "四凭证"
for date_dir in sorted(four_dir.iterdir()):
    if not date_dir.is_dir():
        continue
    for f in date_dir.glob("*.txt"):
        email = f.stem.lower().replace("_at_", "@")
        cloud_4[email] = (date_dir.name, f)

# 4. 读取云端已有三凭证
cloud_3 = {}  # email -> (date_dir, file_path)
three_dir = CLOUD / "三凭证"
for date_dir in sorted(three_dir.iterdir()):
    if not date_dir.is_dir():
        continue
    for f in date_dir.glob("*.txt"):
        email = f.stem.lower().replace("_at_", "@")
        cloud_3[email] = (date_dir.name, f)

# 5. 找到本地有RT但云端四凭证没有的 -> 需要新增
to_add = set(local_4.keys()) - set(cloud_4.keys())
print(f"本地有RT: {len(local_4)}")
print(f"云端四凭证: {len(cloud_4)}")
print(f"需要新增四凭证: {len(to_add)}")

# 6. 找到云端四凭证和三凭证都有同一账号的 -> 删除三凭证
to_delete_3 = set(cloud_4.keys()) & set(cloud_3.keys())
print(f"需要删除三凭证: {len(to_delete_3)}")

# 7. 找到本地有RT但云端四凭证里RT为空的 -> 需要更新
to_update = []
for email, (date_dir, fpath) in cloud_4.items():
    if email in local_4:
        parts = fpath.read_text("utf-8").strip().split("----")
        if len(parts) >= 4 and len(parts[3].strip()) < 20:
            to_update.append((email, date_dir, fpath))
print(f"需要更新RT为空的四凭证: {len(to_update)}")

# === 执行 ===

# 删除三凭证
for email in sorted(to_delete_3):
    date_dir, fpath = cloud_3[email]
    if fpath.exists():
        print(f"删除三凭证: {fpath.relative_to(CLOUD)}")
        fpath.unlink()

# 新增四凭证
added = 0
for email in sorted(to_add):
    pwd, cid, rt = local_4[email]
    date_str = reg_dates.get(email, "")
    if not date_str:
        print(f"  跳过(无注册日期): {email}")
        continue
    target_dir = four_dir / date_str
    target_dir.mkdir(parents=True, exist_ok=True)
    fname = email.replace("@", "@")
    target = target_dir / f"{fname}.txt"
    line = f"{email}----{pwd}----{cid}----{rt}"
    target.write_text(line + "\n", encoding="utf-8")
    added += 1
    print(f"新增四凭证: {date_str}/{fname}.txt")

# 更新RT为空的四凭证
updated = 0
for email, date_dir, fpath in to_update:
    pwd, cid, rt = local_4[email]
    line = f"{email}----{pwd}----{cid}----{rt}"
    fpath.write_text(line + "\n", encoding="utf-8")
    updated += 1
    print(f"更新四凭证: {date_dir}/{email}.txt")

# 清理空目录
for d in [three_dir, four_dir]:
    for sub in list(d.iterdir()):
        if sub.is_dir() and not any(sub.iterdir()):
            print(f"删除空目录: {sub.relative_to(CLOUD)}")
            sub.rmdir()

print(f"\n=== 完成 ===")
print(f"新增四凭证: {added}")
print(f"更新四凭证: {updated}")
print(f"删除三凭证: {len(to_delete_3)}")
