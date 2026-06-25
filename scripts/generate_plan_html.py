#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
考研规划报告 HTML 生成器
========================
将用户考研数据注入 HTML 模板，生成独立的、可交互的静态页面。

用法:
    python generate_plan_html.py --data user_data.json --output 报告.html
    python generate_plan_html.py --data user_data.json --template ../assets/plan-template.html

输入 JSON 格式见下方 DATA_SCHEMA 注释，或参考 test_data 变量。
"""

import json
import os
import sys
import argparse
import math
from datetime import datetime, timedelta
from pathlib import Path

# 修复 Windows GBK 控制台编码问题
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


# ============================================================
# 1. 工具函数
# ============================================================

def escape_html(text: str) -> str:
    """转义 HTML 特殊字符"""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def badged(risk_level: str) -> str:
    """根据风险等级返回 HTML badge"""
    if risk_level in ("danger", "red", "🔴", "严重落后", "危险区"):
        return '<span class="badge badge-danger">🔴 危险</span>'
    if risk_level in ("warning", "yellow", "🟡", "警戒", "有较大提升空间"):
        return '<span class="badge badge-warning">🟡 警戒</span>'
    if risk_level in ("success", "green", "🟢", "安全", "接近目标"):
        return '<span class="badge badge-success">🟢 安全</span>'
    return f'<span class="badge">{risk_level}</span>'


def progress_bar(label: str, pct: float, level: str = "primary") -> str:
    """生成进度条 HTML（带 data-subject 属性用于打卡联动）"""
    cls = {"danger": "danger", "warning": "warning", "success": "success"}.get(level, "primary")
    pct_clamped = max(0, min(100, pct))
    # 提取科目关键词用于匹配
    subject_key = label.strip()
    return f"""<div class="progress-row" data-subject="{escape_html(subject_key)}">
  <div class="progress-label"><span>{escape_html(label)}</span><span class="progress-pct">{pct_clamped:.0f}%</span></div>
  <div class="progress-bar"><div class="progress-fill {cls}" style="width:{pct_clamped}%"></div></div>
</div>"""


def color_for_pct(pct: float) -> str:
    """根据百分比返回颜色等级"""
    if pct >= 80:
        return "success"
    if pct >= 50:
        return "warning"
    return "danger"


# ============================================================
# 2. SVG 雷达图生成 (纯 SVG，无外部依赖)
# ============================================================

def generate_radar_svg(dimensions: list[dict], size: int = 320) -> str:
    """
    生成多维度雷达图 SVG。
    dimensions: [{"label":"学校层次","score":4,"max":5}, ...]
    返回完整 <svg> 标签内的内容（不含 <svg> 外层，方便模板嵌入）。
    """
    n = len(dimensions)
    if n < 3:
        return '<text x="160" y="160" text-anchor="middle" fill="#999">数据不足，无法绘制雷达图</text>'

    cx, cy, r = size / 2, size / 2, size * 0.32  # 缩小半径，给标签留空间
    angles = [2 * math.pi * i / n - math.pi / 2 for i in range(n)]

    parts = []

    # 背景网格
    for level in range(1, 6):
        level_r = r * level / 5
        points = []
        for a in angles:
            px = cx + level_r * math.cos(a)
            py = cy + level_r * math.sin(a)
            points.append(f"{px:.1f},{py:.1f}")
        opacity = 0.1 if level < 5 else 0.25
        parts.append(f'<polygon points="{" ".join(points)}" fill="none" stroke="#cbd5e1" stroke-width="1" opacity="{opacity}"/>')

    # 轴线
    for a in angles:
        ex, ey = cx + r * math.cos(a), cy + r * math.sin(a)
        parts.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="#e2e8f0" stroke-width="1"/>')

    # 数据多边形和点
    data_points = []
    for i, dim in enumerate(dimensions):
        score = dim.get("score", 0)
        max_val = dim.get("max", 5)
        ratio = max(0, min(1, score / max_val)) if max_val > 0 else 0
        px = cx + r * ratio * math.cos(angles[i])
        py = cy + r * ratio * math.sin(angles[i])
        data_points.append((f"{px:.1f},{py:.1f}", px, py))

    pts_str = " ".join(p[0] for p in data_points)
    parts.append(f'<polygon points="{pts_str}" fill="rgba(79,70,229,0.2)" stroke="#4f46e5" stroke-width="2.5" stroke-linejoin="round"/>')

    for _, px, py in data_points:
        parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="#4f46e5" stroke="white" stroke-width="2"/>')

    # 标签 — 分行显示，避免溢出
    label_r = r + 36
    for i, (dim, a) in enumerate(zip(dimensions, angles)):
        lx = cx + label_r * math.cos(a)
        ly = cy + label_r * math.sin(a)
        score = dim.get("score", 0)
        max_val = dim.get("max", 5)
        label_text = escape_html(dim["label"])

        # 根据角度确定对齐方式
        if abs(a + math.pi/2) < 0.15:  # 顶部
            anchor = "middle"; dy1, dy2 = "-0.2em", "1.1em"
        elif abs(a - math.pi/2) < 0.15:  # 底部
            anchor = "middle"; dy1, dy2 = "-0.2em", "1.1em"
        elif lx < cx:  # 左侧
            anchor = "end"; dy1, dy2 = "-0.2em", "1.1em"
        else:  # 右侧
            anchor = "start"; dy1, dy2 = "-0.2em", "1.1em"

        # 标签名（第一行）
        parts.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" dy="{dy1}" '
            f'font-size="11" fill="#334155" font-weight="500">{label_text}</text>'
        )
        # 分数（第二行，更小更淡）
        parts.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" dy="{dy2}" '
            f'font-size="10" fill="#94a3b8">{score}/{max_val}</text>'
        )

    return "\n".join(parts)


# ============================================================
# 3. HTML 片段生成器
# ============================================================

def generate_overview_table(student: dict) -> str:
    """考生画像表"""
    rows = [
        ("本科院校", student.get("undergrad_school", "未知")),
        ("本科专业", student.get("undergrad_major", "未知")),
        ("目标院校", student.get("target_school", "未确定")),
        ("目标专业", student.get("target_major", "未确定")),
        ("英语水平", student.get("english_level", "未知")),
        ("数学基础", student.get("math_level", "未知")),
        ("每日可用时间", student.get("daily_hours", "未知")),
        ("是否跨专业", "是" if student.get("is_cross_major") else "否"),
        ("是否在职", "是" if student.get("is_working") else "否"),
        ("是否接受二战", "是" if student.get("accept_retry") else "否"),
    ]
    return "\n".join(f"<tr><td><strong>{k}</strong></td><td>{escape_html(v)}</td></tr>" for k, v in rows)


def generate_progress_bars(subjects: dict) -> str:
    """各科进度条"""
    bars = []
    for name, info in subjects.items():
        pct = info.get("progress_pct", 0)
        level = color_for_pct(pct)
        bars.append(progress_bar(name, pct, level))
    return "\n".join(bars)


def generate_strengths_weaknesses(assessment: dict) -> tuple[str, str]:
    """加分项 / 薄弱项"""
    strengths = assessment.get("strengths", ["暂无数据"])
    weaknesses = assessment.get("weaknesses", ["暂无数据"])
    s_html = "\n".join(f"<li>{escape_html(s)}</li>" for s in strengths)
    w_html = "\n".join(f"<li>{escape_html(w)}</li>" for w in weaknesses)
    return s_html, w_html


def generate_school_table(schools: list[dict], tier_label: str, tier_emoji: str) -> str:
    """单档院校表格"""
    if not schools:
        return f"<h3>{tier_emoji} {tier_label}</h3><p style='color:var(--text-secondary)'>暂无推荐</p>"

    header = "<tr><th>院校</th><th>层次</th><th>专业</th><th>近年复试线</th><th>报录比</th><th>备注</th></tr>"
    rows = []
    for s in schools:
        rows.append(
            f"<tr>"
            f"<td><strong>{escape_html(s.get('name', '-'))}</strong></td>"
            f"<td>{escape_html(s.get('level', '-'))}</td>"
            f"<td>{escape_html(s.get('major', '-'))}</td>"
            f"<td>{escape_html(s.get('cutoff', '-'))}</td>"
            f"<td>{escape_html(s.get('ratio', '-'))}</td>"
            f"<td>{escape_html(s.get('note', '-'))}</td>"
            f"</tr>"
        )
    return f"<h3>{tier_emoji} {tier_label}（录取概率 {escape_html(str(schools[0].get('probability',''))) if schools else ''}）</h3>" \
           f"<div class='table-wrap'><table>{header}{''.join(rows)}</table></div>"


def generate_school_analysis(school_data: dict) -> str:
    """完整的择校分析 HTML"""
    parts = []
    for tier, emoji in [("sprint", "🚀 冲刺档"), ("stable", "🎯 稳妥档"), ("safety", "🛡️ 保底档")]:
        label = {"sprint": "冲刺档", "stable": "稳妥档", "safety": "保底档"}[tier]
        schools = school_data.get(tier, [])
        parts.append(generate_school_table(schools, label, emoji))

    if school_data.get("risk_notes"):
        parts.append(
            '<div class="card"><h2>⚠️ 风险提示</h2><ul>'
            + "\n".join(f"<li>{escape_html(n)}</li>" for n in school_data["risk_notes"])
            + "</ul></div>"
        )
    return "\n".join(parts)


def generate_study_plan_table(phases: list[dict]) -> str:
    """三阶段学习计划"""
    parts = []
    for ph in phases:
        name = ph.get("phase_name", "阶段")
        period = ph.get("period", "")
        rows_html = ""
        for subj in ph.get("subjects", []):
            rows_html += (
                f"<tr>"
                f"<td><strong>{escape_html(subj.get('name', '-'))}</strong></td>"
                f"<td>{escape_html(subj.get('task', '-'))}</td>"
                f"<td>{escape_html(subj.get('material', '-'))}</td>"
                f"<td>{escape_html(str(subj.get('daily_hours', '-')))}</td>"
                f"<td>{escape_html(subj.get('completion_criteria', '-'))}</td>"
                f"</tr>"
            )
        table = (
            f"<h3>{escape_html(name)}（{escape_html(period)}）</h3>"
            f"<div class='table-wrap'><table>"
            f"<tr><th>科目</th><th>任务</th><th>推荐资料</th><th>每日用时</th><th>完成标准</th></tr>"
            f"{rows_html}"
            f"</table></div>"
        )
        parts.append(table)
    return "\n".join(parts)


def generate_timeline(months: list[dict]) -> str:
    """月度时间轴"""
    items = []
    for m in months:
        items.append(
            f'<div class="timeline-item">'
            f'<div class="time">{escape_html(m.get("month", "-"))}</div>'
            f'<div><strong>{escape_html(m.get("title", "-"))}</strong></div>'
            f'<div style="color:var(--text-secondary);font-size:.9rem;">{escape_html(m.get("detail", ""))}</div>'
            f'</div>'
        )
    return "\n".join(items)


def generate_daily_schedule(slots: list[dict]) -> str:
    """每日作息表"""
    header = "<tr><th>时间</th><th>任务</th><th>类型</th><th>强度</th></tr>"
    rows = []
    for s in slots:
        intensity_badge = {"高": "badge-danger", "中": "badge-warning", "低": "badge-success"}.get(
            s.get("intensity", "中"), ""
        )
        rows.append(
            f"<tr>"
            f"<td><strong>{escape_html(s.get('time', '-'))}</strong></td>"
            f"<td>{escape_html(s.get('task', '-'))}</td>"
            f"<td>{escape_html(s.get('type', '-'))}</td>"
            f"<td><span class='badge {intensity_badge}'>{escape_html(s.get('intensity', '中'))}</span></td>"
            f"</tr>"
        )
    return f"<div class='table-wrap'><table>{header}{''.join(rows)}</table></div>"


def generate_minimum_tasks(tasks: list[dict]) -> str:
    """每日保底任务表"""
    header = "<tr><th>科目</th><th>最低量</th><th>用时</th></tr>"
    rows = []
    for t in tasks:
        rows.append(
            f"<tr>"
            f"<td><strong>{escape_html(t.get('subject', '-'))}</strong></td>"
            f"<td>{escape_html(t.get('amount', '-'))}</td>"
            f"<td>{escape_html(t.get('time', '-'))}</td>"
            f"</tr>"
        )
    return f"<table>{header}{''.join(rows)}</table>"


def generate_checkin_items(tasks: list[dict]) -> str:
    """每日保底打卡项（checkboxes），带 data-subject 关联进度条"""
    if not tasks:
        return '<p style="color:var(--text-secondary)">暂无打卡项</p>'
    items = []
    for i, t in enumerate(tasks):
        subj = escape_html(t.get('subject', ''))
        amt = escape_html(t.get('amount', ''))
        tm = escape_html(t.get('time', ''))
        cid = f"chk-{i}"
        # 提取科目关键词用于匹配进度条（如 "数二"→"数二", "408"→"408专业课"）
        subject_key = subj.replace("（9月后）", "").strip()
        items.append(
            f'<div class="check-item">'
            f'<input type="checkbox" id="{cid}" data-subject="{escape_html(subject_key)}" data-increment="2">'
            f'<label for="{cid}">{subj}：{amt}（{tm}）</label>'
            f'</div>'
        )
    return "\n".join(items)


def generate_weekly_milestones(weeks: list[dict]) -> str:
    """每周里程碑表"""
    header = "<tr><th>周次</th><th>数学一</th><th>408</th><th>政治</th><th>英语</th></tr>"
    rows = []
    for w in weeks:
        cells = [
            f"<td><strong>{escape_html(w.get('week', '-'))}</strong></td>",
            f"<td>{escape_html(w.get('math', '-'))}</td>",
            f"<td>{escape_html(w.get('cs408', '-'))}</td>",
            f"<td>{escape_html(w.get('politics', '-'))}</td>",
            f"<td>{escape_html(w.get('english', '-'))}</td>",
        ]
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"<table>{header}{''.join(rows)}</table>"


def generate_mock_exam_content(mock: dict) -> str:
    """模考评估完整内容 —— 这是最复杂的模块"""
    parts = []

    # 成绩对标
    scores = mock.get("scores", {})
    target = mock.get("target_scores", {})
    parts.append('<div class="card"><h2>一、成绩对标</h2>')
    parts.append('<div class="table-wrap"><table>')
    parts.append("<tr><th>科目</th><th>模考成绩</th><th>目标分数</th><th>差距</th><th>判断</th></tr>")
    for subj in ["数学", "408专业课", "政治", "英语"]:
        s = scores.get(subj, "—")
        t = target.get(subj, "—")
        gap = f"-{t - s}" if isinstance(s, (int, float)) and isinstance(t, (int, float)) and t > s else ("—" if s == "—" else f"+{s - t}")
        risk = "danger" if (isinstance(s, (int, float)) and isinstance(t, (int, float)) and (t - s) >= 20) else "warning" if (t - s) >= 8 else "success"
        parts.append(f"<tr><td><strong>{subj}</strong></td><td>{s}</td><td>{t}</td><td class='risk-high'>{gap}</td><td>{badged(risk)}</td></tr>")
    total_s = scores.get("总分", "—")
    total_t = target.get("总分", "—")
    total_gap = f"-{total_t - total_s}" if isinstance(total_s, (int, float)) and isinstance(total_t, (int, float)) else "—"
    parts.append(f"<tr style='font-weight:700;background:#f8fafc'><td>总分</td><td>{total_s}</td><td>{total_t}</td><td class='risk-high'>{total_gap}</td><td>{badged('danger')}</td></tr>")
    parts.append("</table></div>")
    if mock.get("score_analysis"):
        parts.append(f"<p style='margin-top:12px;color:var(--text-secondary)'>{escape_html(mock['score_analysis'])}</p>")
    parts.append("</div>")

    # 单科短板分析
    parts.append('<div class="card"><h2>二、单科短板深度分析</h2>')
    for subj_analysis in mock.get("subject_analysis", []):
        parts.append(f"<h3>{escape_html(subj_analysis.get('subject', ''))}</h3>")
        for li in subj_analysis.get("points", []):
            parts.append(f"<li>{escape_html(li)}</li>")
    parts.append("</div>")

    # 总分可达性推演
    if mock.get("projection"):
        parts.append('<div class="card"><h2>三、总分可达性推演</h2>')
        parts.append('<div class="table-wrap"><table>')
        parts.append("<tr><th>科目</th><th>当前</th><th>两月最大可期</th><th>乐观上限</th></tr>")
        for row in mock["projection"]:
            parts.append(
                f"<tr><td><strong>{escape_html(row.get('subject','-'))}</strong></td>"
                f"<td>{escape_html(str(row.get('current','-')))}</td>"
                f"<td>{escape_html(str(row.get('expected','-')))}</td>"
                f"<td>{escape_html(str(row.get('optimistic','-')))}</td></tr>"
            )
        parts.append("</table></div>")
        if mock.get("projection_conclusion"):
            parts.append(f"<p style='margin-top:12px;font-weight:600;'>{escape_html(mock['projection_conclusion'])}</p>")
        parts.append("</div>")

    # 调整建议（方案对比）
    if mock.get("plans"):
        parts.append('<div class="card"><h2>四、调整建议</h2>')
        parts.append('<div class="table-wrap"><table>')
        parts.append("<tr><th>方案</th><th>目标院校</th><th>层次</th><th>预估复试线</th><th>你的中性预期</th><th>差距</th><th>成功率</th></tr>")
        for plan in mock["plans"]:
            parts.append(
                f"<tr><td><strong>{escape_html(plan.get('label','-'))}</strong></td>"
                f"<td>{escape_html(plan.get('school','-'))}</td>"
                f"<td>{escape_html(plan.get('level','-'))}</td>"
                f"<td>{escape_html(str(plan.get('cutoff','-')))}</td>"
                f"<td>{escape_html(str(plan.get('expected','-')))}</td>"
                f"<td>{escape_html(str(plan.get('gap','-')))}</td>"
                f"<td><strong>{escape_html(str(plan.get('success_rate','-')))}</strong></td></tr>"
            )
        parts.append("</table></div>")
        if mock.get("recommendation"):
            parts.append(f"<p style='margin-top:12px;'>{escape_html(mock['recommendation'])}</p>")
        parts.append("</div>")

    # 刷题优先级 + 政治时间轴 + 每周里程碑等已在其他 tab 展示
    # 这里加上心态调节
    if mock.get("mindset_advice"):
        parts.append('<div class="card"><h2>五、心态调节方案</h2>')
        for item in mock["mindset_advice"]:
            parts.append(
                f"<details><summary>{escape_html(item.get('title',''))}</summary>"
                f"<div class='details-content'><p>{escape_html(item.get('content',''))}</p></div></details>"
            )
        parts.append("</div>")

    # 下次评估
    if mock.get("next_eval"):
        parts.append(
            f'<div class="card" style="background:var(--primary-light);border-left:4px solid var(--primary)">'
            f'<h2>📅 下次评估时间</h2><p>{escape_html(mock["next_eval"])}</p></div>'
        )

    return "\n".join(parts)


# ============================================================
# 4. 主生成逻辑
# ============================================================

# 模考评估中使用的标准科目键名
MOCK_SUBJECT_KEYS = ["数学", "408专业课", "政治", "英语", "总分"]

# subjects 中可能出现的科目别名 → 标准名
SUBJECT_ALIAS_MAP = {
    "数学一": "数学", "数学二": "数学", "数学三": "数学",
    "数一": "数学", "数二": "数学", "数三": "数学",
    "数学": "数学",
    "英语一": "英语", "英语二": "英语", "英语": "英语",
    "408": "408专业课", "408专业课": "408专业课",
    "政治": "政治",
}


def validate_and_normalize_data(data: dict):
    """
    校验用户数据完整性，修正常见字段错误。
    返回 (warnings: list[str], errors: list[str])。
    errors 不为空时数据不可用；warnings 为提醒事项。
    """
    warnings = []
    errors = []

    student = data.get("student", {})
    subjects = data.get("subjects", {})
    assessment = data.get("assessment", {})
    mock = data.get("mock_exam", {})

    # 1. 检查必要顶层字段
    for field in ["student", "subjects", "assessment"]:
        if field not in data or not data[field]:
            errors.append(f"缺少必要字段: {field}")

    # 2. 检查 subjects 是否为空
    if not subjects:
        errors.append("subjects 为空，无法生成进度条。请填写至少一科的学习进度。")

    # 3. 校验 mock_exam.scores 的键名
    mock_scores = mock.get("scores", {})
    mock_targets = mock.get("target_scores", {})

    if mock_scores:
        # 检查是否有总分
        if "总分" not in mock_scores:
            # 尝试自动计算
            course_total = 0
            count = 0
            for key in mock_scores:
                if key != "总分" and isinstance(mock_scores[key], (int, float)):
                    course_total += mock_scores[key]
                    count += 1
            if count >= 3:
                mock_scores["总分"] = course_total
                warnings.append(f"mock_exam.scores 缺少「总分」字段，已自动计算为 {course_total}")

        # 检查科目键名是否在标准列表中
        for key in list(mock_scores.keys()):
            if key == "总分":
                continue
            if key not in MOCK_SUBJECT_KEYS:
                found = False
                for alias, std in SUBJECT_ALIAS_MAP.items():
                    if key == alias and std in MOCK_SUBJECT_KEYS:
                        # 自动修正键名
                        old_val = mock_scores.pop(key)
                        mock_scores[std] = old_val
                        warnings.append(f"mock_exam.scores 中「{key}」已自动修正为「{std}」")
                        found = True
                        break
                if not found:
                    warnings.append(f"mock_exam.scores 中存在未知科目「{key}」，模考成绩表可能显示为「—」")

    # 同样修正 target_scores
    if mock_targets:
        if "总分" not in mock_targets and "总分" not in mock_scores:
            course_total_t = 0
            count_t = 0
            for key in mock_targets:
                if key != "总分" and isinstance(mock_targets[key], (int, float)):
                    course_total_t += mock_targets[key]
                    count_t += 1
            if count_t >= 3:
                mock_targets["总分"] = course_total_t
                warnings.append(f"mock_exam.target_scores 缺少「总分」字段，已自动计算为 {course_total_t}")

        for key in list(mock_targets.keys()):
            if key == "总分":
                continue
            if key not in MOCK_SUBJECT_KEYS:
                for alias, std in SUBJECT_ALIAS_MAP.items():
                    if key == alias and std in MOCK_SUBJECT_KEYS:
                        old_val = mock_targets.pop(key)
                        mock_targets[std] = old_val
                        break

    # 4. 检查 subject_analysis 引用的科目
    for sa in mock.get("subject_analysis", []):
        subj_name = sa.get("subject", "")
        if subj_name:
            matched = False
            for std_key in MOCK_SUBJECT_KEYS:
                if std_key in subj_name:
                    matched = True
                    break
            if not matched:
                for alias in SUBJECT_ALIAS_MAP:
                    if alias in subj_name:
                        matched = True
                        break
            if not matched:
                warnings.append(f"subject_analysis 中的科目「{subj_name}」无法匹配标准科目名，分析内容可能无法显示在正确位置")

    # 5. 检查关键 student 字段
    for field in ["name", "target_school", "target_major"]:
        if not student.get(field):
            warnings.append(f"student.{field} 为空，报告中对应位置将显示默认值")

    # 6. subjects 进度值范围检查
    for name, info in subjects.items():
        pct = info.get("progress_pct", -1)
        if isinstance(pct, (int, float)) and (pct < 0 or pct > 100):
            warnings.append(f"subjects.{name}.progress_pct = {pct}，超出 0-100 范围，已自动修正")
            info["progress_pct"] = max(0, min(100, pct))

    return warnings, errors


def generate_plan_html(data: dict, template_path: str) -> str:
    """
    主入口：根据用户数据生成完整的 HTML 报告。
    参数 data 的 JSON 结构见函数末尾的 DATA_SCHEMA 注释。
    """
    # —— 数据校验 ——
    warnings, errors = validate_and_normalize_data(data)
    if errors:
        err_msg = "❌ 用户数据存在以下错误，无法生成报告：\n"
        for e in errors:
            err_msg += f"  • {e}\n"
        err_msg += "\n请修正后重试。参考数据结构见 scripts/test_data.json"
        raise ValueError(err_msg)
    if warnings:
        print("⚠️ 数据校验提醒：", file=sys.stderr)
        for w in warnings:
            print(f"  • {w}", file=sys.stderr)
        print(file=sys.stderr)

    # —— 正文生成 ——
    student = data.get("student", {})
    assessment = data.get("assessment", {})
    subjects = data.get("subjects", {})
    school_data = data.get("school_selection", {})
    study_plan = data.get("study_plan", {})
    daily = data.get("daily_schedule", {})
    weeks = data.get("weekly_milestones", [])
    mock = data.get("mock_exam", {})

    # 读取模板
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    # 简单字符串替换
    now = datetime.now()
    exam_date_str = student.get("exam_date", f"{now.year}-12-20")
    try:
        exam_date = datetime.strptime(exam_date_str, "%Y-%m-%d")
    except ValueError:
        exam_date = datetime(now.year, 12, 20)

    replacements = {
        "{{STUDENT_NAME}}": escape_html(student.get("name", "同学")),
        "{{TARGET_SCHOOL}}": escape_html(student.get("target_school", "未确定")),
        "{{TARGET_MAJOR}}": escape_html(student.get("target_major", "")),
        "{{GEN_DATE}}": now.strftime("%Y年%m月%d日"),
        "{{GEN_DATETIME}}": now.strftime("%Y-%m-%d %H:%M:%S"),
        "{{TOTAL_SCORE}}": escape_html(str(student.get("target_total_score", "—"))),
        "{{PROBABILITY}}": escape_html(str(assessment.get("probability", "—"))),
        "{{EXAM_DATE}}": exam_date.strftime("%Y-%m-%d"),
        "{{WEIGHTED_SCORE}}": escape_html(str(assessment.get("weighted_score", "—"))),
        "{{ASSESSMENT_LEVEL}}": escape_html(assessment.get("level", "—")),
        "{{XLSX_PATH}}": "",
    }

    for k, v in replacements.items():
        html = html.replace(k, v)

    # 复杂 HTML 片段
    html = html.replace("{{OVERVIEW_TABLE}}", generate_overview_table(student))

    # 雷达图
    radar_dims = assessment.get("radar_dimensions", [])
    html = html.replace("{{RADAR_SVG}}", generate_radar_svg(radar_dims))

    # 加分/薄弱
    s_html, w_html = generate_strengths_weaknesses(assessment)
    html = html.replace("{{STRENGTHS}}", s_html)
    html = html.replace("{{WEAKNESSES}}", w_html)

    # 进度条
    html = html.replace("{{PROGRESS_BARS}}", generate_progress_bars(subjects))

    # 择校分析
    html = html.replace("{{SCHOOL_ANALYSIS}}", generate_school_analysis(school_data))

    # 学习计划
    phases = study_plan.get("phases", [])
    html = html.replace("{{STUDY_PLAN}}", generate_study_plan_table(phases))
    months = study_plan.get("months", [])
    html = html.replace("{{TIMELINE}}", generate_timeline(months))

    # 每日作息
    slots = daily.get("slots", [])
    html = html.replace("{{DAILY_SCHEDULE_TABLE}}", generate_daily_schedule(slots))

    # 保底任务
    min_tasks = daily.get("minimum_tasks", [])
    html = html.replace("{{MINIMUM_TASKS}}", generate_minimum_tasks(min_tasks))
    html = html.replace("{{CHECKIN_ITEMS}}", generate_checkin_items(min_tasks))

    # 每周里程碑
    html = html.replace("{{WEEKLY_MILESTONES}}", generate_weekly_milestones(weeks))

    # 模考评估
    html = html.replace("{{MOCK_EXAM_CONTENT}}", generate_mock_exam_content(mock))

    return html


# ============================================================
# 5. CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="考研规划报告 HTML 生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python generate_plan_html.py --data input.json --output 我的报告.html
  python generate_plan_html.py --data input.json --template ../assets/plan-template.html
  python generate_plan_html.py --data input.json --print  # 输出到 stdout

输入 JSON 格式参考本脚本末尾的 test_data。
        """
    )
    parser.add_argument("--data", required=True, help="用户数据 JSON 文件路径")
    parser.add_argument("--template", default=None, help="HTML 模板路径（默认使用 ../assets/plan-template.html）")
    parser.add_argument("--output", "-o", default=None, help="输出 HTML 文件路径（默认：考研规划报告_{姓名}.html）")
    parser.add_argument("--print", action="store_true", help="输出到 stdout 而不是写文件")
    args = parser.parse_args()

    # 读取用户数据
    try:
        with open(args.data, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ 数据文件不存在: {args.data}", file=sys.stderr)
        print(f"   请先运行 collect_user_info.py 采集数据，或检查路径是否正确。", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ 读取用户数据失败：JSON 格式有误。", file=sys.stderr)
        print(f"   错误位置: 第 {e.lineno} 行，第 {e.colno} 列", file=sys.stderr)
        print(f"   错误详情: {e.msg}", file=sys.stderr)
        print(f"   请检查文件: {args.data}", file=sys.stderr)
        print(f"   提示: 重新运行 collect_user_info.py 可生成格式正确的 JSON。", file=sys.stderr)
        sys.exit(1)
    except UnicodeDecodeError as e:
        print(f"❌ 文件编码错误: {args.data}", file=sys.stderr)
        print(f"   请确保文件使用 UTF-8 编码保存。", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ 读取数据文件时发生未知错误: {e}", file=sys.stderr)
        sys.exit(1)

    # 确定模板路径
    script_dir = Path(__file__).resolve().parent
    if args.template:
        template_path = args.template
    else:
        template_path = script_dir.parent / "assets" / "plan-template.html"

    if not os.path.exists(template_path):
        print(f"❌ HTML 模板文件不存在: {template_path}", file=sys.stderr)
        print(f"   请确认 assets/plan-template.html 文件未被删除或移动。", file=sys.stderr)
        sys.exit(1)

    # 生成 HTML
    try:
        html = generate_plan_html(data, str(template_path))
    except ValueError as e:
        # 数据校验失败（validate_and_normalize_data 抛出的错误）
        print(e, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ HTML 生成过程中出现意外错误: {e}", file=sys.stderr)
        print(f"   请检查 JSON 数据是否完整，或参考 scripts/test_data.json 的数据结构。", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 输出
    if args.print:
        print(html)
    else:
        student_name = data.get("student", {}).get("name", "同学")
        output_path = args.output or f"考研规划报告_{student_name}.html"
        output_path = os.path.abspath(output_path)
        xlsx_path = output_path.replace(".html", ".xlsx")

        # 注入 xlsx 路径（相对路径，同目录下）
        html = html.replace("{{XLSX_PATH}}", os.path.basename(xlsx_path))

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"✅ HTML 报告已生成: {output_path}")
        print(f"📄 文件大小: {len(html.encode('utf-8')) / 1024:.1f} KB")

        # 同步生成 Excel
        try:
            from generate_plan_xlsx import generate_plan_xlsx as gen_xlsx
            gen_xlsx(data, xlsx_path)
            print(f"✅ Excel 计划表已生成: {xlsx_path}")
            print(f"📄 文件大小: {os.path.getsize(xlsx_path) / 1024:.1f} KB")
        except Exception as e:
            print(f"⚠️ Excel 生成跳过 ({e})，可手动运行 generate_plan_xlsx.py")

        print(f"🌐 用浏览器打开 HTML 即可查看。导出按钮已关联同目录下的 xlsx 文件。")


if __name__ == "__main__":
    main()


# ============================================================
# 附录 A：输入 JSON 数据模式 (DATA SCHEMA)
# ============================================================
"""
{
  "student": {
    "name": "张三",
    "undergrad_school": "武汉某二本",
    "undergrad_major": "计算机科学与技术",
    "target_school": "武汉大学",
    "target_major": "计算机学硕",
    "target_total_score": 355,
    "english_level": "四级 460",
    "math_level": "期末 70+",
    "daily_hours": "6-8小时",
    "is_cross_major": false,
    "is_working": false,
    "accept_retry": false,
    "exam_date": "2025-12-20"
  },
  "assessment": {
    "probability": 45,
    "weighted_score": 2.8,
    "level": "需要努力",
    "strengths": ["本专业报考，基础扎实", "英语阅读能力较好"],
    "weaknesses": ["数学基础薄弱", "目标院校竞争激烈"],
    "radar_dimensions": [
      {"label": "学校层次", "score": 2, "max": 5},
      {"label": "专业匹配", "score": 5, "max": 5},
      {"label": "英语水平", "score": 3, "max": 5},
      {"label": "数学基础", "score": 2, "max": 5},
      {"label": "目标难度", "score": 2, "max": 5},
      {"label": "可用时间", "score": 3, "max": 5}
    ]
  },
  "subjects": {
    "数学一": {"progress_pct": 78, "target_score": 115},
    "408专业课": {"progress_pct": 56, "target_score": 115},
    "政治": {"progress_pct": 72, "target_score": 70},
    "英语": {"progress_pct": 91, "target_score": 68}
  },
  "school_selection": {
    "sprint": [
      {"name": "武汉大学", "level": "985", "major": "计算机学硕",
       "cutoff": "355/350/360", "ratio": "~1:1.5", "probability": "10%-30%",
       "note": "原目标，差距较大"}
    ],
    "stable": [
      {"name": "武汉理工大学", "level": "211", "major": "计算机学硕",
       "cutoff": "315/325/320", "ratio": "~1:1.3", "probability": "40%-60%",
       "note": "✅ 推荐，同城408统考"}
    ],
    "safety": [
      {"name": "中国地质大学(武汉)", "level": "211", "major": "计算机学硕",
       "cutoff": "300/310/305", "ratio": "~1:1.2", "probability": "70%+",
       "note": "保底选择"}
    ],
    "risk_notes": ["跨专业考生需确认目标院校是否接受跨考", "以上分数线为估算值，请以研招网为准"]
  },
  "study_plan": {
    "phases": [
      {
        "phase_name": "阶段一：基础阶段",
        "period": "4月-6月",
        "subjects": [
          {"name": "数学一", "task": "一轮课本知识学习+课后习题", "material": "张宇/汤家凤基础课+教材", "daily_hours": "3h", "completion_criteria": "课后基础题正确率70%+"}
        ]
      }
    ],
    "months": [
      {"month": "4月", "title": "基础阶段启动", "detail": "数学教材通读+英语核心词汇第一轮+专业课教材通读"},
      {"month": "7月", "title": "强化阶段启动", "detail": "数学1000题+英语阅读训练+政治强化课+专业课真题"}
    ]
  },
  "daily_schedule": {
    "slots": [
      {"time": "08:00-11:00", "task": "数学一", "type": "逻辑型", "intensity": "高"},
      {"time": "11:00-12:00", "task": "政治选择题/英语单词", "type": "输入型", "intensity": "低"}
    ],
    "minimum_tasks": [
      {"subject": "数学", "amount": "20道选择填空", "time": "40分钟"},
      {"subject": "408", "amount": "1套选择题(40题)", "time": "50分钟"}
    ]
  },
  "weekly_milestones": [
    {"week": "第1周", "math": "近5年真题选择填空", "cs408": "2015-2017真题按科目", "politics": "肖八选择题1刷", "english": "2018-2020阅读真题"}
  ],
  "mock_exam": {
    "scores": {"数学": 72, "408专业课": 85, "政治": 55, "英语": 62, "总分": 274},
    "target_scores": {"数学": 115, "408专业课": 115, "政治": 70, "英语": 68, "总分": 355},
    "score_analysis": "差距81分，四科中两科存在30分以上差距，属于系统性差距。",
    "subject_analysis": [
      {"subject": "数学一（72分）——最大失血点", "points": ["基础阶段有漏洞", "提分空间：72→95-100", "策略：不做难题，全力保基础分"]}
    ],
    "projection": [
      {"subject": "数学一", "current": 72, "expected": 95, "optimistic": 105},
      {"subject": "408", "current": 85, "expected": 105, "optimistic": 110},
      {"subject": "政治", "current": 55, "expected": 68, "optimistic": 72},
      {"subject": "英语", "current": 62, "expected": 65, "optimistic": 70},
      {"subject": "总分", "current": 274, "expected": 333, "optimistic": 357}
    ],
    "projection_conclusion": "中性预期333分，距离武大355还差22分；最乐观上限357仅擦线。以当前基础，不到两月冲武大成功概率<10%。",
    "plans": [
      {"label": "A：坚持", "school": "武汉大学", "level": "985", "cutoff": 355, "expected": 333, "gap": "-22", "success_rate": "<10%"},
      {"label": "B：调整 ✅", "school": "武汉理工大学", "level": "211", "cutoff": 320, "expected": 333, "gap": "+13", "success_rate": "~60%"},
      {"label": "C：保底", "school": "中国地质大学(武汉)", "level": "211", "cutoff": 305, "expected": 333, "gap": "+28", "success_rate": "~80%"}
    ],
    "recommendation": "强烈推荐方案B：换武汉理工大学。中性预期超复试线约13分，同城、同408统考、无缝切换。",
    "mindset_advice": [
      {"title": "每日10分钟复盘日记", "content": "只写今天完成了什么，禁止写后悔/对比。用"已完成"对冲"还不够好"的焦虑。"}
    ],
    "next_eval": "2周后再做完整模考。总分≥300则武理工稳了，280-300加强薄弱科，<280考虑进一步降至地大/武科大。"
  }
}
"""
