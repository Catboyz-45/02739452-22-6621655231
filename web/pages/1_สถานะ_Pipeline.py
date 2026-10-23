import json

import pandas as pd
import streamlit as st

import style
from db import safe_query

st.set_page_config(page_title="สถานะ Pipeline", page_icon="🛠️", layout="wide", initial_sidebar_state="collapsed")
style.apply()

runs, err = safe_query("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 30")
style.topbar("สถานะ Pipeline", "ผลการรัน DAG ku_faculty_popularity สถานะของแต่ละแหล่งข้อมูล และแถวที่ไม่ผ่านการตรวจคุณภาพ",
             "Airflow: http://localhost:8080")
if err or runs.empty:
    st.info("ยังไม่มีประวัติการรัน DAG")
    st.stop()

last = runs.iloc[0]
details = last["details"] if isinstance(last["details"], dict) else json.loads(last["details"] or "{}")
STATUS = {"success": ("#1baf7a", "สำเร็จ"), "partial": ("#eda100", "สำเร็จบางแหล่ง"), "no_load": ("#e34948", "ไม่ได้โหลด")}
color, label = STATUS.get(last["status"], ("#9aa19c", last["status"]))
when = pd.to_datetime(last["finished_at"]).tz_convert("Asia/Bangkok").strftime("%d/%m/%Y %H:%M")

k1, k2, k3, k4 = st.columns(4)
style.kpi(k1, "รอบล่าสุด", f'<span class="dot" style="background:{color};width:14px;height:14px"></span>{label}',
          f"เสร็จเมื่อ {when}")
style.kpi(k2, "แถวที่โหลด (UPSERT)", f"{int(last['rows_loaded'] or 0):,}", f"ดึงมาทั้งหมด {int(last['rows_extracted'] or 0):,} แถว")
style.kpi(k3, "แถวที่ถูกกักไว้", f"{int(last['rows_quarantined'] or 0):,}", "ไม่ผ่านการตรวจคุณภาพ")
summary = details.get("summary") or {}
style.kpi(k4, "หลักสูตรหลังตัดซ้ำ", f"{summary.get('programs', 0):,}",
          f"พบมากกว่า 1 แหล่ง {summary.get('programs_multi_source', 0):,} หลักสูตร")
st.write("")

left, right = st.columns([1, 1.4], gap="medium")
with left, st.container(border=True):
    style.title("แหล่งข้อมูล (รอบล่าสุด)", f"เส้นทางหลังตรวจคุณภาพ: {last['dq_branch'] or '-'}")
    labels = {"tcas": "ทปอ. สถิติ TCAS รอบ 3", "mhesi": "สป.อว. นักศึกษาเข้าใหม่", "kuadm": "admission.ku.ac.th"}
    per_source = (details.get("info") or {}).get("rows_per_source", {})
    ok = set((last["sources_ok"] or "").split(","))
    st.markdown("".join(
        f'<div class="lvl"><div style="display:flex;align-items:center">'
        f'<span class="dot" style="background:{"#1baf7a" if s in ok else "#e34948"}"></span>'
        f'<div><div class="nm">{name}</div><div class="r">{"ดึงสำเร็จ" if s in ok else "ดึงไม่สำเร็จ"}</div></div></div>'
        f'<b>{per_source.get(s, 0):,} แถว</b></div>' for s, name in labels.items()), unsafe_allow_html=True)
    st.markdown('<div class="note">ถ้าแหล่งใดล่ม DAG ยังรวมข้อมูลจากแหล่งที่เหลือ และรอบนั้นจะมีสถานะ "สำเร็จบางแหล่ง"</div>',
                unsafe_allow_html=True)

with right, st.container(border=True):
    style.title("ประวัติการรัน", f"{len(runs)} รอบล่าสุด")
    hist = pd.DataFrame({
        "รอบ": runs["run_id"].str.slice(0, 32),
        "เริ่ม": pd.to_datetime(runs["started_at"]).dt.tz_convert("Asia/Bangkok").dt.strftime("%d/%m %H:%M"),
        "สถานะ": runs["status"].map(lambda x: STATUS.get(x, ("", x))[1]),
        "แหล่งที่ล้ม": runs["sources_failed"].replace("", "-").fillna("-"),
        "โหลด": runs["rows_loaded"].fillna(0).astype(int).map("{:,}".format),
    })
    st.markdown(style.table(hist, num=("โหลด",), muted=("เริ่ม", "แหล่งที่ล้ม")), unsafe_allow_html=True)

with st.container(border=True):
    bad, _ = safe_query("SELECT DISTINCT ON (source, academic_year, source_record_id) source, academic_year, "
                        "source_record_id, reason FROM dq_quarantine ORDER BY source, academic_year, source_record_id, id DESC")
    style.title("แถวที่ไม่ผ่านการตรวจคุณภาพ", f"{len(bad):,} รายการ (ไม่นับซ้ำ) · ถูกแยกไปตาราง dq_quarantine ไม่นำมาคำนวณ")
    if bad.empty:
        st.success("ไม่มีแถวที่ถูกกักไว้")
    else:
        show = pd.DataFrame({"แหล่ง": bad["source"], "ปี": bad["academic_year"].astype(str),
                             "รายการ": bad["source_record_id"].str.replace("|", " · ", regex=False).str.slice(0, 90),
                             "เหตุผล": bad["reason"]})
        st.markdown(style.table(show, muted=("แหล่ง", "ปี")), unsafe_allow_html=True)

with st.expander("สถานะ task ในรอบล่าสุด"):
    states = details.get("task_states") or {}
    st.markdown(style.table(pd.DataFrame(sorted(states.items()), columns=["task", "สถานะ"])), unsafe_allow_html=True)
