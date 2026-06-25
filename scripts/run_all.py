#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
考研规划报告一键生成器
====================
整合信息采集 → JSON 生成 → HTML 报告 + Excel 计划表 → 自动打开浏览器的完整流程。

用法:
    python run_all.py                          # 使用默认模板数据生成报告
    python run_all.py --data 我的数据.json      # 使用已有 JSON 数据
    python run_all.py --collect                # 先交互式采集再生成报告

输出:
    - 考研报告_{姓名}.html  (交互式 HTML 报告)
    - 考研报告_{姓名}.xlsx  (6 Sheet Excel 计划表)
    - 用户数据_{姓名}.json  (用户数据存档)

依赖:
    pip install -r requirements.txt
"""

import json
import os
import sys
import argparse
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

# 修复 Windows GBK 控制台编码问题
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SCRIPT_DIR = Path(__file__).resolve().parent


def print_banner():
    """打印欢迎横幅"""
    print("""
╔══════════════════════════════════════════════╗
║         🎓 考研规划报告一键生成器            ║
║                                              ║
║   整合 信息采集 → 报告生成 → 自动打开         ║
╚══════════════════════════════════════════════╝
""")


def run_collect(output_json: str) -> bool:
    """运行信息采集脚本。成功返回 True。"""
    print("📋 第 1/3 步：采集用户信息...")
    cmd = [sys.executable, str(SCRIPT_DIR / "collect_user_info.py"),
           "--template", "-o", output_json]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        print(result.stdout)
        if result.returncode != 0:
            print(f"⚠️ 采集脚本有警告（继续执行）: {result.stderr[:200] if result.stderr else ''}")
        return os.path.exists(output_json)
    except Exception as e:
        print(f"❌ 采集失败: {e}")
        return False


def run_generate_html(data_json: str, output_html: str) -> bool:
    """运行 HTML 报告生成。成功返回 True。"""
    print("📄 第 2/3 步：生成 HTML 交互式报告...")
    cmd = [sys.executable, str(SCRIPT_DIR / "generate_plan_html.py"),
           "--data", data_json, "-o", output_html]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        print(result.stdout)
        if result.returncode != 0:
            print(f"⚠️ HTML 生成有警告: {result.stderr[:300] if result.stderr else ''}")
        # 检查文件是否生成（HTML 生成成功后文件一定存在）
        if os.path.exists(output_html):
            size_kb = os.path.getsize(output_html) / 1024
            print(f"   📄 HTML 文件大小: {size_kb:.1f} KB")
        return os.path.exists(output_html)
    except Exception as e:
        print(f"❌ HTML 生成失败: {e}")
        return False


def check_xlsx(output_xlsx: str) -> bool:
    """检查 Excel 是否已由 generate_plan_html.py 同步生成。"""
    if os.path.exists(output_xlsx):
        size_kb = os.path.getsize(output_xlsx) / 1024
        print(f"   📊 Excel 文件大小: {size_kb:.1f} KB")
        return True
    else:
        print("   ⚠️ Excel 未生成（可能需要安装 openpyxl: pip install openpyxl）")
        return False


def open_in_browser(filepath: str):
    """在浏览器中打开报告。"""
    abs_path = os.path.abspath(filepath)
    print(f"🌐 第 3/3 步：在浏览器中打开报告...")
    print(f"   文件路径: {abs_path}")
    try:
        webbrowser.open(f"file:///{abs_path.replace(os.sep, '/')}")
        print("   ✅ 已打开浏览器。")
    except Exception as e:
        print(f"   ⚠️ 无法自动打开浏览器，请手动打开: {abs_path}")
        print(f"   提示: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="考研规划报告一键生成器 —— 整合采集→生成→打开",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_all.py                          # 使用默认模板数据
  python run_all.py --data 我的数据.json      # 使用已有 JSON
  python run_all.py --collect                # 先交互采集再生成
  python run_all.py --data test_data.json    # 用示例数据快速体验
        """
    )
    parser.add_argument("--data", default=None,
                        help="已有用户数据 JSON 文件（跳过采集步骤）")
    parser.add_argument("--collect", action="store_true",
                        help="强制交互式采集（即使提供了 --data）")
    parser.add_argument("--no-open", action="store_true",
                        help="不自动打开浏览器")
    args = parser.parse_args()

    print_banner()

    script_dir = Path(__file__).resolve().parent
    data_json = None

    # 第 1 步：确定数据来源
    if args.collect:
        # 强制交互采集
        data_json = str(script_dir / f"用户数据_交互采集_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        if not run_collect(data_json):
            print("❌ 信息采集失败，流程终止。")
            sys.exit(1)
    elif args.data:
        # 使用已有数据
        data_json = args.data
        if not os.path.exists(data_json):
            print(f"❌ 数据文件不存在: {data_json}")
            print("   请检查路径，或使用以下命令先采集数据：")
            print(f"   python {script_dir / 'collect_user_info.py'} --template -o {data_json}")
            sys.exit(1)
        print(f"📂 使用已有数据: {data_json}")
    else:
        # 默认：用 test_data.json 或生成模板
        test_data = script_dir / "test_data.json"
        if test_data.exists():
            data_json = str(test_data)
            print(f"📂 使用示例数据: {data_json}")
            print("   提示: 用 --collect 可以交互式采集你自己的数据")
        else:
            data_json = str(script_dir / "用户数据_模板.json")
            if not run_collect(data_json):
                print("❌ 模板生成失败，流程终止。")
                sys.exit(1)

    # 第 2 步：生成 HTML 报告
    student_name = "同学"
    try:
        with open(data_json, "r", encoding="utf-8") as f:
            user_data = json.load(f)
        student_name = user_data.get("student", {}).get("name", "同学")
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"❌ 读取用户数据失败：JSON 格式有误。")
        print(f"   错误详情: {e}")
        print(f"   请检查文件: {data_json}")
        sys.exit(1)
    except FileNotFoundError:
        print(f"❌ 数据文件不存在: {data_json}")
        sys.exit(1)

    output_dir = str(script_dir.parent)
    output_html = os.path.join(output_dir, f"考研报告_{student_name}.html")
    output_xlsx = os.path.join(output_dir, f"考研报告_{student_name}.xlsx")

    if not run_generate_html(data_json, output_html):
        print("❌ 报告生成失败，请检查上方错误信息。")
        sys.exit(1)

    # 检查 Excel
    check_xlsx(output_xlsx)

    # 第 3 步：打开浏览器
    if not args.no_open:
        print()
        open_in_browser(output_html)

    print(f"""
{'='*50}
  🎉 完成！你的考研规划报告已就绪：

  📄 HTML 报告: {output_html}
  📊 Excel 计划表: {output_xlsx}
  📋 用户数据: {data_json}

  💡 提示:
     - 编辑 {data_json} 后重新运行即可更新报告
     - HTML 报告可直接打印（Ctrl+P）或导出 Word
{'='*50}
""")


if __name__ == "__main__":
    main()
