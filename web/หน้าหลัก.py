import math
import re

import altair as alt
import pandas as pd
import streamlit as st

import style
from db import safe_query

st.set_page_config(page_title="ความนิยมคณะ มก.", page_icon="🌾", layout="wide", initial_sidebar_state="collapsed")
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


# ---------------------------------------------------------------- ส่วนหัว + เมนู + ตัวกรอง (ตามดีไซน์)
if "nav_target" in st.session_state:
    st.session_state["nav_main"] = st.session_state.pop("nav_target")
st.session_state.setdefault("nav_main", "ภาพรวม")
page = style.header("nav_main")
if page == "สถานะ Pipeline":
    st.switch_page("pages/1_สถานะ_Pipeline.py")

ALL_CAMPUS, ALL_FAC, ALL_LEVEL = "ทุกวิทยาเขต", "ทุกคณะ", "ทุกระดับ"
DEFAULTS = {"f_year": years[0], "f_campus": ALL_CAMPUS, "f_fac": ALL_FAC, "f_level": ALL_LEVEL, "f_q": ""}
for _k, _v in DEFAULTS.items():
    st.session_state.setdefault(_k, _v)


def reset_filters():
    # ตั้งค่ากลับเป็นค่าเริ่มต้นตรง ๆ (ถ้าแค่ลบ key ช่องค้นหาจะยังจำข้อความเดิมไว้)
    st.session_state.update(DEFAULTS)


updated = pd.to_datetime(last_run["finished_at"].iloc[0]).tz_convert("Asia/Bangkok").strftime("%d/%m/%Y %H:%M") \
    if not last_run.empty else "-"

with st.container(border=True, key="filters"):
    f1, f2, f3, f4, f5, f6 = st.columns([1.45, 1.2, 1.25, 1.05, 1.65, 0.85], vertical_alignment="bottom")
    year = f1.radio("ปีการศึกษา", years, horizontal=True, key="f_year")
    base = year_frame(tcas, names, int(year))
    campus = f2.selectbox("วิทยาเขต", [ALL_CAMPUS] + sorted(base["campus"].dropna().unique()), key="f_campus")
    fac_pool = base if campus == ALL_CAMPUS else base[base["campus"] == campus]
    fac_opts = [ALL_FAC] + sorted(fac_pool["faculty"].dropna().unique())
    if st.session_state.get("f_fac") not in fac_opts:
        st.session_state["f_fac"] = ALL_FAC
    faculty = f3.selectbox("คณะ", fac_opts, key="f_fac")
    level = f4.selectbox("ระดับการแข่งขัน", [ALL_LEVEL] + LEVEL_NAMES, key="f_level")
    q = f5.text_input("ค้นหาหลักสูตร", key="f_q", placeholder="เช่น คอมพิวเตอร์ บัญชี สัตวแพทย์")
    f6.button("ล้างตัวกรอง", on_click=reset_filters, use_container_width=True, key="clear")

view = base.copy()
if campus != ALL_CAMPUS:
    view = view[view["campus"] == campus]
if faculty != ALL_FAC:
    view = view[view["faculty"] == faculty]
if level != ALL_LEVEL:
    view = view[view["level"] == level]
if q:
    view = view[view["program_name"].fillna("").str.contains(q.strip(), case=False)]

if view.empty:
    st.warning("ไม่พบหลักสูตรที่ตรงกับตัวกรอง ลองกด \"ล้างตัวกรอง\" ดูครับ")
    st.stop()

k1, k2, k3, k4 = st.columns(4)
ratio_all = view["applicants"].sum() / view["seats"].sum() if view["seats"].sum() else 0
style.kpi(k1, "หลักสูตรที่ตรงตัวกรอง", f"{len(view):,}", f"ปีการศึกษา {year} · รอบ 3 Admission")
style.kpi(k2, "ผู้สมัครทั้งหมด", f"{int(view['applicants'].sum()):,}", "รายการสมัครในรอบ 3")
style.kpi(k3, "ที่นั่งที่เปิดรับ", f"{int(view['seats'].sum()):,}", "จำนวนรับในรอบ 3")
style.kpi(k4, "อัตราการแข่งขัน", f"1 : {ratio_all:.1f}", "1 ที่นั่ง มีคนสมัครกี่คน")
st.write("")


def themed(chart, height):
    return chart.properties(height=height).configure(font="IBM Plex Sans Thai, sans-serif", background="#ffffff").configure_view(strokeWidth=0).configure_axis(
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



# ---------------------------------------------------------------- แท็บ 1: ภาพรวม
if page == "ภาพรวม":
    left, right = st.columns([2, 1], gap="medium")
    with left, st.container(border=True):
        hc1, hc2 = st.columns([0.85, 1.3], vertical_alignment="center")
        rank_by = hc2.radio("จัดอันดับตาม", ["คนสมัครมาก", "แข่งขันสูง", "คะแนนสูง", "โอกาสติดสูง"], horizontal=True,
                            label_visibility="collapsed", key="rank_by")
        col, asc, unit, fmt, color = {
            "คนสมัครมาก": ("applicants", False, "คนสมัคร", "{:,.0f}", style.BLUE),
            "แข่งขันสูง": ("ratio", False, "ผู้สมัครต่อ 1 ที่นั่ง", "1 : {:.1f}", style.BLUE),
            "คะแนนสูง": ("min_score", False, "คะแนนต่ำสุด", "{:.2f}", style.BLUE),
            "โอกาสติดสูง": ("ratio", True, "ผู้สมัครต่อ 1 ที่นั่ง (น้อย = ติดง่าย)", "1 : {:.1f}", style.AQUA),
        }[rank_by]
        top_n = 10
        top = view.dropna(subset=[col]).sort_values(col, ascending=asc).head(top_n)
        hc1.markdown(f"#### {len(top)} อันดับหลักสูตร" + {"คนสมัครมาก": "ที่คนสมัครมากที่สุด", "แข่งขันสูง": "ที่แข่งขันสูงที่สุด",
                     "คะแนนสูง": "ที่ใช้คะแนนสูงที่สุด", "โอกาสติดสูง": "ที่มีโอกาสติดสูงที่สุด"}[rank_by])
        mx = float(top[col].max() or 1)
        rows = "".join(
            f'<div class="rank" title="{r.program_name} · {r.faculty} · ผู้สมัคร {r.applicants:,.0f} · ที่นั่ง {r.seats:,.0f}">'
            f'<span class="n">{i}</span><span class="nm">{r["name"]} <small>· {r.campus}</small></span>'
            f'<div class="track"><div class="bar" style="width:{max(2, r[col] / mx * 100):.1f}%;background:{color}"></div></div>'
            f'<span class="v">{fmt.format(r[col])}</span></div>'
            for i, (_, r) in enumerate(top.iterrows(), start=1))
        st.markdown(rows, unsafe_allow_html=True)

    with right, st.container(border=True):
        st.markdown("#### ระดับการแข่งขัน")
        lv = view.dropna(subset=["level"]).groupby("level")["label"].count()
        total = int(lv.sum()) or 1
        st.markdown(f'<div class="howto">{total} หลักสูตร แบ่งตามจำนวนผู้สมัครต่อ 1 ที่นั่ง</div>', unsafe_allow_html=True)
        segs = "".join(f'<div style="width:{lv.get(n, 0) / total * 100:.1f}%;background:{c}"></div>'
                       for n, c in zip(LEVEL_NAMES, LEVEL_COLORS) if lv.get(n, 0))
        items = "".join(
            f'<div class="lvl"><div style="display:flex;align-items:center"><span class="sw" style="background:{c}"></span>'
            f'<div><div class="nm">{n}</div><div class="r">{("≥ " + str(lo)) if hi == math.inf else (f"{lo}–{hi}" if lo else "น้อยกว่า " + str(hi))} คน ต่อ 1 ที่นั่ง</div></div></div>'
            f'<b>{int(lv.get(n, 0))} หลักสูตร</b></div>'
            for (n, lo, hi), c in zip(LEVELS, LEVEL_COLORS))
        st.markdown(f'<div class="stack">{segs}</div>{items}'
                    '<div class="note">อ่านค่า: 1 : 20 แปลว่า 1 ที่นั่งมีคนสมัคร 20 คน ยิ่งตัวเลขมาก ยิ่งแข่งขันสูง</div>',
                    unsafe_allow_html=True)

    with st.container(border=True):
        fa, fb = st.columns([1, 1.6], gap="large")
        with fa:
            st.markdown("#### คะแนนของฉันพอเข้าที่ไหนได้บ้าง?")
            my0 = st.number_input("คะแนนรวมของฉัน (เต็ม 100)", 0.0, 100.0, 60.0, 0.5, key="my_score")
            fit0 = view.dropna(subset=["min_score"])
            fit0 = fit0[fit0["min_score"] <= my0].sort_values("min_score", ascending=False)
            st.markdown(f"มี **{len(fit0):,}** หลักสูตรที่คะแนนต่ำสุดปี {year} ไม่เกิน {my0:g} คะแนน")
            st.markdown('<div class="howto">แต่ละหลักสูตรใช้วิชาและสัดส่วนคะแนนต่างกัน ใช้เป็นแนวทางเบื้องต้นเท่านั้น</div>',
                        unsafe_allow_html=True)
        with fb:
            show0 = pd.DataFrame({"หลักสูตร": fit0["name"], "วิทยาเขต": fit0["campus"],
                                  "คะแนนต่ำสุด": fit0["min_score"].map("{:.2f}".format),
                                  "เผื่อ": (my0 - fit0["min_score"]).map("+{:.2f}".format)}).head(6)
            st.markdown(style.table(show0, num=("คะแนนต่ำสุด", "เผื่อ"), muted=("วิทยาเขต",), pos=("เผื่อ",),
                                    bold=("คะแนนต่ำสุด",)), unsafe_allow_html=True)

# ---------------------------------------------------------------- แท็บ 2: เปรียบเทียบคณะ
if page == "เปรียบเทียบคณะ":
    with st.container(border=True):
        metric = st.radio("เปรียบเทียบด้วย", ["ผู้สมัคร", "ที่นั่ง", "อัตราการแข่งขัน", "คะแนนต่ำสุดเฉลี่ย"],
                          horizontal=True, key="m_fac")
        by_fac = view.groupby("fac", as_index=False).agg(applicants=("applicants", "sum"), seats=("seats", "sum"),
                                                          min_score=("min_score", "mean"), n=("label", "count"))
        by_fac["ratio"] = by_fac["applicants"] / by_fac["seats"]
        col, fmt = {"ผู้สมัคร": ("applicants", "{:,.0f}"), "ที่นั่ง": ("seats", "{:,.0f}"),
                    "อัตราการแข่งขัน": ("ratio", "1 : {:.1f}"), "คะแนนต่ำสุดเฉลี่ย": ("min_score", "{:.1f}")}[metric]
        show_all = st.toggle("แสดงทุกคณะ", value=False, key="fac_all")
        fp = by_fac.dropna(subset=[col]).sort_values(col, ascending=False)
        fp = fp if show_all else fp.head(12)
        style.title(f"{metric} แยกตามคณะ — ปี {year}",
                    f"{len(by_fac)} คณะ" + ("" if show_all else " · แสดง 12 อันดับแรก"))
        mx = float(fp[col].max() or 1)
        st.markdown(style.bar_rows([{
            "n": i, "name": r["fac"], "sub": f"· {int(r['n'])} หลักสูตร", "value": fmt.format(r[col]),
            "pct": r[col] / mx * 100, "title": f"ผู้สมัคร {r['applicants']:,.0f} · ที่นั่ง {r['seats']:,.0f}"}
            for i, (_, r) in enumerate(fp.iterrows(), start=1)]), unsafe_allow_html=True)

    c1, c2 = st.columns(2, gap="medium")
    with c1, st.container(border=True):
        style.title("แนวโน้มผู้สมัคร 3 ปี", "เลือกได้สูงสุด 5 คณะ")
        keys = view[["campus", "major_key"]].drop_duplicates()
        hist = tcas.merge(keys, on=["campus", "major_key"]).merge(names[["campus", "major_key", "faculty"]],
                                                                    on=["campus", "major_key"], suffixes=("_x", ""))
        hist["fac"] = hist["faculty"].map(short_fac)
        trend = hist.groupby(["fac", "academic_year"], as_index=False)["applicants"].sum()
        trend["academic_year"] = trend["academic_year"].astype(int)
        default = trend.groupby("fac")["applicants"].sum().nlargest(3).index.tolist()
        picks = st.multiselect("คณะ", sorted(trend["fac"].unique()), default=default, max_selections=5,
                               label_visibility="collapsed")
        tr = trend[trend["fac"].isin(picks)]
        line = alt.Chart(tr).mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=70, filled=True)).encode(
            x=alt.X("academic_year:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("applicants:Q", title=None),
            color=alt.Color("fac:N", scale=alt.Scale(domain=picks, range=style.SERIES[:len(picks)]), title=None),
            tooltip=[alt.Tooltip("fac:N", title="คณะ"), alt.Tooltip("academic_year:O", title="ปี"),
                     alt.Tooltip("applicants:Q", title="ผู้สมัคร", format=",")])
        st.altair_chart(themed(line, 290), use_container_width=True)
    with c2, st.container(border=True):
        style.title("สมัคร vs เข้าเรียนจริง — ปี 2567", "8 คณะที่มีนักศึกษาใหม่มากที่สุด")
        sub = view.dropna(subset=["enrolled_2567"])
        app67 = tcas[tcas["academic_year"] == 2567].merge(sub[["campus", "major_key", "fac"]], on=["campus", "major_key"]) \
            .groupby("fac")["applicants"].sum()
        enr67 = sub.groupby("fac")["enrolled_2567"].sum()
        comp = pd.concat([app67.rename("app"), enr67.rename("enr")], axis=1).dropna().nlargest(8, "enr")
        mx2 = float(comp["app"].max() or 1)
        html = (f'<div class="legend"><span><i style="background:{style.BLUE}"></i>ผู้สมัครรอบ 3 (ทปอ.)</span>'
                f'<span><i style="background:{style.ORANGE}"></i>นักศึกษาใหม่ทุกรอบ (อว.)</span></div>')
        for fac, r in comp.iterrows():
            html += (f'<div class="pair"><span class="nm">{style.esc(fac)}</span><div>'
                     f'<div class="row"><div class="track" style="background:#eef1ec;border-radius:6px;height:10px">'
                     f'<div style="height:10px;border-radius:0 6px 6px 0;background:{style.BLUE};width:{r.app / mx2 * 100:.1f}%"></div></div>'
                     f'<span class="v">{r.app:,.0f}</span></div>'
                     f'<div class="row"><div class="track" style="background:#eef1ec;border-radius:6px;height:10px">'
                     f'<div style="height:10px;border-radius:0 6px 6px 0;background:{style.ORANGE};width:{max(1, r.enr / mx2 * 100):.1f}%"></div></div>'
                     f'<span class="v">{r.enr:,.0f}</span></div></div></div>')
        st.markdown(html + '<div class="note">1 คนสมัครได้หลายหลักสูตร ยอดสมัครจึงสูงกว่ายอดเข้าเรียนจริงมาก</div>',
                    unsafe_allow_html=True)

# ---------------------------------------------------------------- แท็บ 3: หาหลักสูตรที่ใช่
if page == "หาหลักสูตรที่ใช่":
    with st.container(border=True):
        a, b = st.columns([1, 1.7], gap="large")
        with a:
            st.markdown("#### คะแนนของฉันพอเข้าที่ไหนได้บ้าง?")
            my = st.number_input("คะแนนรวมของฉัน (เต็ม 100)", 0.0, 100.0, 60.0, 0.5)
            fit = view.dropna(subset=["min_score"]).copy()
            fit = fit[fit["min_score"] <= my].sort_values("min_score", ascending=False)
            st.markdown(f"มี **{len(fit):,}** หลักสูตรที่คะแนนต่ำสุดปี {year} ไม่เกิน {my:g} คะแนน")
            st.markdown('<div class="howto">แต่ละหลักสูตรใช้วิชาและสัดส่วนคะแนนต่างกัน ใช้เป็นแนวทางเบื้องต้นเท่านั้น</div>',
                        unsafe_allow_html=True)
        with b:
            show = pd.DataFrame({
                "หลักสูตร": fit["name"], "วิทยาเขต": fit["campus"],
                "คะแนนต่ำสุด": fit["min_score"].map("{:.2f}".format),
                "เผื่อ": (my - fit["min_score"]).map("+{:.2f}".format),
                "การแข่งขัน": fit["level"].fillna("-")}).head(30)
            st.markdown(style.table(show, num=("คะแนนต่ำสุด", "เผื่อ"), muted=("วิทยาเขต", "การแข่งขัน"),
                                    pos=("เผื่อ",), bold=("คะแนนต่ำสุด",)), unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("#### รายละเอียดรายหลักสูตร")
        opts = view.sort_values("applicants", ascending=False)
        pick = st.selectbox("เลือกหลักสูตร (พิมพ์ค้นหาได้)", opts["label"].tolist())
        row = opts[opts["label"] == pick].iloc[0]
        srcs = "".join(f'<span class="badge">{x}</span>' for x in str(row["sources"] or "").split(",") if x)
        st.markdown(f'<div style="margin:2px 0 10px"><b>{style.esc(row["program_name"])}</b><br>'
                    f'<span style="color:#5d665f;font-size:.88rem">{style.esc(row["faculty"])} · วิทยาเขต{row["campus"]}</span>'
                    f'<br><span style="font-size:.82rem;color:#5d665f">พบในแหล่งข้อมูล:</span> {srcs}</div>',
                    unsafe_allow_html=True)
        m1, m2, m3, m4, m5 = st.columns(5)
        style.kpi(m1, "ผู้สมัคร", f"{int(row['applicants']):,}", f"ปี {year}", small=True)
        style.kpi(m2, "ที่นั่งรอบ 3", f"{int(row['seats']):,}", "จำนวนรับ", small=True)
        style.kpi(m3, "การแข่งขัน", f"1 : {row['ratio']:.1f}" if pd.notna(row["ratio"]) else "-", row["level"] or "", small=True)
        style.kpi(m4, "คะแนนต่ำสุด", f"{row['min_score']:.2f}" if pd.notna(row["min_score"]) else "-",
                  f"สูงสุด {row['max_score']:.2f}" if pd.notna(row["max_score"]) else "", small=True)
        style.kpi(m5, "เข้าใหม่ 2567", f"{int(row['enrolled_2567']):,}" if pd.notna(row["enrolled_2567"]) else "-",
                  "ข้อมูล อว.", small=True)
        hist1 = tcas[(tcas["campus"] == row["campus"]) & (tcas["major_key"] == row["major_key"])] \
            .groupby("academic_year", as_index=False).agg(applicants=("applicants", "sum"), min_score=("min_score", "min"))
        hist1["academic_year"] = hist1["academic_year"].astype(int)
        st.write("")
        y1, y2, y3 = st.columns(3, gap="large")
        with y1:
            st.markdown("**ผู้สมัครย้อนหลัง**")
            amx = float(hist1["applicants"].max() or 1)
            st.markdown("".join(
                f'<div class="yr"><span>{r.academic_year}</span><div class="track" style="background:#eef1ec;border-radius:6px;height:14px">'
                f'<div style="height:14px;border-radius:0 6px 6px 0;width:{r.applicants / amx * 100:.1f}%;'
                f'background:{style.YEAR_RAMP.get(r.academic_year, style.BLUE)}"></div></div>'
                f'<span class="v" style="text-align:right;font-weight:600">{r.applicants:,.0f}</span></div>'
                for r in hist1.itertuples()), unsafe_allow_html=True)
        with y2:
            st.markdown("**คะแนนต่ำสุดย้อนหลัง**")
            st.markdown("".join(
                f'<div class="yr"><span>{r.academic_year}</span><div class="track" style="background:#eef1ec;border-radius:6px;height:14px">'
                f'<div style="height:14px;border-radius:0 6px 6px 0;width:{(r.min_score or 0):.1f}%;background:{style.ORANGE}"></div></div>'
                f'<span class="v" style="text-align:right;font-weight:600">{r.min_score:.2f}</span></div>'
                for r in hist1.dropna(subset=["min_score"]).itertuples()), unsafe_allow_html=True)
        with y3:
            st.markdown("**ที่นั่ง TCAS70 ที่ประกาศแล้ว**")
            seats70 = stats[(stats["source"] == "kuadm") & (stats["campus"] == row["campus"])
                            & (stats["major_key"] == row["major_key"])].groupby("project", as_index=False)["seats"].sum()
            if seats70.empty:
                st.markdown('<div class="howto">ยังไม่พบประกาศบน admission.ku.ac.th</div>', unsafe_allow_html=True)
            else:
                seats70["project"] = seats70["project"].str.replace("โครงการ ", "", regex=False)
                seats70["seats"] = seats70["seats"].fillna(0).astype(int).map("{:,}".format)
                st.markdown(style.table(seats70.rename(columns={"project": "โครงการ", "seats": "ที่นั่ง"}),
                                        num=("ที่นั่ง",), bold=("ที่นั่ง",)), unsafe_allow_html=True)

# ---------------------------------------------------------------- แท็บ 4: ตาราง
if page == "ตารางข้อมูล":
  with st.container(border=True):
    style.title("ตารางหลักสูตรทั้งหมด", f"{len(view):,} หลักสูตรตามตัวกรอง · ปี {year} · คลิกหัวคอลัมน์เพื่อเรียงลำดับ")
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
    st.download_button("ดาวน์โหลดตารางนี้ (CSV)", table.to_csv(index=False).encode("utf-8-sig"), f"ku_programs_{year}.csv")

st.markdown(f'<footer class="foot"><span>ที่มา: ทปอ. สถิติ TCAS รอบ 3 ปี 2567–2569 · สป.อว. นักศึกษาใหม่ 2567 · '
            f'admission.ku.ac.th ที่นั่ง TCAS70</span><span>อัปเดตล่าสุด {updated}</span></footer>', unsafe_allow_html=True)
