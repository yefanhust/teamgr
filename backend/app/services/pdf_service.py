import io
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

# Try to register Chinese font
_chinese_font_registered = False
_FONT_PATHS = [
    # WQY fonts use TrueType outlines — reportlab compatible
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    # Noto CJK uses CFF outlines — reportlab may NOT support these
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def _ensure_chinese_font():
    global _chinese_font_registered
    if _chinese_font_registered:
        return "ChineseFont"

    for path in _FONT_PATHS:
        try:
            pdfmetrics.registerFont(TTFont("ChineseFont", path))
            _chinese_font_registered = True
            logger.info(f"Chinese font registered: {path}")
            return "ChineseFont"
        except Exception as e:
            logger.debug(f"Font {path} failed: {e}")
            continue

    logger.warning("No Chinese font found, PDF export may not render Chinese characters correctly")
    return "Helvetica"


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from a PDF file using pdfplumber."""
    import pdfplumber

    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    return "\n\n".join(text_parts)


def pdf_to_images(pdf_bytes: bytes, dpi: int = 200) -> list[bytes]:
    """Convert each PDF page to a PNG image using PyMuPDF.

    Args:
        pdf_bytes: Raw PDF file bytes
        dpi: Resolution for rendering (200 is good balance of quality vs size)

    Returns: List of PNG image bytes, one per page
    """
    import fitz  # PyMuPDF

    images = []
    zoom = dpi / 72  # 72 is the default PDF DPI
    matrix = fitz.Matrix(zoom, zoom)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page in doc:
            pix = page.get_pixmap(matrix=matrix)
            images.append(pix.tobytes("png"))
    finally:
        doc.close()

    return images


def generate_talent_card_pdf(talent_data: dict, dimensions: list[dict]) -> bytes:
    """Generate a PDF document for a talent card.

    Args:
        talent_data: dict with keys: name, email, phone, current_role, department, card_data, summary, tags
        dimensions: list of dimension definitions

    Returns: PDF file bytes
    """
    font_name = _ensure_chinese_font()
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCN", parent=styles["Title"], fontName=font_name, fontSize=22
    )
    heading_style = ParagraphStyle(
        "HeadingCN", parent=styles["Heading2"], fontName=font_name, fontSize=14,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "BodyCN", parent=styles["Normal"], fontName=font_name, fontSize=11,
        leading=16, spaceAfter=4,
    )
    tag_style = ParagraphStyle(
        "TagCN", parent=styles["Normal"], fontName=font_name, fontSize=10,
        textColor=colors.HexColor("#3B82F6"),
    )

    elements = []

    # Title
    name = talent_data.get("name", "未知")
    elements.append(Paragraph(f"人才卡 - {name}", title_style))
    elements.append(Spacer(1, 4 * mm))

    # Tags
    tags = talent_data.get("tags", [])
    if tags:
        tags_text = " | ".join(tags)
        elements.append(Paragraph(f"标签: {tags_text}", tag_style))
        elements.append(Spacer(1, 3 * mm))

    # Summary
    summary = talent_data.get("summary", "")
    if summary:
        elements.append(Paragraph(f"<b>摘要:</b> {summary}", body_style))
        elements.append(Spacer(1, 3 * mm))

    # Basic contact info
    info_lines = []
    for key, label in [("email", "邮箱"), ("phone", "电话"), ("current_role", "职位"), ("department", "部门")]:
        val = talent_data.get(key, "")
        if val:
            info_lines.append(f"<b>{label}:</b> {val}")
    if info_lines:
        for line in info_lines:
            elements.append(Paragraph(line, body_style))
        elements.append(Spacer(1, 4 * mm))

    # Card data by dimensions
    card_data = talent_data.get("card_data", {})
    for dim in dimensions:
        dim_key = dim["key"]
        dim_label = dim["label"]
        value = card_data.get(dim_key)

        if value is None or value == "" or value == [] or value == {}:
            continue

        elements.append(Paragraph(dim_label, heading_style))

        if isinstance(value, list):
            for item in value:
                elements.append(Paragraph(f"• {item}", body_style))
        elif isinstance(value, dict):
            for k, v in value.items():
                if v and v != [] and v != "":
                    if isinstance(v, list):
                        v_text = ", ".join(str(i) for i in v)
                    else:
                        v_text = str(v)
                    elements.append(Paragraph(f"<b>{k}:</b> {v_text}", body_style))
        else:
            elements.append(Paragraph(str(value), body_style))

        elements.append(Spacer(1, 3 * mm))

    # Footer
    elements.append(Spacer(1, 10 * mm))
    footer_style = ParagraphStyle(
        "FooterCN", parent=styles["Normal"], fontName=font_name, fontSize=8,
        textColor=colors.grey,
    )
    elements.append(Paragraph(
        f"生成时间: {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')} | TeaMgr人才管理系统",
        footer_style,
    ))

    doc.build(elements)
    return buffer.getvalue()


# ──────────────── Scholar Result PDF ────────────────


def _xml_escape(text: str) -> str:
    """Escape text for use in reportlab Paragraph XML markup."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _md_inline_to_xml(text: str) -> str:
    """Convert markdown inline formatting to reportlab XML tags.

    Processes: **bold**, *italic*, `code`, [text](url)
    Input text must NOT be XML-escaped yet (this function handles it).
    """
    # Escape XML first
    text = _xml_escape(text)
    # Bold
    text = re.sub(
        r"\*\*(.+?)\*\*",
        r"<b>\1</b>",
        text,
    )
    # Italic
    text = re.sub(
        r"\*(.+?)\*",
        r"<i>\1</i>",
        text,
    )
    # Inline code — just bold monospace look
    text = re.sub(
        r"`([^`]+)`",
        r"<b>\1</b>",
        text,
    )
    # Links [text](url)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" color="#3B82F6">\1</a>',
        text,
    )
    return text


def _parse_markdown_segments(text: str) -> list[dict]:
    """Parse markdown text into typed segments: heading, paragraph, table, list, code, hr."""
    lines = text.split("\n")
    segments = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Code block
        if line.strip().startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            segments.append({"type": "code", "content": "\n".join(code_lines)})
            continue

        # Table detection: line with | followed by separator line
        if (
            "|" in line
            and i + 1 < len(lines)
            and re.match(r"^\|?\s*[-:]+[-| :]*$", lines[i + 1])
        ):
            table_lines = [line, lines[i + 1]]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                table_lines.append(lines[i])
                i += 1
            segments.append({"type": "table", "content": table_lines})
            continue

        # Horizontal rule
        if re.match(r"^---+\s*$", line.strip()):
            segments.append({"type": "hr"})
            i += 1
            continue

        # Heading
        m = re.match(r"^(#{1,4})\s+(.+)$", line)
        if m:
            segments.append({"type": "heading", "level": len(m.group(1)), "content": m.group(2)})
            i += 1
            continue

        # List items (accumulate consecutive list lines)
        if re.match(r"^(\d+\.\s+|- ).+", line):
            list_items = []
            while i < len(lines) and re.match(r"^(\d+\.\s+|- ).+", lines[i]):
                item = re.sub(r"^(\d+\.\s+|- )", "", lines[i])
                list_items.append(item)
                i += 1
            segments.append({"type": "list", "items": list_items})
            continue

        # Empty line
        if not line.strip():
            i += 1
            continue

        # Regular paragraph — accumulate non-special consecutive lines
        para_lines = [line]
        i += 1
        while i < len(lines):
            next_line = lines[i]
            if (
                not next_line.strip()
                or next_line.strip().startswith("```")
                or next_line.strip().startswith("#")
                or re.match(r"^(\d+\.\s+|- ).+", next_line)
                or re.match(r"^---+\s*$", next_line.strip())
                or ("|" in next_line and i + 1 < len(lines) and re.match(r"^\|?\s*[-:]+[-| :]*$", lines[i + 1]))
            ):
                break
            para_lines.append(next_line)
            i += 1
        segments.append({"type": "paragraph", "content": "\n".join(para_lines)})

    return segments


def _parse_pipe_table(table_lines: list[str]) -> tuple[list[str], list[list[str]]]:
    """Parse pipe table lines into (headers, body_rows)."""
    rows = []
    for line in table_lines:
        line = re.sub(r"^\|", "", line)
        line = re.sub(r"\|$", "", line)
        rows.append([c.strip() for c in line.split("|")])

    if len(rows) < 2:
        return rows[0] if rows else [], []

    header = rows[0]
    body = rows[2:]  # skip separator row
    return header, body


def generate_scholar_result_pdf(
    title: str,
    answer: str,
    period_label: str = "",
    generated_at: str = "",
) -> bytes:
    """Generate a PDF document from a Scholar scheduled result.

    Args:
        title: Question title
        answer: Markdown answer text
        period_label: e.g. "2026-03-17" or "2026-W12"
        generated_at: ISO datetime string

    Returns: PDF file bytes
    """
    font_name = _ensure_chinese_font()
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    # Define styles
    title_style = ParagraphStyle(
        "ScholarTitle", parent=styles["Title"],
        fontName=font_name, fontSize=18, leading=24,
        spaceAfter=2 * mm,
    )
    subtitle_style = ParagraphStyle(
        "ScholarSubtitle", parent=styles["Normal"],
        fontName=font_name, fontSize=10, leading=14,
        textColor=colors.HexColor("#6B7280"), alignment=TA_CENTER,
        spaceAfter=6 * mm,
    )
    h1_style = ParagraphStyle(
        "ScholarH1", parent=styles["Heading1"],
        fontName=font_name, fontSize=16, leading=22,
        spaceBefore=8, spaceAfter=4,
        textColor=colors.HexColor("#1F2937"),
    )
    h2_style = ParagraphStyle(
        "ScholarH2", parent=styles["Heading2"],
        fontName=font_name, fontSize=14, leading=20,
        spaceBefore=6, spaceAfter=3,
        textColor=colors.HexColor("#1F2937"),
    )
    h3_style = ParagraphStyle(
        "ScholarH3", parent=styles["Heading3"],
        fontName=font_name, fontSize=12, leading=17,
        spaceBefore=4, spaceAfter=2,
        textColor=colors.HexColor("#374151"),
    )
    body_style = ParagraphStyle(
        "ScholarBody", parent=styles["Normal"],
        fontName=font_name, fontSize=10, leading=16,
        spaceAfter=3,
    )
    list_style = ParagraphStyle(
        "ScholarList", parent=styles["Normal"],
        fontName=font_name, fontSize=10, leading=16,
        leftIndent=12, spaceAfter=2,
    )
    code_style = ParagraphStyle(
        "ScholarCode", parent=styles["Normal"],
        fontName=font_name, fontSize=9, leading=13,
        leftIndent=8, rightIndent=8, spaceAfter=4,
        backColor=colors.HexColor("#F3F4F6"),
    )
    table_cell_style = ParagraphStyle(
        "ScholarCell", parent=styles["Normal"],
        fontName=font_name, fontSize=9, leading=13,
    )
    table_header_style = ParagraphStyle(
        "ScholarCellH", parent=styles["Normal"],
        fontName=font_name, fontSize=9, leading=13,
        textColor=colors.HexColor("#374151"),
    )
    footer_style = ParagraphStyle(
        "ScholarFooter", parent=styles["Normal"],
        fontName=font_name, fontSize=8, leading=12,
        textColor=colors.grey, alignment=TA_CENTER,
    )

    heading_styles = {1: h1_style, 2: h2_style, 3: h3_style, 4: h3_style}

    elements = []

    # Title
    elements.append(Paragraph(_xml_escape(title), title_style))

    # Subtitle (period + time)
    subtitle_parts = []
    if period_label:
        subtitle_parts.append(period_label)
    if generated_at:
        try:
            dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            cn_dt = dt.astimezone(timezone(timedelta(hours=8)))
            subtitle_parts.append(cn_dt.strftime("%Y-%m-%d %H:%M"))
        except Exception:
            subtitle_parts.append(generated_at)
    if subtitle_parts:
        elements.append(Paragraph(" · ".join(subtitle_parts), subtitle_style))

    elements.append(HRFlowable(
        width="100%", thickness=0.5,
        color=colors.HexColor("#E5E7EB"), spaceAfter=4 * mm,
    ))

    # Parse markdown and build elements
    segments = _parse_markdown_segments(answer or "")
    page_width = A4[0] - 36 * mm  # available width

    for seg in segments:
        seg_type = seg.get("type")

        if seg_type == "heading":
            level = seg.get("level", 2)
            style = heading_styles.get(level, h3_style)
            elements.append(Paragraph(_md_inline_to_xml(seg["content"]), style))

        elif seg_type == "paragraph":
            text = seg["content"].replace("\n", "<br/>")
            elements.append(Paragraph(_md_inline_to_xml(text), body_style))

        elif seg_type == "list":
            for item in seg["items"]:
                elements.append(Paragraph(
                    f"•  {_md_inline_to_xml(item)}", list_style,
                ))

        elif seg_type == "code":
            code_text = _xml_escape(seg["content"]).replace("\n", "<br/>")
            elements.append(Paragraph(code_text, code_style))

        elif seg_type == "hr":
            elements.append(HRFlowable(
                width="100%", thickness=0.5,
                color=colors.HexColor("#D1D5DB"),
                spaceBefore=3 * mm, spaceAfter=3 * mm,
            ))

        elif seg_type == "table":
            header, body = _parse_pipe_table(seg["content"])
            if not header:
                continue

            num_cols = len(header)
            col_width = page_width / num_cols

            # Build table data as Paragraphs for proper wrapping
            table_data = []
            header_row = [
                Paragraph(f"<b>{_md_inline_to_xml(h)}</b>", table_header_style)
                for h in header
            ]
            table_data.append(header_row)

            for row in body:
                cells = []
                for idx in range(num_cols):
                    cell_text = row[idx] if idx < len(row) else ""
                    cells.append(Paragraph(_md_inline_to_xml(cell_text), table_cell_style))
                table_data.append(cells)

            tbl = Table(table_data, colWidths=[col_width] * num_cols)
            tbl_style = TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#374151")),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
                ("TOPPADDING", (0, 1), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ])
            tbl.setStyle(tbl_style)
            elements.append(Spacer(1, 2 * mm))
            elements.append(tbl)
            elements.append(Spacer(1, 2 * mm))

    # Footer
    elements.append(Spacer(1, 8 * mm))
    elements.append(HRFlowable(
        width="100%", thickness=0.5,
        color=colors.HexColor("#E5E7EB"), spaceAfter=2 * mm,
    ))
    gen_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    elements.append(Paragraph(
        f"生成时间: {gen_time} | 龙图阁大学士",
        footer_style,
    ))

    doc.build(elements)
    return buffer.getvalue()


def _build_markdown_elements(
    answer: str, segments_fn, page_width: float,
    body_style, list_style, code_style,
    table_cell_style, table_header_style,
    heading_styles, font_name,
):
    """Build reportlab elements from markdown text. Shared by both PDF generators."""
    elements = []
    segments = segments_fn(answer or "")

    for seg in segments:
        seg_type = seg.get("type")

        if seg_type == "heading":
            level = seg.get("level", 2)
            style = heading_styles.get(level, heading_styles.get(3))
            elements.append(Paragraph(_md_inline_to_xml(seg["content"]), style))

        elif seg_type == "paragraph":
            text = seg["content"].replace("\n", "<br/>")
            elements.append(Paragraph(_md_inline_to_xml(text), body_style))

        elif seg_type == "list":
            for item in seg["items"]:
                elements.append(Paragraph(
                    f"•  {_md_inline_to_xml(item)}", list_style,
                ))

        elif seg_type == "code":
            code_text = _xml_escape(seg["content"]).replace("\n", "<br/>")
            elements.append(Paragraph(code_text, code_style))

        elif seg_type == "hr":
            elements.append(HRFlowable(
                width="100%", thickness=0.5,
                color=colors.HexColor("#D1D5DB"),
                spaceBefore=3 * mm, spaceAfter=3 * mm,
            ))

        elif seg_type == "table":
            header, body = _parse_pipe_table(seg["content"])
            if not header:
                continue

            num_cols = len(header)
            col_width = page_width / num_cols

            table_data = []
            header_row = [
                Paragraph(f"<b>{_md_inline_to_xml(h)}</b>", table_header_style)
                for h in header
            ]
            table_data.append(header_row)

            for row in body:
                cells = []
                for idx in range(num_cols):
                    cell_text = row[idx] if idx < len(row) else ""
                    cells.append(Paragraph(_md_inline_to_xml(cell_text), table_cell_style))
                table_data.append(cells)

            tbl = Table(table_data, colWidths=[col_width] * num_cols)
            tbl_style = TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#374151")),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
                ("TOPPADDING", (0, 1), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ])
            tbl.setStyle(tbl_style)
            elements.append(Spacer(1, 2 * mm))
            elements.append(tbl)
            elements.append(Spacer(1, 2 * mm))

    return elements


def generate_scholar_answer_pdf(
    question: str,
    answer: str,
    title: str = "龙图阁大学士",
) -> bytes:
    """Generate a PDF for a single Scholar answer.

    Args:
        question: The user's question
        answer: The assistant's markdown answer
        title: PDF title

    Returns: PDF file bytes
    """
    font_name = _ensure_chinese_font()
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "AnsTitle", parent=styles["Title"],
        fontName=font_name, fontSize=18, leading=24,
        spaceAfter=4 * mm,
    )
    question_style = ParagraphStyle(
        "AnsQuestion", parent=styles["Normal"],
        fontName=font_name, fontSize=11, leading=17,
        textColor=colors.white, backColor=colors.HexColor("#3B82F6"),
        borderPadding=(8, 10, 8, 10), spaceAfter=4 * mm,
    )
    h1_style = ParagraphStyle(
        "AnsH1", parent=styles["Heading1"],
        fontName=font_name, fontSize=16, leading=22,
        spaceBefore=8, spaceAfter=4,
        textColor=colors.HexColor("#1F2937"),
    )
    h2_style = ParagraphStyle(
        "AnsH2", parent=styles["Heading2"],
        fontName=font_name, fontSize=14, leading=20,
        spaceBefore=6, spaceAfter=3,
        textColor=colors.HexColor("#1F2937"),
    )
    h3_style = ParagraphStyle(
        "AnsH3", parent=styles["Heading3"],
        fontName=font_name, fontSize=12, leading=17,
        spaceBefore=4, spaceAfter=2,
        textColor=colors.HexColor("#374151"),
    )
    body_style = ParagraphStyle(
        "AnsBody", parent=styles["Normal"],
        fontName=font_name, fontSize=10, leading=16,
        spaceAfter=3,
    )
    list_style = ParagraphStyle(
        "AnsList", parent=styles["Normal"],
        fontName=font_name, fontSize=10, leading=16,
        leftIndent=12, spaceAfter=2,
    )
    code_style = ParagraphStyle(
        "AnsCode", parent=styles["Normal"],
        fontName=font_name, fontSize=9, leading=13,
        leftIndent=8, rightIndent=8, spaceAfter=4,
        backColor=colors.HexColor("#F3F4F6"),
    )
    table_cell_style = ParagraphStyle(
        "AnsCell", parent=styles["Normal"],
        fontName=font_name, fontSize=9, leading=13,
    )
    table_header_style = ParagraphStyle(
        "AnsCellH", parent=styles["Normal"],
        fontName=font_name, fontSize=9, leading=13,
        textColor=colors.HexColor("#374151"),
    )
    footer_style = ParagraphStyle(
        "AnsFooter", parent=styles["Normal"],
        fontName=font_name, fontSize=8, leading=12,
        textColor=colors.grey, alignment=TA_CENTER,
    )

    heading_styles = {1: h1_style, 2: h2_style, 3: h3_style, 4: h3_style}
    page_width = A4[0] - 36 * mm

    elements = []

    # Title
    elements.append(Paragraph(_xml_escape(title), title_style))

    # Question
    if question and question.strip():
        elements.append(Paragraph(_xml_escape(question), question_style))

    # Answer (markdown)
    answer_elements = _build_markdown_elements(
        answer, _parse_markdown_segments, page_width,
        body_style, list_style, code_style,
        table_cell_style, table_header_style,
        heading_styles, font_name,
    )
    elements.extend(answer_elements)

    # Footer
    elements.append(Spacer(1, 8 * mm))
    elements.append(HRFlowable(
        width="100%", thickness=0.5,
        color=colors.HexColor("#E5E7EB"), spaceAfter=2 * mm,
    ))
    gen_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    elements.append(Paragraph(
        f"导出时间: {gen_time} | 龙图阁大学士",
        footer_style,
    ))

    doc.build(elements)
    return buffer.getvalue()


def generate_scholar_conversation_pdf(
    title: str,
    messages: list[dict],
) -> bytes:
    """Generate a PDF document from a Scholar chat conversation.

    Args:
        title: Conversation title
        messages: List of message dicts with keys: question, answer, timestamp

    Returns: PDF file bytes
    """
    font_name = _ensure_chinese_font()
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ConvTitle", parent=styles["Title"],
        fontName=font_name, fontSize=18, leading=24,
        spaceAfter=2 * mm,
    )
    subtitle_style = ParagraphStyle(
        "ConvSubtitle", parent=styles["Normal"],
        fontName=font_name, fontSize=10, leading=14,
        textColor=colors.HexColor("#6B7280"), alignment=TA_CENTER,
        spaceAfter=6 * mm,
    )
    question_style = ParagraphStyle(
        "ConvQuestion", parent=styles["Normal"],
        fontName=font_name, fontSize=11, leading=17,
        textColor=colors.white, backColor=colors.HexColor("#3B82F6"),
        borderPadding=(8, 10, 8, 10), spaceAfter=3 * mm,
        spaceBefore=4 * mm,
    )
    question_label_style = ParagraphStyle(
        "ConvQLabel", parent=styles["Normal"],
        fontName=font_name, fontSize=8, leading=12,
        textColor=colors.HexColor("#9CA3AF"), spaceBefore=6 * mm,
    )
    h1_style = ParagraphStyle(
        "ConvH1", parent=styles["Heading1"],
        fontName=font_name, fontSize=16, leading=22,
        spaceBefore=8, spaceAfter=4,
        textColor=colors.HexColor("#1F2937"),
    )
    h2_style = ParagraphStyle(
        "ConvH2", parent=styles["Heading2"],
        fontName=font_name, fontSize=14, leading=20,
        spaceBefore=6, spaceAfter=3,
        textColor=colors.HexColor("#1F2937"),
    )
    h3_style = ParagraphStyle(
        "ConvH3", parent=styles["Heading3"],
        fontName=font_name, fontSize=12, leading=17,
        spaceBefore=4, spaceAfter=2,
        textColor=colors.HexColor("#374151"),
    )
    body_style = ParagraphStyle(
        "ConvBody", parent=styles["Normal"],
        fontName=font_name, fontSize=10, leading=16,
        spaceAfter=3,
    )
    list_style = ParagraphStyle(
        "ConvList", parent=styles["Normal"],
        fontName=font_name, fontSize=10, leading=16,
        leftIndent=12, spaceAfter=2,
    )
    code_style = ParagraphStyle(
        "ConvCode", parent=styles["Normal"],
        fontName=font_name, fontSize=9, leading=13,
        leftIndent=8, rightIndent=8, spaceAfter=4,
        backColor=colors.HexColor("#F3F4F6"),
    )
    table_cell_style = ParagraphStyle(
        "ConvCell", parent=styles["Normal"],
        fontName=font_name, fontSize=9, leading=13,
    )
    table_header_style = ParagraphStyle(
        "ConvCellH", parent=styles["Normal"],
        fontName=font_name, fontSize=9, leading=13,
        textColor=colors.HexColor("#374151"),
    )
    footer_style = ParagraphStyle(
        "ConvFooter", parent=styles["Normal"],
        fontName=font_name, fontSize=8, leading=12,
        textColor=colors.grey, alignment=TA_CENTER,
    )

    heading_styles = {1: h1_style, 2: h2_style, 3: h3_style, 4: h3_style}
    page_width = A4[0] - 36 * mm

    elements = []

    # Title
    elements.append(Paragraph(_xml_escape(title), title_style))
    elements.append(Paragraph(
        f"龙图阁大学士 · 共 {len(messages)} 轮对话",
        subtitle_style,
    ))
    elements.append(HRFlowable(
        width="100%", thickness=0.5,
        color=colors.HexColor("#E5E7EB"), spaceAfter=4 * mm,
    ))

    # Messages
    for i, msg in enumerate(messages):
        question = msg.get("question", "")
        answer = msg.get("answer", "")
        timestamp = msg.get("timestamp", "")

        # Time label
        time_str = ""
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                time_str = timestamp
        elements.append(Paragraph(
            f"第 {i + 1} 轮" + (f"  {time_str}" if time_str else ""),
            question_label_style,
        ))

        # User question
        elements.append(Paragraph(_xml_escape(question), question_style))

        # Assistant answer (markdown)
        if answer and answer.strip():
            answer_elements = _build_markdown_elements(
                answer, _parse_markdown_segments, page_width,
                body_style, list_style, code_style,
                table_cell_style, table_header_style,
                heading_styles, font_name,
            )
            elements.extend(answer_elements)

    # Footer
    elements.append(Spacer(1, 8 * mm))
    elements.append(HRFlowable(
        width="100%", thickness=0.5,
        color=colors.HexColor("#E5E7EB"), spaceAfter=2 * mm,
    ))
    gen_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    elements.append(Paragraph(
        f"导出时间: {gen_time} | 龙图阁大学士",
        footer_style,
    ))

    doc.build(elements)
    return buffer.getvalue()
