"""สไตล์ร่วมของทุกหน้า: ฟอนต์ Sarabun, การ์ด KPI, ป้ายแหล่งข้อมูล"""
import streamlit as st

# สีกราฟ (ชุดสีที่ผ่านการตรวจสำหรับผู้ที่ตาบอดสี) — สีของ มก. ใช้เฉพาะส่วนหัว ไม่ใช้กับข้อมูล
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
YEAR_RAMP = {2567: "#86b6ef", 2568: "#3987e5", 2569: "#1c5cab"}  # ปีเก่า → ใหม่ = อ่อน → เข้ม
INK, INK_2, GRID = "#1c2420", "#5d665f", "#e3e6df"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stText, button, input, textarea, select, label,
[data-testid="stSidebar"] *, [data-testid="stWidgetLabel"] * { font-family: 'IBM Plex Sans Thai', sans-serif !important; }
.block-container { padding-top: 0.6rem; padding-bottom: 3rem; max-width: 1240px; }
[data-testid="stHeader"] { background: transparent; }
h1, h2, h3, h4 { letter-spacing: -0.01em; font-weight: 700 !important; }
.topbar { background: #fff; border: 1px solid #e3e6df; border-radius: 16px; padding: 14px 18px; margin-bottom: 14px;
          display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; }
.brand { display: flex; align-items: center; gap: 12px; }
.logo { width: 40px; height: 40px; border-radius: 10px; background: #00704a; display: flex; align-items: center; justify-content: center; }
.brand .t { font-size: 1.15rem; font-weight: 700; line-height: 1.2; color: #1c2420; }
.brand .s { font-size: .82rem; color: #5d665f; }
.src { font-size: .78rem; color: #5d665f; text-align: right; line-height: 1.5; }
.kpi { background: #fff; border: 1px solid #e3e6df; border-radius: 16px; padding: 16px 18px; height: 100%; }
.kpi .label { color: #5d665f; font-size: .85rem; }
.kpi .value { color: #1c2420; font-size: 2rem; font-weight: 700; line-height: 1.15; margin-top: 4px; letter-spacing: -0.01em; }
.kpi.sm .value { font-size: 1.3rem; white-space: nowrap; }
.kpi .hint { color: #6b736d; font-size: .78rem; margin-top: 4px; }
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) { background: #fff; border-radius: 16px !important; border-color: #e3e6df !important; }
.rank { display: grid; grid-template-columns: 26px minmax(0, 300px) minmax(0, 1fr) 70px; align-items: center; gap: 10px; margin: 7px 0; }
.rank .n { font-size: .82rem; color: #6b736d; text-align: right; }
.rank .nm { font-size: .9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #1c2420; }
.rank .nm small { color: #6b736d; font-size: .75rem; }
.rank .track { background: #eef1ec; border-radius: 6px; height: 14px; }
.rank .bar { height: 14px; border-radius: 0 6px 6px 0; }
.rank .v { font-size: .9rem; font-weight: 600; text-align: right; color: #1c2420; }
.stack { display: flex; height: 18px; border-radius: 6px; overflow: hidden; gap: 2px; margin: 4px 0 12px; }
.lvl { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin: 9px 0; }
.lvl .sw { width: 12px; height: 12px; border-radius: 3px; display: inline-block; margin-right: 10px; }
.lvl .nm { font-weight: 600; font-size: .9rem; } .lvl .r { font-size: .76rem; color: #6b736d; }
.note { background: #f5f6f2; border-radius: 12px; padding: 10px 14px; font-size: .82rem; color: #4a524c; line-height: 1.55; margin-top: 8px; }
.howto { color: #5d665f; font-size: .85rem; margin: 2px 0 6px; }
.badge { display: inline-block; padding: 1px 9px; border-radius: 999px; font-size: .78rem; margin-right: 4px;
         background: #eef1ec; color: #1c2420; border: 1px solid #d7dcd4; }
.level { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .85rem; font-weight: 600; }
[data-testid="stTabs"] [role="tablist"] { background: #eef1ec; padding: 4px; border-radius: 12px; gap: 4px; }
[data-testid="stTabs"] button[role="tab"] { border-radius: 9px; padding: 6px 16px; }
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] { background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.08); }
[data-testid="stTabs"] button[role="tab"] p { font-size: .95rem; font-weight: 600; }
[data-testid="stTabs"] [data-baseweb="tab-highlight"], [data-testid="stTabs"] [data-baseweb="tab-border"] { display: none; }
</style>
"""

LOGO = ('<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22V9"></path>'
        '<path d="M12 13c-3 0-5-2-5-5 3 0 5 2 5 5z"></path><path d="M12 13c3 0 5-2 5-5-3 0-5 2-5 5z"></path>'
        '<path d="M12 9c-2 0-3-2-3-4 2 0 3 2 3 4z"></path><path d="M12 9c2 0 3-2 3-4-2 0-3 2-3 4z"></path></svg>')


def topbar(title, subtitle, right=""):
    st.markdown(f'<div class="topbar"><div class="brand"><div class="logo">{LOGO}</div><div>'
                f'<div class="t">{title}</div><div class="s">{subtitle}</div></div></div>'
                f'<div class="src">{right}</div></div>', unsafe_allow_html=True)



def apply():
    st.markdown(CSS, unsafe_allow_html=True)


def kpi(col, label, value, hint="", small=False):
    cls = "kpi sm" if small else "kpi"
    col.markdown(f'<div class="{cls}"><div class="label">{label}</div><div class="value">{value}</div>'
                 f'<div class="hint">{hint}</div></div>', unsafe_allow_html=True)
