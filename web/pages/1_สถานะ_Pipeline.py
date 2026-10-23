import json

import pandas as pd
import streamlit as st

from db import safe_query

st.set_page_config(page_title="สถานะ Pipeline", page_icon="🛠️", layout="wide")
st.title("สถานะ Pipeline")

runs, err = safe_query("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 30")
if err or runs.empty:
    st.info("ยังไม่มีประวัติการรัน DAG")
    st.stop()

last = runs.iloc[0]
icon = {"success": "🟢", "partial": "🟡", "no_load": "🔴"}.get(last["status"], "⚪")
c1, c2, c3, c4 = st.columns(4)
c1.metric("รอบล่าสุด", f"{icon} {last['status']}")
c2.metric("แถวที่โหลด (UPSERT)", f"{int(last['rows_loaded'] or 0):,}")
c3.metric("แถวที่ถูกกักไว้ (DQ)", f"{int(last['rows_quarantined'] or 0):,}")
c4.metric("เส้นทางหลังตรวจคุณภาพ", last["dq_branch"] or "-")

details = last["details"] if isinstance(last["details"], dict) else json.loads(last["details"] or "{}")
st.subheader("สถานะแต่ละแหล่งข้อมูล (รอบล่าสุด)")
labels = {"tcas": "ทปอ. สถิติ TCAS รอบ 3", "mhesi": "สป.อว. นักศึกษาเข้าใหม่", "kuadm": "admission.ku.ac.th"}
per_source = (details.get("info") or {}).get("rows_per_source", {})
ok = set((last["sources_ok"] or "").split(","))
st.dataframe(pd.DataFrame([
    {"แหล่ง": labels[s], "สถานะ": "✅ สำเร็จ" if s in ok else "❌ ล้มเหลว", "แถวที่ดึงได้": per_source.get(s, 0)}
    for s in labels
]), hide_index=True, use_container_width=True)

summary = details.get("summary") or {}
if summary:
    st.write(f"ตัดซ้ำข้ามแหล่ง: รวม **{summary.get('source_rows_merged', 0):,}** แถวจากทุกแหล่ง เหลือ "
             f"**{summary.get('programs', 0):,}** หลักสูตร (พบมากกว่า 1 แหล่ง {summary.get('programs_multi_source', 0):,} หลักสูตร)")

st.subheader("ประวัติการรัน")
show = runs[["run_id", "started_at", "finished_at", "status", "dq_branch", "sources_ok", "sources_failed",
             "rows_extracted", "rows_loaded", "rows_quarantined"]]
st.dataframe(show, hide_index=True, use_container_width=True)

with st.expander("สถานะ task ในรอบล่าสุด"):
    states = details.get("task_states") or {}
    st.dataframe(pd.DataFrame(sorted(states.items()), columns=["task", "state"]), hide_index=True,
                 use_container_width=True)

st.subheader("แถวที่ไม่ผ่านการตรวจคุณภาพ (ล่าสุด 200 แถว)")
bad, _ = safe_query("SELECT created_at, source, academic_year, source_record_id, reason FROM dq_quarantine "
                    "ORDER BY id DESC LIMIT 200")
if bad.empty:
    st.success("ไม่มีแถวที่ถูกกักไว้")
else:
    st.dataframe(bad, hide_index=True, use_container_width=True)
