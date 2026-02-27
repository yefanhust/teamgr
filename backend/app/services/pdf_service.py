import io
import json
import logging
from datetime import datetime, timezone, timedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
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
