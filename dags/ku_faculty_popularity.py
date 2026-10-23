"""
### ku_faculty_popularity — ความนิยมและคะแนนเข้าคณะ ป.ตรี ม.เกษตรศาสตร์

รวมข้อมูล 3 แหล่ง:
1. **ทปอ.** scrape หน้า mytcas.com/stat หาไฟล์ Excel สถิติ TCAS รอบ 3 (ปี 67–69): จำนวนรับ, ผู้สมัคร, คะแนนต่ำสุด/สูงสุด
2. **สป.อว.** หา metadata ผ่าน CKAN API ของ data.go.th แล้วดาวน์โหลด CSV นักศึกษาเข้าใหม่ ปี 2567
3. **admission.ku.ac.th** scrape ตาราง HTML จำนวนรับ TCAS70 ทุกโครงการ (Dynamic Task Mapping ตามโครงการ)

ขั้นตอน: extract (TaskGroup รันขนานกัน, แหล่งไหนล่มก็รวมจากแหล่งที่เหลือ) → merge + ตัดซ้ำภายในแหล่ง
→ ตรวจคุณภาพแล้วแยกเส้นทาง → UPSERT → สร้างตารางสรุปที่ตัดซ้ำข้ามแหล่ง → บันทึกสถานะ pipeline
"""
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
from airflow.decorators import dag, task, task_group
from airflow.exceptions import AirflowException
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import get_current_context
from airflow.utils.trigger_rule import TriggerRule

from kupop import db
from kupop import extract as ex
from kupop import transform as tf
from kupop.common import SOURCES, staging_dir

log = logging.getLogger(__name__)
TEXT_DTYPES = {c: str for c in ["source", "source_record_id", "campus", "faculty", "program_name", "major_key", "project"]}


def _stage():
    return staging_dir(get_current_context()["run_id"])


def _simulate_outage(source: str):
    """ทดสอบกรณีแหล่งล่ม: ตั้ง Airflow Variable kupop_simulate_down เช่น "mhesi" หรือ "tcas,kuadm" """
    from airflow.models import Variable

    down = {s.strip() for s in Variable.get("kupop_simulate_down", default_var="").split(",") if s.strip()}
    if source in down:
        raise AirflowException(f"จำลองแหล่ง {source} ล่ม (Variable kupop_simulate_down)")


def _read(path):
    return pd.read_csv(path, dtype=TEXT_DTYPES, keep_default_na=False, na_values=[""])


@dag(
    dag_id="ku_faculty_popularity",
    description="ความนิยมและคะแนนเข้าคณะ ป.ตรี ม.เกษตรศาสตร์ จาก ทปอ. + สป.อว. + admission.ku.ac.th",
    schedule="@daily",
    start_date=datetime(2026, 10, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "6621655231", "retries": 1, "retry_delay": timedelta(seconds=30)},
    tags=["02739452", "final", "tcas"],
    doc_md=__doc__,
)
def ku_faculty_popularity():
    start = EmptyOperator(task_id="start")

    @task
    def create_tables():
        db.ensure_schema()

    @task_group(group_id="extract", tooltip="ดึงข้อมูล 3 แหล่งขนานกัน")
    def extract_group():
        @task
        def extract_tcas():
            _simulate_outage("tcas")
            df = ex.extract_tcas()
            df.to_csv(_stage() / "tcas.csv", index=False)
            return len(df)

        @task
        def extract_mhesi():
            _simulate_outage("mhesi")
            df = ex.extract_mhesi()
            df.to_csv(_stage() / "mhesi.csv", index=False)
            return len(df)

        @task
        def list_kuadm_projects():
            _simulate_outage("kuadm")
            return ex.list_kuadm_projects()

        @task(retries=2, max_active_tis_per_dag=3)
        def extract_kuadm_project(project_id: int):
            df = ex.extract_kuadm_project(project_id)
            df.to_csv(_stage() / f"kuadm_{project_id}.csv", index=False)
            return len(df)

        @task(trigger_rule=TriggerRule.ALL_DONE)
        def combine_kuadm():
            stage = _stage()
            parts = [_read(p) for p in sorted(stage.glob("kuadm_*.csv"))]
            if not parts:
                raise AirflowException("admission.ku.ac.th: ไม่ได้ข้อมูลจากโครงการใดเลย")
            df = pd.concat(parts, ignore_index=True)
            df.to_csv(stage / "kuadm.csv", index=False)
            return len(df)

        project_ids = list_kuadm_projects()
        pages = extract_kuadm_project.expand(project_id=project_ids)
        combined = combine_kuadm()
        pages >> combined
        return [extract_tcas(), extract_mhesi(), combined]

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def merge_and_transform():
        stage = _stage()
        frames = {s: (_read(stage / f"{s}.csv") if (stage / f"{s}.csv").exists() else None) for s in SOURCES}
        ok = [s for s in SOURCES if frames[s] is not None and len(frames[s])]
        failed = [s for s in SOURCES if s not in ok]
        if failed:
            log.warning("แหล่งที่ดึงไม่สำเร็จ: %s รวมเฉพาะแหล่งที่เหลือ: %s", failed, ok)
        df, dup_removed = tf.merge_sources(frames)
        df.to_csv(stage / "unified.csv", index=False)
        return {
            "sources_ok": ok,
            "sources_failed": failed,
            "rows_extracted": len(df),
            "dup_removed_within_source": dup_removed,
            "rows_per_source": {k: int(v) for k, v in df["source"].value_counts().items()},
        }

    @task.branch
    def quality_check(info: dict):
        stage = _stage()
        df = _read(stage / "unified.csv")
        good, bad = tf.quality_check(df)
        good.to_csv(stage / "good.csv", index=False)
        bad.to_csv(stage / "bad.csv", index=False)
        branch = tf.choose_branch(len(good), len(bad), len(info["sources_ok"]))
        dq = {"good": len(good), "bad": len(bad), "branch": branch,
              "bad_reasons": {k: int(v) for k, v in bad["reason"].value_counts().items()} if len(bad) else {}}
        get_current_context()["ti"].xcom_push(key="dq", value=dq)
        log.info("ผลตรวจคุณภาพ: %s", dq)
        return branch

    @task
    def quarantine_bad_rows():
        bad = _read(_stage() / "bad.csv")
        return db.insert_quarantine(get_current_context()["run_id"], bad)

    @task
    def alert_insufficient_data():
        log.error("ข้อมูลไม่พอ (น้อยกว่า %d แถว หรือไม่มีแหล่งใดสำเร็จ) ข้ามการโหลดเพื่อเก็บข้อมูลเดิมไว้", tf.MIN_ROWS)

    @task(trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS)
    def load_to_postgres():
        return db.upsert_stats(_read(_stage() / "good.csv"))

    @task
    def build_program_summary():
        summary = tf.build_summary(db.read_stats())
        n = db.upsert_summary(summary)
        multi = int((summary["n_sources"] > 1).sum()) if n else 0
        log.info("สรุป %d หลักสูตร (พบมากกว่า 1 แหล่ง %d หลักสูตร)", n, multi)
        return {"programs": n, "programs_multi_source": multi,
                "source_rows_merged": int(summary["n_source_rows"].sum()) if n else 0}

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def record_pipeline_run():
        ctx = get_current_context()
        dag_run, ti = ctx["dag_run"], ctx["ti"]
        # ดึง XCom เองแทนการรับเป็น argument เพราะ task ต้นทางอาจถูก skip/fail
        info = ti.xcom_pull(task_ids="merge_and_transform")
        summary = ti.xcom_pull(task_ids="build_program_summary")
        info = info or {"sources_ok": [], "sources_failed": SOURCES, "rows_extracted": 0}
        dq = ti.xcom_pull(task_ids="quality_check", key="dq") or {}
        loaded = ti.xcom_pull(task_ids="load_to_postgres")
        states = {}
        for t in dag_run.get_task_instances():
            name = t.task_id if t.map_index < 0 else f"{t.task_id}[{t.map_index}]"
            states[name] = t.state
        if dq.get("branch") == "alert_insufficient_data" or loaded is None:
            status = "no_load"
        elif info["sources_failed"]:
            status = "partial"
        else:
            status = "success"
        db.save_run({
            "run_id": ctx["run_id"],
            "started_at": dag_run.start_date,
            "finished_at": datetime.now(timezone.utc),
            "status": status,
            "dq_branch": dq.get("branch"),
            "sources_ok": ",".join(info["sources_ok"]),
            "sources_failed": ",".join(info["sources_failed"]),
            "rows_extracted": info["rows_extracted"],
            "rows_loaded": loaded or 0,
            "rows_quarantined": dq.get("bad", 0),
            "details": {"info": info, "dq": dq, "summary": summary, "task_states": states},
        })

    end = EmptyOperator(task_id="end", trigger_rule=TriggerRule.ALL_DONE)

    extracted = extract_group()
    info = merge_and_transform()
    branch = quality_check(info)
    quarantine = quarantine_bad_rows()
    alert = alert_insufficient_data()
    loaded = load_to_postgres()
    summary = build_program_summary()
    record = record_pipeline_run()

    start >> create_tables() >> extracted >> info
    branch >> [quarantine, alert, loaded]
    quarantine >> loaded >> summary
    [summary, alert] >> record >> end


ku_faculty_popularity()
