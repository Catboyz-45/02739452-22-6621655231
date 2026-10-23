"""ค่าคงที่และฟังก์ชันช่วยที่ทุกขั้นตอนใช้ร่วมกัน"""
import os
import re
from pathlib import Path

import requests

DATA_DIR = Path(os.environ.get("KUPOP_DATA_DIR", "/opt/airflow/data"))
KU_NAME = "มหาวิทยาลัยเกษตรศาสตร์"
HEADERS = {"User-Agent": "Mozilla/5.0 (KU 02739452 student data-engineering project)"}

# แหล่งที่ 1: ทปอ. (mytcas) — scrape หน้าสถิติเพื่อหาลิงก์ไฟล์ Excel
MYTCAS_STAT_URL = "https://www.mytcas.com/stat/"
TCAS_YEARS = [67, 68, 69]
# ใช้เฉพาะตอนหน้า /stat/ เปลี่ยนโครงสร้างจนหาลิงก์ไม่เจอ
TCAS_FALLBACK_FILES = {
    67: "https://assets.mytcas.com/67/TCAS67_maxmin.xlsx",
    68: "https://assets.mytcas.com/68/T68-stat-r3_2-maxmin-24May25.xlsx",
    69: "https://assets.mytcas.com/69/TCAS69-R3-MinMax-10June26.xlsx",
}

# แหล่งที่ 2: สป.อว. ชุดข้อมูลนักศึกษาเข้าใหม่ (ค้น metadata ผ่าน CKAN API ของ data.go.th)
DATAGOTH_PACKAGE_API = "https://data.go.th/api/3/action/package_show"
MHESI_PACKAGE_ID = "univ_std_11_04"
MHESI_YEAR = 2567

# แหล่งที่ 3: เว็บรับสมัคร มก. (scrape ตาราง HTML)
KUADM_BASE = "https://admission.ku.ac.th"
KUADM_YEAR = 2570

UNIFIED_COLUMNS = [
    "source", "academic_year", "source_record_id", "campus", "faculty",
    "program_name", "major_key", "project", "seats", "applicants", "enrolled",
    "min_score", "max_score",
]

SOURCES = ["tcas", "mhesi", "kuadm"]
SOURCE_LABELS = {
    "tcas": "ทปอ. สถิติ TCAS รอบ 3",
    "mhesi": "สป.อว. นักศึกษาเข้าใหม่",
    "kuadm": "admission.ku.ac.th",
}


def staging_dir(run_id: str) -> Path:
    """โฟลเดอร์แยกต่อ DAG run กันไม่ให้ใช้ไฟล์ค้างจากรอบก่อน"""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", run_id)
    path = DATA_DIR / "staging" / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def http_get(url: str, timeout: int = 60, **kwargs) -> requests.Response:
    resp = requests.get(url, headers=HEADERS, timeout=timeout, **kwargs)
    resp.raise_for_status()
    return resp


def norm_space(value) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.lower() == "nan":
        return ""
    return re.sub(r"\s+", " ", text).strip()


def norm_campus(value) -> str:
    text = str(value or "")
    for key in ["บางเขน", "กำแพงแสน", "ศรีราชา", "สกลนคร", "สุพรรณบุรี"]:
        if key in text:
            return key
    return norm_space(text) or "ไม่ระบุ"


def major_key(name) -> str:
    """คีย์กลางสำหรับจับคู่หลักสูตรเดียวกันข้ามแหล่ง

    'วท.บ. สาขาวิชาวิทยาการคอมพิวเตอร์ (ภาษาไทย ปกติ)' -> 'วิทยาการคอมพิวเตอร์'
    'วิทยาการคอมพิวเตอร์'                              -> 'วิทยาการคอมพิวเตอร์'
    """
    text = norm_space(name)
    if "สาขาวิชา" in text:
        text = re.sub(r"\(.*?\)", "", text.split("สาขาวิชา", 1)[1])
    else:
        # หลักสูตรที่ไม่มีคำว่า "สาขาวิชา" เช่น 'น.บ.(นิติศาสตรบัณฑิต)' ใช้ชื่อปริญญาในวงเล็บแทน
        inner = [p for p in re.findall(r"\((.*?)\)", text)
                 if not re.search(r"ภาษา|ปกติ|พิเศษ|นานาชาติ|โครงการ", p)]
        text = inner[0] if inner else re.sub(r"\(.*?\)", "", text)
        text = re.sub(r"บัณฑิต\s*$", "", text.strip())
    text = re.sub(r"^วิชาเอก", "", text)
    # ตัดช่องว่าง/เครื่องหมาย และไม้ทัณฑฆาต ('นิติศาสตร' กับ 'นิติศาสตร์' ให้เป็นคีย์เดียวกัน)
    text = re.sub(r"[\s\-–.,/์]", "", text)
    return text.lower()


def to_int(value):
    text = re.sub(r"[^\d-]", "", norm_space(value))
    return int(text) if text not in ("", "-") else None


def to_float(value):
    text = norm_space(value).replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None
