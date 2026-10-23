import altair as alt
import pandas as pd
import streamlit as st

from db import safe_query

st.set_page_config(page_title="ความนิยมคณะ มก.", page_icon="🌾", layout="wide")
st.title("ความนิยมและคะแนนเข้าคณะ ป.ตรี ม.เกษตรศาสตร์")
st.caption("ข้อมูลจาก ทปอ. (สถิติ TCAS รอบ 3 ปี 67–69) · สป.อว. (นักศึกษาเข้าใหม่ 2567) · admission.ku.ac.th (จำนวนรับ TCAS70) "
           "— รวมด้วย Apache Airflow และอ่านจาก PostgreSQL โดยตรง")

summary, err = safe_query("SELECT * FROM program_summary")
stats, _ = safe_query("SELECT * FROM admission_stats")
if err or summary.empty:
    st.info("ยังไม่มีข้อมูล รอให้ DAG `ku_faculty_popularity` ใน Airflow (http://localhost:8080) รันเสร็จก่อน แล้วรีเฟรชหน้านี้")
    if err:
        st.caption(f"รายละเอียด: {err[:200]}")
    st.stop()

num_cols = ["applicants", "seats_r3", "competition_ratio", "min_score", "max_score",
            "applicants_2567", "enrolled_2567", "seats_2570", "n_sources"]
summary[num_cols] = summary[num_cols].apply(pd.to_numeric, errors="coerce")
for c in ["seats", "applicants", "enrolled", "min_score", "max_score"]:
    stats[c] = pd.to_numeric(stats[c], errors="coerce")

# ---------------------------------------------------------------- ตัวกรอง
with st.sidebar:
    st.header("ตัวกรอง")
    campuses = sorted(summary["campus"].dropna().unique())
    sel_campus = st.multiselect("วิทยาเขต", campuses, default=campuses)
    faculties = sorted(summary.loc[summary["campus"].isin(sel_campus), "faculty"].dropna().unique())
    sel_fac = st.multiselect("คณะ", faculties, placeholder="ทุกคณะ")
    keyword = st.text_input("ค้นหาชื่อหลักสูตร")
    min_sources = st.slider("พบในอย่างน้อยกี่แหล่ง", 1, 3, 1)

mask = summary["campus"].isin(sel_campus) & (summary["n_sources"] >= min_sources)
if sel_fac:
    mask &= summary["faculty"].isin(sel_fac)
if keyword:
    mask &= summary["program_name"].fillna("").str.contains(keyword, case=False)
view = summary[mask].copy()

stats_view = stats[stats["campus"].isin(sel_campus)]
if sel_fac:
    stats_view = stats_view[stats_view["faculty"].isin(sel_fac)]
if keyword:
    stats_view = stats_view[stats_view["program_name"].fillna("").str.contains(keyword, case=False)]

# ---------------------------------------------------------------- KPI
latest_year = int(view["latest_tcas_year"].max()) if view["latest_tcas_year"].notna().any() else None
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("หลักสูตร (หลังตัดซ้ำ)", f"{len(view):,}")
k2.metric(f"ผู้สมัครรอบ 3 ({latest_year or '-'})", f"{int(view['applicants'].sum()):,}")
ratio = view["applicants"].sum() / view["seats_r3"].sum() if view["seats_r3"].sum() else 0
k3.metric("อัตราการแข่งขันรวม", f"1 : {ratio:.1f}")
k4.metric("นักศึกษาใหม่ 2567", f"{int(view['enrolled_2567'].sum()):,}")
k5.metric("ที่นั่ง TCAS70 (ทุกโครงการ)", f"{int(view['seats_2570'].sum()):,}")

# ---------------------------------------------------------------- กราฟ
c1, c2 = st.columns(2)
with c1:
    st.subheader("Top 15 หลักสูตรที่แข่งขันสูงสุด (รอบ 3 ปีล่าสุด)")
    top = view.dropna(subset=["competition_ratio"]).nlargest(15, "competition_ratio")
    top["label"] = top["program_name"].str.slice(0, 45) + " · " + top["campus"]
    st.altair_chart(
        alt.Chart(top).mark_bar().encode(
            x=alt.X("competition_ratio:Q", title="ผู้สมัครต่อ 1 ที่นั่ง"),
            y=alt.Y("label:N", sort="-x", title=None),
            color=alt.Color("faculty:N", legend=None),
            tooltip=["program_name", "faculty", "campus", "applicants", "seats_r3", "competition_ratio", "min_score"],
        ).properties(height=430),
        use_container_width=True,
    )
with c2:
    st.subheader("ผู้สมัครรอบ 3 แยกคณะ ย้อนหลัง 3 ปี")
    tc = stats_view[stats_view["source"] == "tcas"]
    by_fac = tc.groupby(["faculty", "academic_year"], as_index=False)["applicants"].sum()
    top_fac = by_fac.groupby("faculty")["applicants"].sum().nlargest(10).index
    st.altair_chart(
        alt.Chart(by_fac[by_fac["faculty"].isin(top_fac)]).mark_bar().encode(
            x=alt.X("applicants:Q", title="ผู้สมัคร"),
            y=alt.Y("faculty:N", sort="-x", title=None),
            color=alt.Color("academic_year:O", title="ปีการศึกษา"),
            yOffset="academic_year:O",
            tooltip=["faculty", "academic_year", "applicants"],
        ).properties(height=430),
        use_container_width=True,
    )

c3, c4 = st.columns(2)
with c3:
    st.subheader("แนวโน้มคะแนนต่ำสุดรอบ 3")
    options = (tc.dropna(subset=["min_score"]).groupby("program_name")["applicants"].sum()
               .sort_values(ascending=False).index.tolist())
    picks = st.multiselect("เลือกหลักสูตร", options, default=options[:4])
    trend = tc[tc["program_name"].isin(picks)].groupby(["program_name", "academic_year"], as_index=False)["min_score"].min()
    st.altair_chart(
        alt.Chart(trend).mark_line(point=True).encode(
            x=alt.X("academic_year:O", title="ปีการศึกษา"),
            y=alt.Y("min_score:Q", title="คะแนนต่ำสุด", scale=alt.Scale(zero=False)),
            color=alt.Color("program_name:N", title=None, legend=alt.Legend(orient="bottom", labelLimit=320)),
            tooltip=["program_name", "academic_year", "min_score"],
        ).properties(height=360),
        use_container_width=True,
    )
with c4:
    st.subheader("ผู้สมัครรอบ 3 vs นักศึกษาใหม่จริง (2567)")
    both = view.dropna(subset=["applicants_2567", "enrolled_2567"])
    st.altair_chart(
        alt.Chart(both).mark_circle(size=70, opacity=0.7).encode(
            x=alt.X("applicants_2567:Q", title="ผู้สมัครรอบ 3 ปี 2567 (ทปอ.)"),
            y=alt.Y("enrolled_2567:Q", title="นักศึกษาใหม่ 2567 (สป.อว.)"),
            color=alt.Color("campus:N", title="วิทยาเขต"),
            tooltip=["program_name", "faculty", "campus", "applicants_2567", "enrolled_2567"],
        ).properties(height=360),
        use_container_width=True,
    )
    st.caption("จุดที่อยู่ในตารางนี้คือหลักสูตรที่จับคู่ได้ทั้งในข้อมูล ทปอ. และ อว.")

# ---------------------------------------------------------------- ตาราง
st.subheader("ตารางหลักสูตร (รวมจาก 3 แหล่ง ตัดซ้ำแล้ว)")
table = view[["campus", "faculty", "program_name", "sources", "latest_tcas_year", "applicants", "seats_r3",
              "competition_ratio", "min_score", "max_score", "enrolled_2567", "seats_2570"]].rename(columns={
    "campus": "วิทยาเขต", "faculty": "คณะ", "program_name": "หลักสูตร", "sources": "แหล่ง",
    "latest_tcas_year": "ปี TCAS", "applicants": "ผู้สมัคร", "seats_r3": "รับ (รอบ 3)",
    "competition_ratio": "อัตราแข่งขัน", "min_score": "คะแนนต่ำสุด", "max_score": "คะแนนสูงสุด",
    "enrolled_2567": "เข้าใหม่ 2567", "seats_2570": "ที่นั่ง TCAS70",
}).sort_values("ผู้สมัคร", ascending=False)
st.dataframe(table, use_container_width=True, hide_index=True)
st.download_button("ดาวน์โหลด CSV", table.to_csv(index=False).encode("utf-8-sig"), "ku_program_summary.csv")
