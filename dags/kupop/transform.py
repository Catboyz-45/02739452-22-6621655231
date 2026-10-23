"""Transform: รวมแหล่ง ตัดซ้ำ ตรวจคุณภาพ และสร้างตารางสรุปต่อหลักสูตร"""
import logging

import pandas as pd

from kupop.common import SOURCES, UNIFIED_COLUMNS

log = logging.getLogger(__name__)

MIN_ROWS = 100


def merge_sources(frames: dict) -> tuple:
    """รวม DataFrame ของแต่ละแหล่งเป็นชุดเดียว และตัดแถวซ้ำภายในแหล่ง (คีย์เดียวกับ UPSERT)"""
    present = [df for df in frames.values() if df is not None and len(df)]
    if not present:
        return pd.DataFrame(columns=UNIFIED_COLUMNS), 0
    df = pd.concat(present, ignore_index=True)[UNIFIED_COLUMNS]
    before = len(df)
    df = df.drop_duplicates(subset=["source", "academic_year", "source_record_id"], keep="last")
    return df.reset_index(drop=True), before - len(df)


def quality_check(df: pd.DataFrame) -> tuple:
    """คืนค่า (แถวที่ผ่าน, แถวที่ไม่ผ่านพร้อมเหตุผล)"""
    reasons = pd.Series([""] * len(df), index=df.index)

    def flag(mask, text):
        mask = mask.fillna(False)
        reasons[mask] = reasons[mask] + text + "; "

    num = {c: pd.to_numeric(df[c], errors="coerce") for c in ["seats", "applicants", "enrolled", "min_score", "max_score"]}
    flag(df["program_name"].fillna("").str.strip() == "", "ไม่มีชื่อหลักสูตร")
    flag(df["major_key"].fillna("").str.strip() == "", "สร้างคีย์หลักสูตรไม่ได้")
    flag(~df["academic_year"].between(2560, 2575), "ปีการศึกษาผิดช่วง")
    for col in ["seats", "applicants", "enrolled"]:
        flag(num[col] < 0, f"{col} ติดลบ")
    flag((df["source"] == "tcas") & ~(num["seats"] > 0), "TCAS จำนวนรับต้องมากกว่า 0")
    flag((df["source"] == "kuadm") & num["seats"].isna(), "ไม่มีจำนวนรับ")
    flag((df["source"] == "mhesi") & ~(num["enrolled"] > 0), "ยอดเข้าใหม่ต้องมากกว่า 0")
    flag((num["min_score"] < 0) | (num["min_score"] > 100) | (num["max_score"] < 0) | (num["max_score"] > 100),
         "คะแนนอยู่นอกช่วง 0-100")
    flag(num["min_score"] > num["max_score"], "คะแนนต่ำสุดมากกว่าคะแนนสูงสุด")

    bad_mask = reasons != ""
    bad = df[bad_mask].copy()
    bad["reason"] = reasons[bad_mask].str.rstrip("; ")
    return df[~bad_mask].copy(), bad


def choose_branch(n_good: int, n_bad: int, n_sources_ok: int) -> str:
    if n_sources_ok == 0 or n_good < MIN_ROWS:
        return "alert_insufficient_data"
    if n_bad > 0:
        return "quarantine_bad_rows"
    return "load_to_postgres"


def _first(series):
    s = series.dropna()
    s = s[s.astype(str).str.strip() != ""]
    return s.iloc[0] if len(s) else None


def build_summary(stats: pd.DataFrame) -> pd.DataFrame:
    """ตัดซ้ำข้ามแหล่ง: หลักสูตรเดียวกัน (วิทยาเขต + major_key) จากทุกแหล่งรวมเหลือ 1 แถว

    ชื่อคณะ/หลักสูตรเลือกตามลำดับความน่าเชื่อถือ ทปอ. > admission.ku > อว.
    """
    if stats.empty:
        return pd.DataFrame()
    stats = stats.copy()
    for col in ["seats", "applicants", "enrolled", "min_score", "max_score"]:
        stats[col] = pd.to_numeric(stats[col], errors="coerce")
    stats["prio"] = stats["source"].map({"tcas": 0, "kuadm": 1, "mhesi": 2})
    stats = stats.sort_values(["prio", "academic_year"], ascending=[True, False])
    key = ["campus", "major_key"]

    base = stats.groupby(key).agg(
        faculty=("faculty", _first),
        program_name=("program_name", _first),
        sources=("source", lambda s: ",".join(x for x in SOURCES if x in set(s))),
        n_source_rows=("source", "size"),
    )
    base["n_sources"] = base["sources"].str.count(",") + 1

    tcas = stats[stats["source"] == "tcas"]
    if not tcas.empty:
        per_year = tcas.groupby(key + ["academic_year"]).agg(
            applicants=("applicants", "sum"), seats_r3=("seats", "sum"),
            min_score=("min_score", "min"), max_score=("max_score", "max"),
        ).reset_index()
        latest = per_year.sort_values("academic_year").groupby(key).tail(1).set_index(key)
        latest = latest.rename(columns={"academic_year": "latest_tcas_year"})
        base = base.join(latest)
        y67 = per_year[per_year["academic_year"] == 2567].set_index(key)["applicants"]
        base = base.join(y67.rename("applicants_2567"))
    mhesi = stats[stats["source"] == "mhesi"]
    if not mhesi.empty:
        base = base.join(mhesi.groupby(key)["enrolled"].sum().rename("enrolled_2567"))
    kuadm = stats[stats["source"] == "kuadm"]
    if not kuadm.empty:
        base = base.join(kuadm.groupby(key).agg(
            seats_2570=("seats", "sum"), n_projects_2570=("project", "nunique")))

    for col in ["latest_tcas_year", "applicants", "seats_r3", "min_score", "max_score",
                "applicants_2567", "enrolled_2567", "seats_2570", "n_projects_2570"]:
        if col not in base:
            base[col] = None
    base["competition_ratio"] = (base["applicants"] / base["seats_r3"]).where(base["seats_r3"] > 0).round(2)
    return base.reset_index()
