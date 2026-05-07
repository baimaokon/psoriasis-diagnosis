import io
from datetime import datetime
from pathlib import Path

from fpdf import FPDF
from flask import current_app
from PIL import Image


# 使用 Windows 系统黑体字体确保 PDF 中文正常显示
# 部署到 Linux 服务器时需替换为对应中文字体路径（如 /usr/share/fonts/truetype/wqy/wqy-zenhei.ttc）
FONT_PATH = Path("C:/Windows/Fonts/simhei.ttf")


class DiagnosisReport(FPDF):
    """A4 诊断报告 PDF，基于 fpdf2 生成，支持中文渲染"""
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(True, 15)
        if FONT_PATH.exists():
            self.add_font("cjk", "", str(FONT_PATH), uni=True)
            self.add_font("cjk", "B", str(FONT_PATH), uni=True)
        else:
            self.add_font("cjk", "", "Helvetica")
            self.add_font("cjk", "B", "Helvetica-Bold")
        self._has_cjk = FONT_PATH.exists()

    # 每次 add_page 后自动调用
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("cjk", "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 6, "银屑病图像辅助诊断系统 - 诊断报告", align="C")
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("cjk", "", 7)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"第 {self.page_no()} 页", align="C")

    def _section_title(self, text):
        self.set_font("cjk", "B", 13)
        self.set_text_color(64, 128, 255)
        self.cell(0, 8, text)
        self.ln(3)
        self.set_draw_color(64, 128, 255)
        self.set_line_width(0.5)
        self.line(self.get_x(), self.get_y(), self.get_x() + 190, self.get_y())
        self.ln(5)

    def _info_row(self, label, value):
        self.set_font("cjk", "B", 10)
        self.set_text_color(80, 80, 80)
        self.cell(28, 7, f"{label}：")
        self.set_font("cjk", "", 10)
        self.set_text_color(40, 40, 40)
        self.cell(0, 7, str(value) if value else "-")
        self.ln(7)

    def _embed_image_fit(self, image_path: str, max_w: float, max_h: float):
        """将图片按比例缩放嵌入 PDF"""
        if not image_path or not Path(image_path).exists():
            self.set_font("cjk", "", 10)
            self.cell(0, 10, "(图片不可用)", align="C")
            return
        try:
            with Image.open(image_path) as img:
                iw, ih = img.size
        except Exception:
            return
        scale = min(max_w / iw, max_h / ih)
        w, h = iw * scale, ih * scale
        x = self.get_x() + (max_w - w) / 2
        y = self.get_y()
        self.image(image_path, x=x, y=y, w=w, h=h)
        self.set_y(y + h + 2)


def generate_report(record: dict, user_username: str) -> bytes:
    """生成诊断报告 PDF，返回字节流"""
    pdf = DiagnosisReport()
    pdf.add_page()

    storage = Path(current_app.config["STORAGE_DIR"])

    # ===== 封面标题 =====
    pdf.ln(8)
    pdf.set_font("cjk", "B", 22)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(0, 12, "皮肤镜图像辅助诊断报告", align="C")
    pdf.ln(14)

    # ===== 基本信息 =====
    pdf._section_title("基本信息")
    pdf._info_row("患者/用户", user_username)
    pdf._info_row("报告编号", f"RPT-{record.get('id', '')}")
    pdf._info_row("诊断日期", record.get("created_at", ""))
    pdf._info_row("报告生成", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    pdf.ln(4)

    # ===== 图像分析 =====
    pdf._section_title("图像分析")
    pdf.set_font("cjk", "", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "左: 原始皮肤镜像    右: AI 热力分析图（红色区域为模型关注的关键病灶区）")
    pdf.ln(8)

    # 原图 + 热力图并排
    img_left = pdf.get_x() + 5
    img_top = pdf.get_y()
    box_w = 88
    box_h = 80

    image_path = str(storage / record.get("image_path", "")) if record.get("image_path") else ""
    heatmap_path = str(storage / record.get("heatmap_path", "")) if record.get("heatmap_path") else ""

    pdf.set_xy(img_left, img_top)
    pdf.set_font("cjk", "", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(box_w, 5, "原始图像", align="C")
    pdf.set_xy(img_left, img_top + 5)
    pdf._embed_image_fit(image_path, box_w, box_h)

    pdf.set_xy(img_left + box_w + 10, img_top)
    pdf.set_font("cjk", "", 9)
    pdf.cell(box_w, 5, "Grad-CAM 热力图", align="C")
    pdf.set_xy(img_left + box_w + 10, img_top + 5)
    pdf._embed_image_fit(heatmap_path, box_w, box_h)

    pdf.set_y(img_top + box_h + 12)

    # ===== 诊断结果 =====
    pdf._section_title("AI 诊断结论")

    pdf.set_font("cjk", "B", 12)
    pdf.set_text_color(40, 40, 40)
    conf_pct = float(record.get("confidence", 0)) * 100
    pdf.cell(0, 8, f"主诊断: {record.get('predicted_label_zh', '')}（置信度 {conf_pct:.1f}%）")

    psoriasis_flag = record.get("is_psoriasis_related", False)
    pdf.ln(10)
    pdf.set_font("cjk", "", 10)
    pdf.set_text_color(100, 100, 100)
    if psoriasis_flag:
        pdf.cell(0, 6, "该病灶与银屑病/相关皮肤病存在关联，建议临床进一步确认。")
    else:
        pdf.cell(0, 6, "该病灶被识别为其他皮肤病变，建议结合临床综合判断。")
    pdf.ln(10)

    # ===== Top-3 预测 =====
    pdf._section_title("预测详情")
    predictions = record.get("predictions", [])
    if predictions:
        col_w = [12, 60, 68, 36]
        headers = ["#", "中文病名", "英文类别", "置信度"]
        pdf.set_font("cjk", "B", 9)
        pdf.set_fill_color(240, 245, 255)
        for i, (h, w) in enumerate(zip(headers, col_w)):
            pdf.cell(w, 8, h, border=1, fill=True, align="C" if i != 1 else "L")
        pdf.ln()

        pdf.set_font("cjk", "", 9)
        for idx, pred in enumerate(predictions):
            pdf.cell(col_w[0], 7, str(idx + 1), border=1, align="C")
            pdf.cell(col_w[1], 7, str(pred.get("label_zh", "")), border=1)
            pdf.cell(col_w[2], 7, str(pred.get("label_en", "")), border=1)
            pdf.cell(col_w[3], 7, f"{float(pred.get('confidence', 0)) * 100:.1f}%", border=1, align="C")
            pdf.ln()
    pdf.ln(6)

    # ===== 免责声明 =====
    pdf.set_fill_color(255, 245, 230)
    pdf.set_draw_color(230, 200, 150)
    y_before = pdf.get_y()
    pdf.rect(10, y_before, 190, 28, style="DF")

    pdf.set_xy(14, y_before + 3)
    pdf.set_font("cjk", "B", 9)
    pdf.set_text_color(180, 120, 50)
    pdf.cell(0, 5, "免责声明")
    pdf.set_xy(14, y_before + 10)
    pdf.set_font("cjk", "", 7.5)
    pdf.set_text_color(150, 130, 100)
    pdf.multi_cell(182, 4,
        "本报告由 AI 辅助诊断系统自动生成，仅供临床参考，不构成最终医疗诊断。"
        "所有诊断结论应由具备执业资质的皮肤科医师复核确认。"
        "系统开发者不对因使用本报告而产生的任何医疗决策承担责任。"
    )

    return pdf.output()


def generate_report_response(record: dict, username: str):
    """返回 Flask Response 可用的 PDF 字节和文件名"""
    pdf_bytes = generate_report(record, username)
    filename = f"诊断报告_{record.get('id', '')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    return pdf_bytes, filename
