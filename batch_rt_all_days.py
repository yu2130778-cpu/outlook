#!/usr/bin/env python3
"""
按日从新到旧，逐天获取三凭证的RT，升级为四凭证并推送到云端仓库。
"""
import sys, os, time, logging, json, subprocess
from pathlib import Path
from collections import OrderedDict

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "邮箱注册"))
os.environ["DISPLAY"] = ":98"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("batch_rt_all_days")

from cdp_outlook import _extract_refresh_token_device_code, CDPBrowser, CDPLaunchConfig

CLOUD = ROOT / "云端注册邮箱"
THREE_DIR = CLOUD / "三凭证"
FOUR_DIR = CLOUD / "四凭证"
RT_DIR = ROOT / "runtime_outlook" / "rt_tokens"
RT_DIR.mkdir(parents=True, exist_ok=True)

CLIENT_ID_DEFAULT = "14d82eec-204b-4c2f-b7e8-296a70dab67e"


def get_existing_rt_emails() -> set:
    """Get set of emails that already have RT in rt_tokens/ or 四凭证/"""
    s = set()
    # Check rt_tokens/
    if RT_DIR.exists():
        for f in RT_DIR.glob("*.txt"):
            parts = f.read_text(encoding="utf-8").strip().split("----")
            if len(parts) >= 4 and parts[3].strip() and len(parts[3].strip()) > 20:
                s.add(parts[0].strip().lower())
    # Check 四凭证/
    if FOUR_DIR.exists():
        for day_dir in FOUR_DIR.iterdir():
            if day_dir.is_dir():
                for f in day_dir.glob("*.txt"):
                    parts = f.read_text(encoding="utf-8").strip().split("----")
                    if len(parts) >= 4 and parts[3].strip() and len(parts[3].strip()) > 20:
                        s.add(parts[0].strip().lower())
    return s


def load_three_creds(day: str) -> list[dict]:
    """Load unique 三凭证 for a specific day, return list of {email, password, client_id, file_path}"""
    day_dir = THREE_DIR / day
    if not day_dir.exists():
        return []
    seen = set()
    creds = []
    for f in sorted(day_dir.glob("*.txt")):
        content = f.read_text(encoding="utf-8").strip()
        # 智能解析: 密码可能含连续横杠, 用已知 client_id 从尾部定位
        KNOWN_CID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
        suffix = "----" + KNOWN_CID
        if content.endswith(suffix):
            email_pw = content[:-len(suffix)]
            ep = email_pw.split("----", 1)
            if len(ep) == 2:
                email = ep[0].strip()
                password = ep[1].strip()
                client_id = KNOWN_CID
            else:
                continue
        else:
            # fallback: 尝试 client_id 含 - 前缀的情况
            parts = content.split("----")
            if len(parts) < 3:
                continue
            email = parts[0].strip()
            password = parts[1].strip()
            client_id = parts[2].strip().lstrip("-")
        if not email or not password:
            continue
        if email.lower() in seen:
            continue
        seen.add(email.lower())
        creds.append({
            "email": email,
            "password": password,
            "client_id": client_id,
            "file_path": f,
        })
    return creds


def get_rt_for_account(email, password, client_id, proxy_url=""):
    """Get RT using Device Code flow with CDP browser"""
    from proxy_utils import parse_proxy
    pi = parse_proxy(proxy_url) if proxy_url else None
    chrome_proxy = pi.chrome_proxy if pi else ""
    auth_proxy = pi.url if pi and pi.has_auth else ""

    cfg = CDPLaunchConfig(browser_type="chrome", proxy=chrome_proxy, headless=True)
    browser = CDPBrowser(cfg)
    browser.launch()
    try:
        rt = _extract_refresh_token_device_code(
            browser, email, client_id,
            password=password, proxy_url=auth_proxy or chrome_proxy,
            timeout=120
        )
        return rt if rt else ""
    except Exception as e:
        logger.error(f"Error getting RT for {email}: {e}")
        return ""
    finally:
        try:
            browser.close()
        except:
            pass


def save_rt_file(email, password, client_id, rt):
    """Save RT to rt_tokens/ directory"""
    fname = email.replace("@", "_").replace(".", "_") + ".txt"
    f = RT_DIR / fname
    f.write_text(f"{email}----{password}----{client_id}----{rt}", encoding="utf-8")


def upgrade_to_four(email, password, client_id, rt, day):
    """Write 四凭证 file and remove 三凭证 file"""
    four_day_dir = FOUR_DIR / day
    four_day_dir.mkdir(parents=True, exist_ok=True)
    fname = email + ".txt"
    (four_day_dir / fname).write_text(
        f"{email}----{password}----{client_id}----{rt}\n", encoding="utf-8"
    )
    # Remove from 三凭证
    three_file = THREE_DIR / day / fname
    if three_file.exists():
        three_file.unlink()
    logger.info(f"✅ {email} → 四凭证/{day}/")


def git_push_day(day: str):
    """Stage, commit, and push changes for a specific day"""
    # Stage new 四凭证 files
    four_day = FOUR_DIR / day
    if four_day.exists():
        for txt in four_day.glob("*.txt"):
            subprocess.run(["git", "-C", str(CLOUD), "add", str(txt)], check=False)

    # Stage removed 三凭证 (git rm --cached or just add the deletion)
    subprocess.run(["git", "-C", str(CLOUD), "add", "-A", str(THREE_DIR / day) + "/"], check=False)

    # Stage all_success.jsonl
    all_jsonl = CLOUD / "all_success.jsonl"
    if all_jsonl.exists():
        subprocess.run(["git", "-C", str(CLOUD), "add", str(all_jsonl)], check=False)

    # Check if there are staged changes
    diff_out = subprocess.check_output(
        ["git", "-C", str(CLOUD), "diff", "--cached", "--name-only"],
        text=True, stderr=subprocess.DEVNULL
    ).strip()
    if not diff_out:
        logger.info(f"[{day}] nothing to commit")
        return False

    msg = f"upgrade 三凭证→四凭证 for {day}"
    subprocess.run(["git", "-C", str(CLOUD), "commit", "-m", msg], check=True)

    # Push with retry
    r = subprocess.run(["git", "-C", str(CLOUD), "push"], check=False,
                       capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run(["git", "-C", str(CLOUD), "fetch", "origin"], check=False)
        subprocess.run(["git", "-C", str(CLOUD), "rebase", "origin/main"], check=False)
        r = subprocess.run(["git", "-C", str(CLOUD), "push"], check=False,
                           capture_output=True, text=True)
    if r.returncode == 0:
        n_files = len(diff_out.splitlines())
        logger.info(f"[{day}] push_ok ({n_files} files)")
        return True
    else:
        logger.error(f"[{day}] push_failed: {r.stderr[:200]}")
        return False


def update_all_success_jsonl(email, has_rt=True):
    """Update has_refresh_token in all_success.jsonl"""
    all_jsonl = CLOUD / "all_success.jsonl"
    if not all_jsonl.exists():
        return
    lines = all_jsonl.read_text(encoding="utf-8").splitlines()
    changed = False
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except:
            continue
        if d.get("email", "").strip().lower() == email.strip().lower():
            if not d.get("has_refresh_token") and has_rt:
                d["has_refresh_token"] = True
                lines[i] = json.dumps(d, ensure_ascii=False)
                changed = True
    if changed:
        all_jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    # Get all days with 三凭证, sorted newest first
    if not THREE_DIR.exists():
        print("三凭证目录不存在")
        return 1

    days = sorted([d.name for d in THREE_DIR.iterdir() if d.is_dir()], reverse=True)
    if not days:
        print("没有三凭证需要处理")
        return 0

    # Pre-scan existing RTs
    existing_rt = get_existing_rt_emails()
    logger.info(f"已有RT的账号: {len(existing_rt)} 个")

    total_success = 0
    total_fail = 0
    total_skip = 0
    failed_accounts = []

    for day in days:
        creds = load_three_creds(day)
        if not creds:
            logger.info(f"[{day}] 无三凭证，跳过")
            continue

        # Filter out already-have-RT accounts
        todo = [c for c in creds if c["email"].lower() not in existing_rt]
        skip_count = len(creds) - len(todo)
        if skip_count > 0:
            logger.info(f"[{day}] 跳过 {skip_count} 个已有RT的账号")
            total_skip += skip_count

        if not todo:
            logger.info(f"[{day}] 所有账号已有RT，跳过")
            continue

        logger.info(f"\n{'='*60}")
        logger.info(f"[{day}] 处理 {len(todo)} 个三凭证账号")
        logger.info(f"{'='*60}")

        day_success = 0
        day_fail = 0

        for i, cred in enumerate(todo):
            email = cred["email"]
            password = cred["password"]
            client_id = cred["client_id"]

            logger.info(f"[{day}][{i+1}/{len(todo)}] {email} ...")

            rt = get_rt_for_account(email, password, client_id)

            if rt and len(rt) > 20:
                logger.info(f"  ✅ RT: {rt[:40]}...")
                save_rt_file(email, password, client_id, rt)
                upgrade_to_four(email, password, client_id, rt, day)
                update_all_success_jsonl(email, True)
                existing_rt.add(email.lower())
                day_success += 1
                total_success += 1
            else:
                logger.warning(f"  ❌ 获取RT失败")
                day_fail += 1
                total_fail += 1
                failed_accounts.append((day, email))

            # Small delay between accounts
            time.sleep(1)

        logger.info(f"[{day}] 结果: {day_success} 成功, {day_fail} 失败")

        # Push after each day
        if day_success > 0:
            git_push_day(day)

    logger.info(f"\n{'='*60}")
    logger.info(f"全部完成!")
    logger.info(f"  成功: {total_success}")
    logger.info(f"  失败: {total_fail}")
    logger.info(f"  跳过: {total_skip}")
    if failed_accounts:
        logger.info(f"  失败账号列表:")
        for day, email in failed_accounts:
            logger.info(f"    [{day}] {email}")
    logger.info(f"{'='*60}")

    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
