import math
import re

import altair as alt
import pandas as pd
import streamlit as st

import style
from db import safe_query

st.set_page_config(page_title="ความนิยมคณะ มก.", page_icon="🌾", layout="wide")
style.apply()

# ---------------------------------------------------------------- ข้อมูล (อ่านจาก PostgreSQL โดยตรง)
stats, err = safe_query("SELECT * FROM admission_stats")
summary, _ = safe_query("SELECT * FROM program_summary")
last_run, _ = safe_query("SELECT finished_at FROM pipeline_runs WHERE status <> 'no_load' ORDER BY finished_at DESC LIMIT 1")
if err or stats.empty or summary.empty:
    st.info("ยังไม่มีข้อมูล รอให้ DAG `ku_faculty_popularity` ใน Airflow (http://localhost:8080) รันเสร็จก่อน แล้วรีเฟรชหน้านี้")
    st.stop()

for c in ["seats", "applicants", "enrolled", "min_score", "max_score", "academic_year"]:
    stats[c] = pd.to_numeric(stats[c], errors="coerce")
for c in ["enrolled_2567", "seats_2570", "applicants_2567"]:
    summary[c] = pd.to_numeric(summary[c], errors="coerce")

LEVELS = [("แข่งขันสูงมาก", 20, math.inf), ("แข่งขันสูง", 10, 20), ("ปานกลาง", 5, 10), ("ไม่สูง", 0, 5)]
LEVEL_NAMES = [n for n, _, _ in LEVELS]
LEVEL_COLORS = ["#0d366b", "#1c5cab", "#3987e5", "#86b6ef"]  # ramp สีน้ำเงินเดียว เข้ม = แข่งขันสูง


def level_of(ratio):
    if pd.isna(ratio):
        return None
    return next(n for n, lo, hi in LEVELS if lo <= ratio < hi)


def short_name(name: str) -> str:
    name = str(name or "")
    if "สาขาวิชา" in name:
        name = name.split("สาขาวิชา", 1)[1]
    name = re.sub(r"\(ภาษา.*?\)|\(.*?ปกติ\)", "", name).strip()
    return name if len(name) <= 42 else name[:40] + "…"


def short_fac(name: str) -> str:
    return re.sub(r"^คณะ", "", str(name or "")).strip()


tcas = stats[stats["source"] == "tcas"]
years = sorted(tcas["academic_year"].dropna().astype(int).unique(), reverse=True)
names = summary[["campus", "major_key", "faculty", "program_name", "enrolled_2567", "seats_2570", "sources"]]


@st.cache_data(ttl=30)
def year_frame(df_tcas: pd.DataFrame, df_names: pd.DataFrame, year: int) -> pd.DataFrame:
    t = df_tcas[df_tcas["academic_year"] == year].groupby(["campus", "major_key"], as_index=False).agg(
        applicants=("applicants", "sum"), seats=("seats", "sum"),
        min_score=("min_score", "min"), max_score=("max_score", "max"))
    df = t.merge(df_names, on=["campus", "major_key"], how="left")
    df["ratio"] = (df["applicants"] / df["seats"]).where(df["seats"] > 0)
    df["level"] = df["ratio"].map(level_of)
    df["name"] = df["program_name"].map(short_name)
    df["label"] = df["name"] + " · " + df["campus"]
    df["fac"] = df["faculty"].map(short_fac)
    return df


# ---------------------------------------------------------------- ตัวกรอง
FILTER_KEYS = ["f_year", "f_campus", "f_fac", "f_level", "f_score", "f_q"]
with st.sidebar:
    st.markdown("### 🔎 ตัวกรอง")
    if st.button("↺ ล้างตัวกรองทั้งหมด", use_container_width=True):
        for k in FILTER_KEYS:
            st.session_state.pop(k, None)
        st.rerun()
    year = st.radio("ปีการศึกษา (TCAS รอบ 3)", years, horizontal=True, key="f_year")
    base = year_frame(tcas, names, int(year))
    campus = st.multiselect("วิทยาเขต", sorted(base["campus"].dropna().unique()), key="f_campus",
                            placeholder="ทุกวิทยาเขต")
    fac_pool = base[base["campus"].isin(campus)] if campus else base
    faculty = st.multiselect("คณะ", sorted(fac_pool["faculty"].dropna().unique()), key="f_fac", placeholder="ทุกคณะ")
    level = st.multiselect("ระดับการแข่งขัน", LEVEL_NAMES, key="f_level", placeholder="ทุกระดับ",
                           help="ผู้สมัครต่อ 1 ที่นั่ง: สูงมาก ≥ 20 · สูง 10–20 · ปานกลาง 5–10 · ไม่สูง < 5")
    score = st.slider("คะแนนต่ำสุดที่ใช้เข้า (ช่วง)", 0, 100, (0, 100), key="f_score")
    q = st.text_input("ค้นหาชื่อหลักสูตร", key="f_q", placeholder="เช่น คอมพิวเตอร์ บัญชี สัตวแพทย์")
    st.caption("ตัวกรองทุกตัวมีผลกับทุกแท็บ")

view = base.copy()
if campus:
    view = view[view["campus"].isin(campus)]
if faculty:
    view = view[view["faculty"].isin(faculty)]
if level:
    view = view[view["level"].isin(level)]
if score != (0, 100):
    view = view[view["min_score"].between(*score)]
if q:
    view = view[view["program_name"].fillna("").str.contains(q.strip(), case=False)]

# ---------------------------------------------------------------- ส่วนหัว
updated = pd.to_datetime(last_run["finished_at"].iloc[0]).tz_convert("Asia/Bangkok").strftime("%d/%m/%Y %H:%M") \
    if not last_run.empty else "-"
st.markdown(f"""
<div class="hero">
  <h1>🌾 เรียนอะไรดีที่ ม.เกษตรศาสตร์?</h1>
  <p>ดูว่าหลักสูตรไหนคนสมัครเยอะ แข่งขันสูงแค่ไหน และต้องใช้คะแนนเท่าไร — ระดับปริญญาตรี ทุกวิทยาเขต</p>
  <div class="chips">
    <span class="chip">ทปอ. สถิติ TCAS รอบ 3 ปี 2567–2569</span>
    <span class="chip">สป.อว. นักศึกษาใหม่ 2567</span>
    <span class="chip">admission.ku.ac.th ที่นั่ง TCAS70</span>
    <span class="chip">อัปเดตล่าสุด {updated}</span>
  </div>
</div>""", unsafe_allow_html=True)

if view.empty:
    st.warning("ไม่พบหลักสูตรที่ตรงกับตัวกรอง ลองล้างตัวกรองบางตัวดูครับ")
    st.stop()

k1, k2, k3, k4 = st.columns(4)
ratio_all = view["applicants"].sum() / view["seats"].sum() if view["seats"].sum() else 0
style.kpi(k1, "หลักสูตรที่ตรงตัวกรอง", f"{len(view):,}", f"ปีการศึกษา {year} · รอบ 3 Admission")
style.kpi(k2, "ผู้สมัครทั้งหมด", f"{int(view['applicants'].sum()):,} คน", "นับรายการสมัครในรอบ 3")
style.kpi(k3, "ที่นั่งที่เปิดรับ", f"{int(view['seats'].sum()):,} ที่", "จำนวนรับในรอบ 3")
style.kpi(k4, "อัตราการแข่งขัน", f"1 : {ratio_all:.1f}", "1 ที่นั่ง มีคนสมัครกี่คน")
st.write("")


def themed(chart, height):
    return chart.properties(height=height).configure(font="Sarabun, sans-serif").configure_view(strokeWidth=0).configure_axis(
        labelColor=style.INK_2, titleColor=style.INK_2, gridColor=style.GRID, domain=False, tickColor=style.GRID,
        labelFontSize=12, titleFontSize=12, labelLimit=260,
    ).configure_legend(labelColor=style.INK, titleColor=style.INK_2, labelFontSize=12, orient="top")


def hbar(df, x, y, x_title, fmt, color=style.BLUE, tooltip=None, height=None):
    height = height or max(160, 30 * len(df))
    top_val = float(df[x].max() or 1)
    bars = alt.Chart(df).mark_bar(cornerRadiusEnd=4, size=18, color=color).encode(
        x=alt.X(f"{x}:Q", title=x_title, scale=alt.Scale(domain=[0, top_val * 1.15], nice=False)), y=alt.Y(f"{y}:N", sort="-x", title=None),
        tooltip=tooltip or [y, alt.Tooltip(f"{x}:Q", format=fmt)])
    text = bars.mark_text(align="left", dx=4, color=style.INK, fontSize=12).encode(
        text=alt.Text(f"{x}:Q", format=fmt))
    return themed(bars + text, height)


TIP = [alt.Tooltip("name:N", title="หลักสูตร"), alt.Tooltip("faculty:N", title="คณะ"),
       alt.Tooltip("campus:N", title="วิทยาเขต"), alt.Tooltip("applicants:Q", title="ผู้สมัคร", format=","),
       alt.Tooltip("seats:Q", title="ที่นั่ง", format=","), alt.Tooltip("ratio:Q", title="ผู้สมัคร/ที่นั่ง", format=".1f"),
       alt.Tooltip("min_score:Q", title="คะแนนต่ำสุด", format=".2f")]

tab1, tab2, tab3, tab4 = st.tabs(["📊 ภาพรวม", "🏛️ เปรียบเทียบคณะ", "🎯 หาหลักสูตรที่ใช่", "📋 ตารางข้อมูล"])

# ---------------------------------------------------------------- แท็บ 1: ภาพรวม
with tab1:
    left, right = st.columns([2, 1], gap="large")
    with left:
        st.markdown("#### อันดับหลักสูตร")
        rank_by = st.radio("จัดอันดับตาม", ["คนสมัครมากที่สุด", "แข่งขันสูงที่สุด", "คะแนนต่ำสุดสูงที่สุด",
                                          "แข่งขันน้อย (โอกาสติดสูง)"], horizontal=True, label_visibility="collapsed")
        top_n = st.slider("จำนวนอันดับ", 5, 20, 10, key="top_n")
        spec = {
            "คนสมัครมากที่สุด": ("applicants", False, "จำนวนผู้สมัคร (คน)", ","),
            "แข่งขันสูงที่สุด": ("ratio", False, "ผู้สมัครต่อ 1 ที่นั่ง", ".1f"),
            "คะแนนต่ำสุดสูงที่สุด": ("min_score", False, "คะแนนต่ำสุดที่ผ่านการคัดเลือก", ".2f"),
            "แข่งขันน้อย (โอกาสติดสูง)": ("ratio", True, "ผู้สมัครต่อ 1 ที่นั่ง", ".1f"),
        }[rank_by]
        col, asc, title, fmt = spec
        top = view.dropna(subset=[col]).sort_values(col, ascending=asc).head(top_n)
        if asc:
            top = top.assign(**{col: top[col]})
            chart = alt.Chart(top).mark_bar(cornerRadiusEnd=4, size=18, color=style.AQUA).encode(
                x=alt.X(f"{col}:Q", title=title, scale=alt.Scale(domain=[0, float(top[col].max() or 1) * 1.15], nice=False)),
                y=alt.Y("label:N", sort="x", title=None), tooltip=TIP)
            chart = themed(chart + chart.mark_text(align="left", dx=4, color=style.INK).encode(
                text=alt.Text(f"{col}:Q", format=fmt)), max(160, 30 * len(top)))
        else:
            chart = hbar(top, col, "label", title, fmt, tooltip=TIP)
        st.altair_chart(chart, use_container_width=True)
        st.markdown('<div class="howto">💡 วางเมาส์บนแท่งเพื่อดูรายละเอียด · "แข่งขันน้อย" คือหลักสูตรที่ผู้สมัครต่อที่นั่งน้อย '
                    'มีโอกาสติดสูงกว่า</div>', unsafe_allow_html=True)
    with right:
        st.markdown("#### ระดับการแข่งขัน")
        lv = view.dropna(subset=["level"]).groupby("level", as_index=False).size()
        lv["order"] = lv["level"].map(LEVEL_NAMES.index)
        donut = alt.Chart(lv).mark_arc(innerRadius=62, stroke="#fff", strokeWidth=2).encode(
            theta="size:Q",
            color=alt.Color("level:N", scale=alt.Scale(domain=LEVEL_NAMES, range=LEVEL_COLORS), legend=None),
            order="order:Q", tooltip=[alt.Tooltip("level:N", title="ระดับ"), alt.Tooltip("size:Q", title="หลักสูตร")])
        st.altair_chart(themed(donut, 230), use_container_width=True)
        for (name, lo, hi), color in zip(LEVELS, LEVEL_COLORS):
            n = int(lv.loc[lv["level"] == name, "size"].sum())
            rng = f"≥ {lo}" if hi == math.inf else f"{lo}–{hi}"
            st.markdown(f'<div style="display:flex;justify-content:space-between;align-items:center;margin:6px 0">'
                        f'<span><span class="level" style="background:{color};color:#fff">{name}</span> '
                        f'<span style="color:#5b625e;font-size:.85rem">{rng} คน/ที่นั่ง</span></span>'
                        f'<b>{n} หลักสูตร</b></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- แท็บ 2: เปรียบเทียบคณะ
with tab2:
    metric = st.radio("เปรียบเทียบด้วย", ["ผู้สมัคร", "ที่นั่ง", "อัตราการแข่งขัน", "คะแนนต่ำสุดเฉลี่ย"], horizontal=True)
    by_fac = view.groupby("fac", as_index=False).agg(applicants=("applicants", "sum"), seats=("seats", "sum"),
                                                      min_score=("min_score", "mean"), n=("label", "count"))
    by_fac["ratio"] = by_fac["applicants"] / by_fac["seats"]
    col, title, fmt = {"ผู้สมัคร": ("applicants", "ผู้สมัคร (คน)", ","), "ที่นั่ง": ("seats", "ที่นั่ง", ","),
                       "อัตราการแข่งขัน": ("ratio", "ผู้สมัครต่อ 1 ที่นั่ง", ".1f"),
                       "คะแนนต่ำสุดเฉลี่ย": ("min_score", "คะแนนต่ำสุดเฉลี่ย", ".1f")}[metric]
    show_all = st.toggle("แสดงทุกคณะ (ค่าเริ่มต้นแสดง 12 อันดับแรก)", value=False)
    fac_plot = by_fac.dropna(subset=[col]).sort_values(col, ascending=False)
    fac_plot = fac_plot if show_all else fac_plot.head(12)
    st.markdown(f"#### {metric} แยกตามคณะ (ปี {year})")
    st.altair_chart(hbar(fac_plot, col, "fac", title, fmt,
                         tooltip=[alt.Tooltip("fac:N", title="คณะ"), alt.Tooltip(f"{col}:Q", title=metric, format=fmt),
                                  alt.Tooltip("n:Q", title="จำนวนหลักสูตร")]), use_container_width=True)

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### แนวโน้มผู้สมัคร 3 ปี")
        keys = view[["campus", "major_key"]].drop_duplicates()
        hist = tcas.merge(keys, on=["campus", "major_key"]).merge(names[["campus", "major_key", "faculty"]],
                                                                    on=["campus", "major_key"], suffixes=("_x", ""))
        hist["fac"] = hist["faculty"].map(short_fac)
        trend = hist.groupby(["fac", "academic_year"], as_index=False)["applicants"].sum()
        default = trend.groupby("fac")["applicants"].sum().nlargest(3).index.tolist()
        picks = st.multiselect("เลือกคณะ (สูงสุด 5)", sorted(trend["fac"].unique()), default=default, max_selections=5)
        tr = trend[trend["fac"].isin(picks)]
        line = alt.Chart(tr).mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=70, filled=True)).encode(
            x=alt.X("academic_year:O", title="ปีการศึกษา", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("applicants:Q", title="ผู้สมัคร (คน)"),
            color=alt.Color("fac:N", scale=alt.Scale(domain=picks, range=style.SERIES[:len(picks)]), title=None),
            tooltip=[alt.Tooltip("fac:N", title="คณะ"), alt.Tooltip("academic_year:O", title="ปี"),
                     alt.Tooltip("applicants:Q", title="ผู้สมัคร", format=",")])
        st.altair_chart(themed(line, 300), use_container_width=True)
    with c2:
        st.markdown("#### สมัคร vs เข้าเรียนจริง (ปี 2567)")
        sub = view.dropna(subset=["enrolled_2567"])
        keys67 = sub[["campus", "major_key", "fac"]]
        app67 = tcas[tcas["academic_year"] == 2567].merge(keys67, on=["campus", "major_key"]) \
            .groupby("fac")["applicants"].sum().rename("ผู้สมัครรอบ 3 (ทปอ.)")
        enr67 = sub.groupby("fac")["enrolled_2567"].sum().rename("นักศึกษาใหม่ทุกรอบ (อว.)")
        comp = pd.concat([app67, enr67], axis=1).dropna().nlargest(8, "นักศึกษาใหม่ทุกรอบ (อว.)").reset_index() \
            .melt(id_vars="fac", var_name="ชุดข้อมูล", value_name="คน")
        series = ["ผู้สมัครรอบ 3 (ทปอ.)", "นักศึกษาใหม่ทุกรอบ (อว.)"]
        gb = alt.Chart(comp).mark_bar(cornerRadiusEnd=4, size=11).encode(
            y=alt.Y("fac:N", title=None, sort=alt.EncodingSortField("คน", op="max", order="descending")),
            yOffset=alt.YOffset("ชุดข้อมูล:N", sort=series),
            x=alt.X("คน:Q", title="คน"),
            color=alt.Color("ชุดข้อมูล:N", scale=alt.Scale(domain=series, range=[style.BLUE, style.ORANGE]), title=None),
            tooltip=["fac", "ชุดข้อมูล", alt.Tooltip("คน:Q", format=",")])
        st.altair_chart(themed(gb, 300), use_container_width=True)
        st.markdown('<div class="howto">💡 1 คนสมัครได้หลายหลักสูตร ยอดสมัครจึงสูงกว่ายอดที่เข้าเรียนจริงมาก</div>',
                    unsafe_allow_html=True)

# ---------------------------------------------------------------- แท็บ 3: หาหลักสูตรที่ใช่
with tab3:
    a, b = st.columns([1.1, 1], gap="large")
    with a:
        st.markdown("#### คะแนนของฉันพอเข้าหลักสูตรไหนได้บ้าง?")
        my = st.number_input("คะแนนรวมของฉัน (เต็ม 100)", 0.0, 100.0, 60.0, 0.5)
        fit = view.dropna(subset=["min_score"]).copy()
        fit = fit[fit["min_score"] <= my].sort_values("min_score", ascending=False)
        fit["เผื่อ"] = (my - fit["min_score"]).round(2)
        st.markdown(f"มี **{len(fit):,}** หลักสูตรที่คะแนนต่ำสุดปี {year} ไม่เกิน {my:g} คะแนน")
        st.dataframe(fit[["label", "min_score", "เผื่อ", "level"]].head(30).rename(columns={
            "label": "หลักสูตร · วิทยาเขต", "min_score": "คะแนนต่ำสุด", "level": "การแข่งขัน"}),
            hide_index=True, use_container_width=True, height=360,
            column_config={"คะแนนต่ำสุด": st.column_config.NumberColumn(format="%.2f"),
                           "เผื่อ": st.column_config.NumberColumn("คะแนนเผื่อ", format="+%.2f")})
        st.caption("⚠️ แต่ละหลักสูตรใช้วิชาและสัดส่วนคะแนนต่างกัน ใช้เป็นแนวทางเบื้องต้นเท่านั้น")
    with b:
        st.markdown("#### ดูรายละเอียดหลักสูตร")
        opts = view.sort_values("applicants", ascending=False)
        pick = st.selectbox("เลือกหลักสูตร (พิมพ์ค้นหาได้)", opts["label"].tolist())
        row = opts[opts["label"] == pick].iloc[0]
        srcs = "".join(f'<span class="badge">{s}</span>' for s in str(row["sources"] or "").split(",") if s)
        st.markdown(f"**{row['program_name']}**  \n{row['faculty']} · วิทยาเขต{row['campus']}  \nพบในแหล่งข้อมูล: {srcs}",
                    unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns(4)
        style.kpi(m1, "ผู้สมัคร", f"{int(row['applicants']):,}", f"ปี {year}", small=True)
        style.kpi(m2, "ที่นั่ง", f"{int(row['seats']):,}", "รอบ 3", small=True)
        style.kpi(m3, "แข่งขัน", f"1 : {row['ratio']:.1f}" if pd.notna(row["ratio"]) else "-", row["level"] or "", small=True)
        style.kpi(m4, "คะแนนต่ำสุด", f"{row['min_score']:.2f}" if pd.notna(row["min_score"]) else "-",
                  f"สูงสุด {row['max_score']:.2f}" if pd.notna(row["max_score"]) else "", small=True)
        hist1 = tcas[(tcas["campus"] == row["campus"]) & (tcas["major_key"] == row["major_key"])] \
            .groupby("academic_year", as_index=False).agg(applicants=("applicants", "sum"), min_score=("min_score", "min"))
        hist1["academic_year"] = hist1["academic_year"].astype(int)
        s1, s2 = st.columns(2)
        with s1:
            bars = alt.Chart(hist1).mark_bar(cornerRadiusEnd=4, size=26).encode(
                x=alt.X("academic_year:O", title="ปี", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("applicants:Q", title="ผู้สมัคร"),
                color=alt.Color("academic_year:O", scale=alt.Scale(domain=list(style.YEAR_RAMP),
                                                                   range=list(style.YEAR_RAMP.values())), legend=None),
                tooltip=[alt.Tooltip("academic_year:O", title="ปี"), alt.Tooltip("applicants:Q", title="ผู้สมัคร", format=",")])
            st.altair_chart(themed(bars, 200), use_container_width=True)
        with s2:
            ln = alt.Chart(hist1.dropna(subset=["min_score"])).mark_line(
                strokeWidth=2, color=style.ORANGE, point=alt.OverlayMarkDef(size=70, filled=True, color=style.ORANGE)).encode(
                x=alt.X("academic_year:O", title="ปี", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("min_score:Q", title="คะแนนต่ำสุด", scale=alt.Scale(zero=False)),
                tooltip=[alt.Tooltip("academic_year:O", title="ปี"), alt.Tooltip("min_score:Q", title="คะแนนต่ำสุด", format=".2f")])
            st.altair_chart(themed(ln, 200), use_container_width=True)
        seats70 = stats[(stats["source"] == "kuadm") & (stats["campus"] == row["campus"])
                        & (stats["major_key"] == row["major_key"])].groupby("project", as_index=False)["seats"].sum()
        if not seats70.empty:
            st.markdown(f"**ที่นั่ง TCAS70 ที่ประกาศแล้ว** (admission.ku.ac.th) รวม {int(seats70['seats'].sum()):,} ที่")
            st.dataframe(seats70.rename(columns={"project": "โครงการ", "seats": "ที่นั่ง"}), hide_index=True,
                         use_container_width=True)

# ---------------------------------------------------------------- แท็บ 4: ตาราง
with tab4:
    table = view.sort_values("applicants", ascending=False)[
        ["name", "faculty", "campus", "applicants", "seats", "ratio", "level", "min_score", "max_score",
         "enrolled_2567", "seats_2570", "sources"]].rename(columns={
            "name": "หลักสูตร", "faculty": "คณะ", "campus": "วิทยาเขต", "applicants": "ผู้สมัคร", "seats": "ที่นั่ง",
            "ratio": "ผู้สมัคร/ที่นั่ง", "level": "ระดับ", "min_score": "คะแนนต่ำสุด", "max_score": "คะแนนสูงสุด",
            "enrolled_2567": "เข้าใหม่ 2567", "seats_2570": "ที่นั่ง TCAS70", "sources": "แหล่งข้อมูล"})
    st.dataframe(table, hide_index=True, use_container_width=True, height=520, column_config={
        "ผู้สมัคร/ที่นั่ง": st.column_config.ProgressColumn(format="%.1f", min_value=0,
                                                          max_value=float(table["ผู้สมัคร/ที่นั่ง"].max() or 1)),
        "คะแนนต่ำสุด": st.column_config.NumberColumn(format="%.2f"),
        "คะแนนสูงสุด": st.column_config.NumberColumn(format="%.2f"),
    })
    st.download_button("⬇️ ดาวน์โหลดตารางนี้ (CSV)", table.to_csv(index=False).encode("utf-8-sig"),
                       f"ku_programs_{year}.csv")

with st.expander("📖 คำอธิบายคำศัพท์และที่มาของข้อมูล"):
    st.markdown("""
- **ผู้สมัคร / ที่นั่ง** — สถิติ TCAS รอบ 3 (Admission) จาก ทปอ. นับรายการสมัคร (1 คนเลือกได้หลายอันดับ)
- **อัตราการแข่งขัน** — ผู้สมัครหารด้วยที่นั่ง เช่น 1 : 20 แปลว่า 1 ที่นั่งมีคนสมัคร 20 คน
- **คะแนนต่ำสุด / สูงสุด** — คะแนนของผู้ผ่านการคัดเลือกในรอบ 3 (เต็ม 100) แต่ละหลักสูตรใช้วิชาต่างกัน
- **เข้าใหม่ 2567** — นักศึกษาใหม่ทุกรอบจากข้อมูลเปิดของ สป.อว.
- **ที่นั่ง TCAS70** — จำนวนรับที่ประกาศบน admission.ku.ac.th (รวมทุกโครงการที่ประกาศแล้ว)
- หลักสูตรเดียวกันจากหลายแหล่งถูกรวมเป็นแถวเดียว (จับคู่ด้วยวิทยาเขต + ชื่อสาขา)
""")
