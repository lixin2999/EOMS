"""报表导出：Excel（openpyxl）与 PDF（reportlab，内置中文 CID 字体）。

导出数据与在线报表共用 ``services.report.metrics`` 的口径，避免两套数字。
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from app.core.errors import BusinessRuleError

REPORT_TITLES = {
    "OVERVIEW": "经营总览",
    "REVENUE": "营收报表",
    "CASHFLOW": "现金流量表",
    "PROFIT": "利润表",
    "PROJECT_PNL": "项目损益表",
    "VENDOR_SPEND": "供应商支出分析",
    "APPROVAL_EFFICIENCY": "审批效率报表",
}

DETAIL_KEYS = ("monthly", "items", "rows", "trend", "evaluations")


def _label(key: str) -> str:
    return {
        "period": "期间",
        "revenue": "营收",
        "cost": "成本",
        "expense": "报销费用",
        "profit": "利润",
        "gross_profit": "毛利",
        "gross_margin": "毛利率",
        "receipt": "收款",
        "payment": "付款",
        "inflow": "现金流入",
        "outflow": "现金流出",
        "net": "净现金流",
        "cumulative": "累计净现金流",
        "amount": "金额",
        "count": "笔数",
        "project_id": "项目ID",
        "customer_id": "客户ID",
        "vendor_id": "供应商ID",
        "vendor_name": "供应商",
        "level": "等级",
        "score": "评分",
        "spend": "支出",
        "contract_amount": "合同额",
        "ratio": "占比(%)",
        "margin": "利润率",
        "biz_type": "业务类型",
        "total": "总数",
        "approved": "已通过",
        "rejected": "已驳回",
        "avg_hours": "平均耗时(小时)",
        "reject_rate": "驳回率(%)",
        "overdue_tasks": "超时任务",
        "overdue_rate": "超时率(%)",
        "budget_amount": "预算",
        "cost_variance": "成本偏差",
        "milestone_rate": "里程碑达成率",
        "year": "年度",
        "start": "开始期间",
        "end": "结束期间",
        "total_inflow": "总流入",
        "total_outflow": "总流出",
    }.get(key, key)


def _scalar_rows(payload: dict) -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    for key, value in payload.items():
        if key in DETAIL_KEYS or isinstance(value, (dict, list)):
            continue
        rows.append((_label(key), value))
    return rows


def _detail(payload: dict) -> tuple[str, list[dict]]:
    for key in DETAIL_KEYS:
        value = payload.get(key)
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return key, value
    for value in payload.values():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return "明细", value
    return "明细", []


def build_excel(report_code: str, payload: dict) -> bytes:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError as exc:  # pragma: no cover - 部署缺依赖时给出明确提示
        raise BusinessRuleError("Excel 导出组件未安装") from exc

    workbook = Workbook()
    summary = workbook.active
    summary.title = "汇总"
    title = f"{REPORT_TITLES.get(report_code, report_code)}"
    summary.append([title])
    summary["A1"].font = Font(size=14, bold=True)
    summary.append(["生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    summary.append([])
    summary.append(["指标", "数值"])
    for cell in summary[4]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDEBF7")
    for label, value in _scalar_rows(payload):
        summary.append([label, value])
    summary.column_dimensions["A"].width = 26
    summary.column_dimensions["B"].width = 24

    name, rows = _detail(payload)
    if rows:
        sheet = workbook.create_sheet(name[:31] or "明细")
        headers = list(rows[0].keys())
        sheet.append([_label(header) for header in headers])
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="DDEBF7")
            cell.alignment = Alignment(horizontal="center")
        for row in rows:
            values = []
            for header in headers:
                value = row.get(header)
                if isinstance(value, (dict, list)):
                    value = str(value)
                values.append(value)
            sheet.append(values)
        for index, header in enumerate(headers, start=1):
            width = max(len(str(_label(header))) * 2, 14)
            sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = min(width, 40)
        sheet.freeze_panes = "A2"

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def build_pdf(report_code: str, payload: dict) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:  # pragma: no cover
        raise BusinessRuleError("PDF 导出组件未安装") from exc

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        font_name = "STSong-Light"
    except Exception:  # noqa: BLE001 - 回退到默认字体
        font_name = "Helvetica"

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "EomsTitle", parent=styles["Title"], fontName=font_name, fontSize=18, leading=24
    )
    normal = ParagraphStyle("EomsNormal", parent=styles["Normal"], fontName=font_name, fontSize=10, leading=15)
    cell_style = ParagraphStyle("EomsCell", parent=normal, fontSize=8, leading=11)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=REPORT_TITLES.get(report_code, report_code),
    )
    story: list[Any] = [Paragraph(REPORT_TITLES.get(report_code, report_code), title_style), Spacer(1, 6)]
    story.append(
        Paragraph(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal)
    )
    story.append(Spacer(1, 8))

    scalar = _scalar_rows(payload)
    if scalar:
        data = [[Paragraph("指标", cell_style), Paragraph("数值", cell_style)]]
        data += [[Paragraph(str(label), cell_style), Paragraph(str(value), cell_style)] for label, value in scalar]
        table = Table(data, colWidths=[70 * mm, 70 * mm], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDEBF7")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 10))

    _, rows = _detail(payload)
    if rows:
        story.append(PageBreak())
        headers = list(rows[0].keys())[:12]
        data = [[Paragraph(_label(header), cell_style) for header in headers]]
        for row in rows[:2000]:
            data.append([Paragraph(str(row.get(header, "")), cell_style) for header in headers])
        width = 270 * mm / max(len(headers), 1)
        table = Table(data, colWidths=[width] * len(headers), repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDEBF7")),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(table)

    doc.build(story)
    return buffer.getvalue()
