#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
考研用户信息采集脚本
====================
交互式命令行问卷，收集用户背景信息，输出为 generate_plan_html.py 可用的 JSON 文件。

用法:
    python collect_user_info.py                          # 交互式采集（需要终端）
    python collect_user_info.py --output 张三.json        # 指定输出文件
    python collect_user_info.py --from-file partial.json  # 从已有数据补充
    python collect_user_info.py --template                # 零交互：直接输出完整默认 JSON
    python collect_user_info.py --batch answers.json      # 从答案文件填充+默认值 → 完整 JSON

输出文件可直接作为 generate_plan_html.py 的 --data 输入。

注意：--template 和 --batch 模式不需要终端交互，可以在任何环境运行。
"""

import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

# 修复 Windows GBK 控制台编码问题
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


# ============================================================
# 工具函数
# ============================================================

def ask(prompt: str, default: str = "", required: bool = False, options: list[str] = None, example: str = "") -> str:
    """询问用户输入，带默认值和选项提示。"""
    hint = ""
    if options:
        hint = f" [{'/'.join(options)}]"
    if default:
        hint += f" (默认: {default})"
    if example:
        hint += f" | {example}"

    while True:
        print(f"\n  {prompt}{hint}")
        answer = input("  > ").strip()
        if not answer and default:
            answer = default
        if required and not answer:
            print("  ⚠️ 此项为必填，请输入。")
            continue
        if options and answer and answer not in options:
            print(f"  ⚠️ 请输入以下选项之一: {', '.join(options)}")
            continue
        return answer


def ask_int(prompt: str, default: int = None, min_val: int = None, max_val: int = None) -> int:
    """询问整数。"""
    hint = ""
    if default is not None:
        hint += f" (默认: {default})"
    while True:
        print(f"\n  {prompt}{hint}")
        answer = input("  > ").strip()
        if not answer and default is not None:
            return default
        try:
            val = int(answer)
            if min_val is not None and val < min_val:
                print(f"  ⚠️ 请不小于 {min_val}")
                continue
            if max_val is not None and val > max_val:
                print(f"  ⚠️ 请不大于 {max_val}")
                continue
            return val
        except ValueError:
            print("  ⚠️ 请输入一个整数。")


def ask_score(prompt: str, max_score: int = 5) -> int:
    """询问 1-5 评分。"""
    return ask_int(prompt, min_val=1, max_val=max_score)


def confirm(prompt: str) -> bool:
    """是/否确认。"""
    answer = ask(prompt, default="n", options=["y", "n"])
    return answer.lower() == "y"


def section(title: str):
    """打印章节标题。"""
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")


# ============================================================
# 采集函数 - 按模块分组
# ============================================================

def collect_basic_info(data: dict):
    """采集基本信息。"""
    section("📋 第一步：基本信息")

    student = data.setdefault("student", {})

    student["name"] = ask("你的姓名或昵称", default="同学")
    student["undergrad_school"] = ask("本科院校全称", required=True, default=student.get("undergrad_school", ""),
                                       example="如: 福建农林大学")
    student["undergrad_major"] = ask("本科专业", required=True, default=student.get("undergrad_major", ""),
                                      example="如: 软件工程")
    student["target_school"] = ask("目标院校", required=True, default=student.get("target_school", ""),
                                    example="如: 厦门大学")
    student["target_major"] = ask("目标专业", required=True, default=student.get("target_major", ""),
                                   example="如: 计算机专硕")
    student["target_total_score"] = ask_int("目标总分（预估复试线附近）", default=355, min_val=200, max_val=500)

    # 考试日期
    year = datetime.now().year
    default_exam = f"{year}-12-20"
    if datetime.now().month > 12:
        default_exam = f"{year + 1}-12-20"
    student["exam_date"] = ask("初试日期 (YYYY-MM-DD)", default=default_exam)


def collect_learning_foundation(data: dict):
    """采集学习基础。"""
    section("📚 第二步：学习基础")

    student = data.setdefault("student", {})

    student["english_level"] = ask("英语水平", default="CET-4 425",
                                    example="如: CET-4 520 / CET-6 480 / 雅思6.5")
    student["math_level"] = ask("数学基础", default="期末70+",
                                 example="如: 刚学完高数 / 期末85+ / 线代未开始 / 数二不考概率")
    student["daily_hours"] = ask("每日可用学习时间", default="6-8小时",
                                  example="如: 6-8小时 / 8-10小时 / 4-6小时(在职)")
    student["is_cross_major"] = confirm("是否跨专业考研？")
    student["is_working"] = confirm("是否在职备考？")
    student["accept_retry"] = confirm("如果一战失败，是否接受二战？")

    # GPA
    gpa_rank = ask("GPA / 专业排名", default="前30%",
                    options=["前10%", "前30%", "前50%", "后50%", "不清楚"])

    # 竞赛
    has_competition = confirm("是否有竞赛/科研/项目经历？")
    if has_competition:
        competition_detail = ask("请简述（如: 蓝桥杯省二 / 大创国家级 / 论文一作）", default="无")


def collect_subject_progress(data: dict):
    """采集各科进度。"""
    section("📊 第三步：各科当前进度")

    subjects = data.setdefault("subjects", {})
    student = data.get("student", {})

    # 判断科目
    math_type = ask("数学科目", default="数二", options=["数一", "数二", "数三", "不考数学"])
    is_408 = confirm("专业课是否考 408 统考？")

    print("\n  --- 各科进度 (0-100%，粗略估计即可) ---")

    if math_type != "不考数学":
        math_pct = ask_int(f"{math_type} 当前进度 (%)", default=30, min_val=0, max_val=100)
        math_target = ask_int(f"{math_type} 目标分数", default=115, min_val=50, max_val=150)
        subjects[math_type] = {"progress_pct": math_pct, "target_score": math_target}

    if is_408:
        cs_pct = ask_int("408专业课 当前进度 (%)", default=30, min_val=0, max_val=100)
        cs_target = ask_int("408专业课 目标分数", default=115, min_val=50, max_val=150)
        subjects["408专业课"] = {"progress_pct": cs_pct, "target_score": cs_target}
    else:
        major_name = ask("专业课科目名称", default="专业课")
        major_pct = ask_int(f"{major_name} 当前进度 (%)", default=30, min_val=0, max_val=100)
        major_target = ask_int(f"{major_name} 目标分数", default=115, min_val=50, max_val=150)
        subjects[major_name] = {"progress_pct": major_pct, "target_score": major_target}

    eng_type = ask("英语科目", default="英语二", options=["英语一", "英语二"])
    eng_pct = ask_int(f"{eng_type} 当前进度 (%)", default=50, min_val=0, max_val=100)
    eng_target = ask_int(f"{eng_type} 目标分数", default=72, min_val=50, max_val=100)
    subjects[eng_type] = {"progress_pct": eng_pct, "target_score": eng_target}

    pol_pct = ask_int("政治 当前进度 (%)（未开始填0）", default=0, min_val=0, max_val=100)
    pol_target = ask_int("政治 目标分数", default=70, min_val=50, max_val=100)
    subjects["政治"] = {"progress_pct": pol_pct, "target_score": pol_target}


def collect_assessment(data: dict):
    """采集评估维度评分。"""
    section("🎯 第四步：竞争力自评 (1-5分)")

    print("  请客观评估自己在以下维度的水平：")
    print("  5=顶尖  4=较强  3=中等  2=偏弱  1=短板\n")

    dims = [
        ("学校层次", "本科院校层次 (985=5, 211=4, 双一流=3, 一本=2, 二本=1)"),
        ("专业匹配", "专业匹配度 (本专业+科研=5, 本专业=4, 相近=3, 跨但有基础=2, 零基础跨=1)"),
        ("英语水平", "英语水平 (六级600+=5, 550+=4, 425+=3, 四级425+=2, 以下=1)"),
        ("数学基础", "数学基础 (竞赛=5, 期末85+=4, 70+=3, 60+=2, 薄弱=1)"),
        ("目标难度", "目标院校难度 (B区双非=5, A区双非=4, 211=3, 985=2, C9=1) [注:分数越高=越好考]"),
        ("可用时间", "可用学习时间 (10h+=5, 8-10h=4, 6-8h=3, 4-6h=2, <4h=1)"),
    ]

    assessment = data.setdefault("assessment", {})
    radar = []

    for label, desc in dims:
        print(f"  [{label}] {desc}")
        score = ask_score(f"  {label}", max_score=5)
        radar.append({"label": label, "score": score, "max": 5})

    assessment["radar_dimensions"] = radar

    # 优势与劣势
    print()
    strengths_raw = ask("你的主要优势（用逗号分隔，如: 本专业,时间充裕,英语好）",
                         default="本专业报考,时间充裕")
    weaknesses_raw = ask("你的主要短板（用逗号分隔，如: 数学基础弱,跨专业,在职时间少）",
                          default="数学基础薄弱,目标院校竞争激烈")

    assessment["strengths"] = [s.strip() for s in strengths_raw.split(",") if s.strip()]
    assessment["weaknesses"] = [w.strip() for w in weaknesses_raw.split(",") if w.strip()]

    # 概率和加权分数（后续由 generate_plan_html.py 或人工校准）
    probability = ask_int("你自评的上岸概率 (%)", default=45, min_val=0, max_val=100)
    assessment["probability"] = probability

    # 计算加权分（基于雷达维度粗略估算）
    weights = [0.15, 0.15, 0.10, 0.10, 0.15, 0.12]
    weighted = sum(d["score"] * w for d, w in zip(radar, weights))
    assessment["weighted_score"] = round(weighted, 2)

    level = "需要努力"
    if weighted >= 4.0:
        level = "优势明显"
    elif weighted >= 3.0:
        level = "中等偏上"
    elif weighted >= 2.0:
        level = "需要努力"
    else:
        level = "挑战较大"
    assessment["level"] = level

    print(f"\n  📊 加权总分: {weighted:.2f} / 5.0 → {level}")


def collect_school_preferences(data: dict):
    """采集择校偏好。"""
    section("🏫 第五步：择校偏好（可选）")

    if not confirm("是否填写三档院校推荐？（可跳过，后续手动补充）"):
        return

    school = data.setdefault("school_selection", {})
    for tier_key, tier_label in [("sprint", "冲刺档"), ("stable", "稳妥档"), ("safety", "保底档")]:
        print(f"\n  --- {tier_label} ---")
        schools = []
        while True:
            name = ask(f"{tier_label}院校名称（回车跳过结束）", default="")
            if not name:
                break
            level = ask("  院校层次", default="211", options=["985", "211", "双一流", "双非", "省重点", "B区"])
            cutoff = ask("  近年复试线（如: 340-355）", default="未知")
            note = ask("  备注", default="")
            schools.append({
                "name": name,
                "level": level,
                "major": data.get("student", {}).get("target_major", ""),
                "cutoff": cutoff,
                "ratio": "未知",
                "probability": "",
                "note": note
            })
        if schools:
            school[tier_key] = schools

    if confirm("是否有特别的风险提示需要记录？"):
        risks_raw = ask("风险提示（逗号分隔）", default="以上分数线为估算值，请以官方为准")
        school["risk_notes"] = [r.strip() for r in risks_raw.split(",") if r.strip()]


def collect_daily_preferences(data: dict):
    """采集作息偏好。"""
    section("⏰ 第六步：作息偏好（可选）")

    if not confirm("是否填写每日作息？（可跳过使用默认模板）"):
        return

    daily = data.setdefault("daily_schedule", {})

    # 默认作息
    default_slots = [
        {"time": "08:00-08:30", "task": "晨读（英语单词）", "type": "输入型", "intensity": "低"},
        {"time": "08:30-11:30", "task": "数学 🔴", "type": "逻辑型", "intensity": "高"},
        {"time": "11:30-12:00", "task": "政治/英语过渡", "type": "输入型", "intensity": "低"},
        {"time": "12:00-13:30", "task": "午餐+午休", "type": "休息", "intensity": "低"},
        {"time": "13:30-16:30", "task": "专业课 🔴", "type": "记忆+逻辑", "intensity": "高"},
        {"time": "16:30-18:00", "task": "英语阅读+运动/晚餐", "type": "输入型", "intensity": "中"},
        {"time": "18:00-20:30", "task": "薄弱科补强/政治", "type": "灵活", "intensity": "中"},
        {"time": "20:30-21:30", "task": "错题回顾+复盘日记", "type": "规划", "intensity": "低"},
        {"time": "23:00", "task": "熄灯睡觉", "type": "休息", "intensity": "低"},
    ]
    daily["slots"] = default_slots

    min_tasks = [
        {"subject": "数学", "amount": "20道选择填空题", "time": "40分钟"},
        {"subject": "408/专业课", "amount": "1套选择题(40题)", "time": "50分钟"},
        {"subject": "政治", "amount": "50道选择题", "time": "30分钟"},
        {"subject": "英语", "amount": "2篇真题阅读", "time": "40分钟"},
    ]
    daily["minimum_tasks"] = min_tasks

    print("  ✅ 已设置默认作息和保底任务（可在 JSON 中手动调整）")


def auto_fill_defaults(data: dict):
    """自动填充 JSON 中空白的默认值。"""
    student = data.setdefault("student", {})

    # 默认值
    defaults = {
        "name": "同学",
        "undergrad_school": "未知",
        "undergrad_major": "未知",
        "target_school": "未确定",
        "target_major": "未确定",
        "target_total_score": 355,
        "english_level": "未知",
        "math_level": "未知",
        "daily_hours": "6-8小时",
        "is_cross_major": False,
        "is_working": False,
        "accept_retry": False,
        "exam_date": f"{datetime.now().year}-12-20",
    }
    for k, v in defaults.items():
        student.setdefault(k, v)

    # 默认评估
    assessment = data.setdefault("assessment", {})
    assessment.setdefault("probability", 50)
    assessment.setdefault("weighted_score", 3.0)
    assessment.setdefault("level", "需要努力")
    assessment.setdefault("strengths", ["本专业报考"])
    assessment.setdefault("weaknesses", ["目标较高"])
    assessment.setdefault("radar_dimensions", [
        {"label": "学校层次", "score": 3, "max": 5},
        {"label": "专业匹配", "score": 4, "max": 5},
        {"label": "英语水平", "score": 3, "max": 5},
        {"label": "数学基础", "score": 3, "max": 5},
        {"label": "目标难度", "score": 2, "max": 5},
        {"label": "可用时间", "score": 3, "max": 5},
    ])

    # 默认科目
    data.setdefault("subjects", {
        "数二": {"progress_pct": 35, "target_score": 115},
        "408专业课": {"progress_pct": 30, "target_score": 115},
        "政治": {"progress_pct": 0, "target_score": 70},
        "英语二": {"progress_pct": 50, "target_score": 72},
    })

    data.setdefault("school_selection", {})
    data.setdefault("study_plan", {"phases": [], "months": []})
    data.setdefault("weekly_milestones", [])
    data.setdefault("mock_exam", {
        "scores": {"数学": 0, "408专业课": 0, "政治": 0, "英语": 0, "总分": 0},
        "target_scores": {"数学": 115, "408专业课": 115, "政治": 70, "英语": 72, "总分": 355},
    })


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="考研用户信息采集 —— 交互式问卷，输出 JSON 供 generate_plan_html.py 使用",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python collect_user_info.py                           # 交互式采集
  python collect_user_info.py -o 张三.json               # 指定输出
  python collect_user_info.py --from-file partial.json   # 续填
  python collect_user_info.py --quick                    # 快速模式
  python collect_user_info.py --template                 # 零交互：输出默认模板（非TTY环境可用）
  python collect_user_info.py --batch answers.json       # 从答案文件填充（非TTY环境可用）
        """
    )
    parser.add_argument("--output", "-o", default=None, help="输出 JSON 文件路径（默认：用户数据_{姓名}.json）")
    parser.add_argument("--from-file", default=None, help="从已有 JSON 文件加载并补充缺失字段")
    parser.add_argument("--quick", action="store_true", help="快速模式：只问必填项，其余用默认值")
    parser.add_argument("--template", action="store_true", help="零交互模式：跳过所有问题，直接输出完整默认 JSON 模板")
    parser.add_argument("--batch", default=None, help="零交互模式：从指定的答案 JSON 文件读取填充，缺失字段用默认值")
    args = parser.parse_args()

    # 检测是否在交互式终端中
    is_tty = sys.stdin.isatty()
    needs_interaction = not args.template and not args.batch

    if needs_interaction and not is_tty:
        print("""
╔══════════════════════════════════════════════╗
║  ⚠️  当前环境不支持交互式输入                 ║
║                                              ║
║  请使用以下非交互模式：                       ║
║                                              ║
║  python collect_user_info.py --template       ║
║    → 直接输出完整默认 JSON，然后手动编辑       ║
║                                              ║
║  python collect_user_info.py --batch ans.json ║
║    → 从答案文件填充+自动补默认值               ║
║                                              ║
║  或在真实终端中运行交互式模式。                ║
╚══════════════════════════════════════════════╝
""")
        sys.exit(1)

    data = {}

    # 加载已有数据
    if args.from_file:
        if os.path.exists(args.from_file):
            with open(args.from_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"📂 已加载: {args.from_file}")
        else:
            print(f"❌ 文件不存在: {args.from_file}")
            sys.exit(1)

    # --- 零交互模式 ---
    if args.batch:
        if not os.path.exists(args.batch):
            print(f"❌ 答案文件不存在: {args.batch}")
            sys.exit(1)
        with open(args.batch, "r", encoding="utf-8") as f:
            answers = json.load(f)
        # 合并答案到 data（浅合并：答案覆盖默认值）
        for key in answers:
            if key in data and isinstance(data[key], dict) and isinstance(answers[key], dict):
                data[key].update(answers[key])
            else:
                data[key] = answers[key]
        print(f"📂 已加载答案: {args.batch}")

    if args.template or args.batch:
        print("⚡ 零交互模式：跳过所有问题，使用默认值填充")
        auto_fill_defaults(data)

        student_name = data.get("student", {}).get("name", "同学")
        output_path = args.output or f"用户数据_{student_name}.json"
        output_path = os.path.abspath(output_path)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"\n{'='*50}")
        print(f"  ✅ 数据已保存: {output_path}")
        print(f"  📄 文件大小: {os.path.getsize(output_path) / 1024:.1f} KB")
        print(f"\n  下一步:")
        print(f"  1. 编辑 {output_path} 填入你的真实信息")
        print(f"  2. python scripts/generate_plan_html.py --data {output_path}")
        print(f"{'='*50}\n")
        return

    # --- 交互模式 ---
    print("""
╔══════════════════════════════════════════════╗
║       🎓 考研用户信息采集                    ║
║                                              ║
║   这将帮助生成个性化的考研全程规划报告。      ║
║   所有信息仅保存在本地 JSON 文件中。          ║
║   不确定的可以跳过或填粗略值，后续再改。      ║
╚══════════════════════════════════════════════╝
""")

    # 采集
    collect_basic_info(data)
    collect_learning_foundation(data)

    if not args.quick:
        collect_subject_progress(data)
        collect_assessment(data)
        collect_school_preferences(data)
        collect_daily_preferences(data)
    else:
        print("\n  ⚡ 快速模式：跳过进度/评估/偏好（使用默认值）")

    # 补默认值
    auto_fill_defaults(data)

    # 输出
    student_name = data.get("student", {}).get("name", "同学")
    output_path = args.output or f"用户数据_{student_name}.json"
    output_path = os.path.abspath(output_path)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"  ✅ 数据已保存: {output_path}")
    print(f"  📄 文件大小: {os.path.getsize(output_path) / 1024:.1f} KB")
    print(f"\n  下一步:")
    print(f"  python scripts/generate_plan_html.py --data {output_path} --output 考研报告_{student_name}.html")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
