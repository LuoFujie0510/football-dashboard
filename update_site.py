#!/usr/bin/env python3
"""
足球预测网站更新脚本

用法:
  python3 update_site.py                           # 用最新的预测 JSON 更新
  python3 update_site.py predictions_2026-05-09.json  # 指定 JSON 文件
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime

REPORTS_DIR = os.path.expanduser("~/football_reports")
SITE_DIR = os.path.expanduser("~/personal-site")
INDEX_PATH = os.path.join(SITE_DIR, "index.html")


def find_latest_json():
    """找到最新的 predictions_*.json 文件"""
    jsons = []
    for f in os.listdir(REPORTS_DIR):
        if f.startswith("predictions_") and f.endswith(".json"):
            jsons.append(f)
    if not jsons:
        print("❌ 没有找到预测 JSON 文件")
        sys.exit(1)
    jsons.sort(reverse=True)
    return os.path.join(REPORTS_DIR, jsons[0])


def load_predictions(json_path):
    """加载预测 JSON，返回更新后的 DATA.predictions 数组"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    predictions = data.get("predictions", [])
    print(f"📋 加载 {len(predictions)} 场预测 ({data.get('date', '?')})")

    for p in predictions:
        print(f"   {p['match']:35s} v3:{p['v3']:8s} v4:{p['v4']:8s} {p['score']}")
    return predictions


def _parse_js_array(js_text):
    """解析 JS 风格的数组内容（容忍尾随逗号、单引号、null）"""
    # 移除 JS 注释
    js_text = re.sub(r'//.*?\n', '\n', js_text)
    js_text = re.sub(r'/\*.*?\*/', '', js_text, flags=re.DOTALL)
    # 移除尾随逗号（在 ] 或 } 前）
    js_text = re.sub(r',\s*(\]|\})', r'\1', js_text)
    # 替换单引号字符串为双引号
    js_text = re.sub(r"'([^']*?)'", r'"\1"', js_text)
    # 替换未加引号的 key (JS 对象字面量)
    js_text = re.sub(r'([{,])\s*(\w+)\s*:', r'\1"\2":', js_text)
    # 包裹为合法 JSON 数组
    js_text = '[' + js_text + ']'
    try:
        return json.loads(js_text)
    except json.JSONDecodeError:
        return None


def merge_predictions(new_preds, html_content):
    """
    将新预测合并到 HTML 中：更新已有比赛、追加新比赛、保留 result/amount
    """
    match = re.search(r"predictions:\s*\[(.*?)\]\s*,", html_content, re.DOTALL)
    existing = []
    if match:
        parsed = _parse_js_array(match.group(1))
        if parsed:
            existing = parsed
            print(f"📋 现有 {len(existing)} 场比赛记录")
        else:
            print("⚠️  解析已有 predictions 失败，将完全替换")

    # 索引: (date + match) -> position
    existing_map = {}
    for i, ep in enumerate(existing):
        key = f"{ep.get('date','')}|{ep.get('match','')}"
        existing_map[key] = i

    updated_count = 0
    new_count = 0
    for np in new_preds:
        key = f"{np['date']}|{np['match']}"
        if key in existing_map:
            # 更新 —— 保留已有的 result/amount
            idx = existing_map[key]
            old = existing[idx]
            existing[idx] = {**np, "result": old.get("result"), "amount": old.get("amount", 0)}
            updated_count += 1
        else:
            existing.append(np)
            new_count += 1

    print(f"🔀 合并后共 {len(existing)} 场比赛 (新增 {new_count}, 更新 {updated_count})")
    return existing


def update_html(merged_preds, html_content):
    """替换 HTML 中的 predictions 数组"""
    # 生成新的 JS 数组（格式与手工编写一致）
    lines = []
    for p in merged_preds:
        match_name = json.dumps(p["match"], ensure_ascii=False)
        v3_str = json.dumps(p.get("v3", "?"), ensure_ascii=False)
        v4_str = json.dumps(p.get("v4", "?"), ensure_ascii=False)
        result_val = p.get("result")
        result_str = json.dumps(result_val) if result_val is not None else "null"
        lines.append(
            f"    {{ date: {json.dumps(p['date'])}, match: {match_name}, "
            f"odds_h: {p['odds_h']}, odds_d: {p['odds_d']}, odds_a: {p['odds_a']}, "
            f"score: {json.dumps(p['score'])}, "
            f"v3: {v3_str}, v3_conf: {p['v3_conf']}, "
            f"v4: {v4_str}, v4_conf: {p['v4_conf']}, "
            f"amount: {p.get('amount', 0)}, result: {result_str} }}"
        )
    new_array = "[\n" + ",\n".join(lines) + "\n  ]"

    # 替换 predictions 数组
    updated = re.sub(
        r"(predictions:\s*)\[.*?\]",
        r"\1" + new_array,
        html_content,
        count=1,
        flags=re.DOTALL
    )
    return updated


def git_push(commit_msg=None):
    """提交并推送到 GitHub"""
    os.chdir(SITE_DIR)
    
    # 检查是否有变更
    result = subprocess.run(
        ["git", "status", "--porcelain", "index.html"],
        capture_output=True, text=True
    )
    if not result.stdout.strip():
        print("✅ 无变更，跳过推送")
        return True

    if commit_msg is None:
        commit_msg = f"📊 更新预测 {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    subprocess.run(["git", "add", "index.html"], check=True)
    subprocess.run(["git", "commit", "-m", commit_msg], check=True)
    result = subprocess.run(["git", "push"], capture_output=True, text=True)
    
    if result.returncode == 0:
        print("🚀 已推送到 GitHub Pages!")
        print("   https://luofujie0510.github.io/football-dashboard/")
        return True
    else:
        print(f"❌ 推送失败:\n{result.stderr}")
        return False


def main():
    # 1. 找 JSON
    if len(sys.argv) > 1:
        json_path = os.path.join(REPORTS_DIR, sys.argv[1])
    else:
        json_path = find_latest_json()

    if not os.path.exists(json_path):
        print(f"❌ 文件不存在: {json_path}")
        sys.exit(1)

    print(f"📂 使用: {json_path}")

    # 2. 读取 HTML
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()

    # 3. 加载预测
    new_preds = load_predictions(json_path)

    # 4. 合并
    merged = merge_predictions(new_preds, html_content)

    # 5. 更新 HTML
    updated_html = update_html(merged, html_content)

    # 6. 写入
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(updated_html)

    print(f"✏️  已更新 {INDEX_PATH}")

    # 7. Git push
    git_push()


if __name__ == "__main__":
    main()
