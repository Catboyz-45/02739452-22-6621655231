"""สไตล์ร่วมของทุกหน้า: ฟอนต์ Sarabun, การ์ด KPI, ป้ายแหล่งข้อมูล"""
import streamlit as st

# สีกราฟ (ชุดสีที่ผ่านการตรวจสำหรับผู้ที่ตาบอดสี) — สีของ มก. ใช้เฉพาะส่วนหัว ไม่ใช้กับข้อมูล
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
YEAR_RAMP = {2567: "#86b6ef", 2568: "#3987e5", 2569: "#1c5cab"}  # ปีเก่า → ใหม่ = อ่อน → เข้ม
INK, INK_2, GRID = "#1d2420", "#5b625e", "#e6e8e4"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stText, button, input, textarea, select,
[data-testid="stSidebar"] *, [data-testid="stMetric"] * { font-family: 'Sarabun', sans-serif !important; }
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1280px; }
h1, h2, h3 { letter-spacing: -0.01em; }
.hero { background: linear-gradient(120deg, #00704a 0%, #0b8a5c 60%, #2f9e6f 100%); color: #fff;
        border-radius: 18px; padding: 22px 26px; margin-bottom: 14px; }
.hero h1 { color: #fff; font-size: 1.85rem; margin: 0 0 4px; font-weight: 700; }
.hero p { margin: 0; opacity: .95; font-size: 1.02rem; }
.chips { margin-top: 10px; display: flex; flex-wrap: wrap; gap: 6px; }
.chip { background: rgba(255,255,255,.18); border: 1px solid rgba(255,255,255,.35); color: #fff;
        padding: 2px 10px; border-radius: 999px; font-size: .82rem; }
.kpi { background: #fff; border: 1px solid #e6e8e4; border-radius: 14px; padding: 14px 16px; height: 100%;
       box-shadow: 0 1px 2px rgba(0,0,0,.04); }
.kpi .label { color: #5b625e; font-size: .88rem; }
.kpi .value { color: #1d2420; font-size: 1.75rem; font-weight: 700; line-height: 1.2; margin-top: 2px; }
.kpi.sm .value { font-size: 1.3rem; white-space: nowrap; }
.kpi .hint { color: #7a817c; font-size: .8rem; margin-top: 2px; }
.card { background: #fff; border: 1px solid #e6e8e4; border-radius: 14px; padding: 6px 16px 12px; margin-bottom: 12px; }
.howto { color: #5b625e; font-size: .88rem; margin: -6px 0 6px; }
.badge { display: inline-block; padding: 1px 9px; border-radius: 999px; font-size: .8rem; margin-right: 4px;
         background: #eef3ef; color: #1d2420; border: 1px solid #d5ded7; }
.level { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .85rem; font-weight: 600; }
[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #e6e8e4; }
[data-testid="stTabs"] button p { font-size: 1rem; font-weight: 600; }
</style>
"""


def apply():
    st.markdown(CSS, unsafe_allow_html=True)


def kpi(col, label, value, hint="", small=False):
    cls = "kpi sm" if small else "kpi"
    col.markdown(f'<div class="{cls}"><div class="label">{label}</div><div class="value">{value}</div>'
                 f'<div class="hint">{hint}</div></div>', unsafe_allow_html=True)
