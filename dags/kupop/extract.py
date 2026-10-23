"""Extract: ดึงข้อมูลจาก 3 แหล่งแล้วแปลงเป็นคอลัมน์ชุดเดียวกัน (UNIFIED_COLUMNS) เก็บเป็น CSV ใน staging"""
import io
import logging
import re
import time

import pandas as pd
from bs4 import BeautifulSoup

from kupop.common import (
    DATAGOTH_PACKAGE_API, KU_NAME, KUADM_BASE, KUADM_YEAR, MHESI_PACKAGE_ID, MHESI_YEAR,
    MYTCAS_STAT_URL, TCAS_FALLBACK_FILES, TCAS_YEARS, UNIFIED_COLUMNS,
    http_get, major_key, norm_campus, norm_space, to_float, to_int,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------- แหล่งที่ 1: ทปอ.
def discover_tcas_files() -> dict:
    """Scrape หน้า mytcas.com/stat หาลิงก์ไฟล์ Excel คะแนนสูงสุด-ต่ำสุดรอบ 3 ของแต่ละปี"""
    found = {}
    try:
        soup = BeautifulSoup(http_get(MYTCAS_STAT_URL, timeout=30).text, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.lower().endswith(".xlsx") or not re.search(r"max\s*-?min|minmax", href, re.I):
                continue
            m = re.search(r"T(?:CAS)?(\d{2})", href.rsplit("/", 1)[-1], re.I)
            if m and int(m.group(1)) in TCAS_YEARS:
                found.setdefault(int(m.group(1)), href)
        log.info("scrape mytcas.com/stat พบไฟล์ปี: %s", sorted(found))
    except Exception as exc:  # หน้าเว็บล่มหรือเปลี่ยนโครงสร้าง
        log.warning("scrape mytcas.com/stat ไม่สำเร็จ: %s", exc)
    for year, url in TCAS_FALLBACK_FILES.items():
        if year not in found:
            log.warning("ปี %s หาลิงก์จากหน้าเว็บไม่เจอ ใช้ลิงก์สำรอง", year)
            found[year] = url
    return found


def _pick_col(columns, keyword):
    """เลือกคอลัมน์คะแนนรอบสุดท้าย (ไม่เอาคอลัมน์ DS) เพราะแต่ละปีตั้งชื่อคอลัมน์ไม่เหมือนกัน"""
    cands = [c for c in columns if keyword in str(c) and "DS" not in str(c)]
    return cands[-1] if cands else None


def parse_tcas_excel(content: bytes, year2: int) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(content), engine="openpyxl", dtype=str)
    df.columns = [norm_space(c) for c in df.columns]
    df = df[df["สถาบัน"].map(norm_space) == KU_NAME]
    min_col = _pick_col(df.columns, "คะแนนต่ำสุด")
    max_col = _pick_col(df.columns, "คะแนนสูงสุด")
    rows = []
    for _, r in df.iterrows():
        program = norm_space(r.get("หลักสูตร"))
        major = norm_space(r.get("สาขา/วิชาเอก"))
        if major in ("0", "-"):
            major = ""
        full_name = f"{program} {major}".strip()
        rows.append({
            "source": "tcas",
            "academic_year": 2500 + year2,
            "source_record_id": "|".join([
                norm_space(r.get("รหัสหลักสูตร")), norm_space(r.get("รายละเอียด")),
                major, norm_space(r.get("รหัสโครงการ")),
            ]),
            "campus": norm_campus(r.get("วิทยาเขต")),
            "faculty": norm_space(r.get("คณะ")),
            "program_name": full_name,
            "major_key": major_key(full_name),
            "project": "TCAS รอบ 3 Admission",
            "seats": to_int(r.get("รับ")),
            "applicants": to_int(r.get("สมัคร")),
            "enrolled": None,
            "min_score": to_float(r.get(min_col)) if min_col else None,
            "max_score": to_float(r.get(max_col)) if max_col else None,
        })
    return pd.DataFrame(rows, columns=UNIFIED_COLUMNS)


def extract_tcas() -> pd.DataFrame:
    frames = []
    for year2, url in sorted(discover_tcas_files().items()):
        log.info("ดาวน์โหลด TCAS%s: %s", year2, url)
        frames.append(parse_tcas_excel(http_get(url, timeout=120).content, year2))
    df = pd.concat(frames, ignore_index=True)
    log.info("TCAS: ได้ %d แถวของ มก.", len(df))
    return df


# ---------------------------------------------------------------- แหล่งที่ 2: สป.อว.
def find_mhesi_csv_url() -> str:
    """ใช้ CKAN API ของ data.go.th หาลิงก์ไฟล์ CSV ปีที่ต้องการ"""
    meta = http_get(DATAGOTH_PACKAGE_API, params={"id": MHESI_PACKAGE_ID}, timeout=30).json()
    for res in meta["result"]["resources"]:
        if str(res.get("format", "")).upper() == "CSV" and str(MHESI_YEAR) in res.get("name", ""):
            return res["url"]
    raise RuntimeError(f"ไม่พบไฟล์ CSV ปี {MHESI_YEAR} ใน {MHESI_PACKAGE_ID}")


def extract_mhesi() -> pd.DataFrame:
    url = find_mhesi_csv_url()
    log.info("ดาวน์โหลดข้อมูล อว.: %s", url)
    raw = pd.read_csv(io.BytesIO(http_get(url, timeout=180).content), dtype=str, encoding="utf-8-sig")
    raw.columns = [norm_space(c).upper() for c in raw.columns]
    amount_col = next(c for c in raw.columns if "AMOUNT" in c or "จำนวน" in c)
    level_col = next(c for c in raw.columns if c.startswith("LEV_NAME"))
    year_col = next((c for c in raw.columns if c in ("ACADEMIC_YEAR", "YEAR")), None)

    ku = raw[(raw["UNIV_MASTERNAME_TH"].map(norm_space) == KU_NAME)
             & (raw[level_col].map(norm_space).isin(["ป.ตรี", "ปริญญาตรี"]))].copy()
    ku["campus"] = ku["UNIV_NAME_TH"].map(norm_campus)
    ku["faculty"] = ku["FAC_NAME"].map(norm_space)
    ku["program_name"] = ku["PROGRAM_NAME"].map(norm_space)
    ku["amount"] = ku[amount_col].map(to_int).fillna(0).astype(int)
    ku["year"] = ku[year_col].map(to_int) if year_col else MHESI_YEAR

    # ข้อมูลต้นทางแยกแถวตามเพศ -> รวมเป็นยอดต่อหลักสูตร
    grouped = ku.groupby(["year", "campus", "faculty", "program_name"], as_index=False)["amount"].sum()
    df = pd.DataFrame({
        "source": "mhesi",
        "academic_year": grouped["year"],
        "source_record_id": grouped["campus"] + "|" + grouped["faculty"] + "|" + grouped["program_name"],
        "campus": grouped["campus"],
        "faculty": grouped["faculty"],
        "program_name": grouped["program_name"],
        "major_key": grouped["program_name"].map(major_key),
        "project": "นักศึกษาเข้าใหม่ (ทุกรอบ)",
        "seats": None,
        "applicants": None,
        "enrolled": grouped["amount"],
        "min_score": None,
        "max_score": None,
    }, columns=UNIFIED_COLUMNS)
    log.info("อว.: ได้ %d หลักสูตรของ มก. (จาก %d แถวดิบ)", len(df), len(ku))
    return df


# ---------------------------------------------------------------- แหล่งที่ 3: admission.ku.ac.th
def list_kuadm_projects() -> list:
    """Scrape หน้าแรกของเว็บรับสมัคร มก. หารหัสโครงการทั้งหมด"""
    html = http_get(KUADM_BASE + "/", timeout=30).text
    ids = sorted({int(x) for x in re.findall(r"/majors/project/(\d+)/", html)})
    if not ids:
        raise RuntimeError("ไม่พบโครงการในหน้า admission.ku.ac.th")
    log.info("พบ %d โครงการ: %s", len(ids), ids)
    return ids


def parse_kuadm_project(html: str, project_id: int) -> pd.DataFrame:
    soup = BeautifulSoup(html, "lxml")
    h2 = soup.find("h2")
    project = norm_space(h2.get_text()) if h2 else f"project {project_id}"
    project = re.sub(r"^เกณฑ์\s*", "", project)
    table = soup.find("table", class_="criteria-table")
    rows, faculty, campus = [], "", ""
    if table is None:
        return pd.DataFrame(rows, columns=UNIFIED_COLUMNS)
    for tr in table.find_all("tr"):
        header = tr.find("th", attrs={"colspan": True})
        if header:  # แถวหัวคณะ เช่น "คณะเกษตร (วิทยาเขตบางเขน)"
            text = norm_space(header.get_text())
            m = re.match(r"(.*?)\s*\(([^()]*)\)\s*$", text)
            faculty, campus = (m.group(1), m.group(2)) if m else (text, "")
            continue
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 2 or "text-center" not in (tds[1].get("class") or []):
            continue  # แถวต่อเนื่องที่มีแค่เกณฑ์ (rowspan)
        name = norm_space(tds[0].get_text())
        crit = tr.find("span", class_="criteria-ids")
        crit_id = norm_space(crit.get_text()) if crit else ""
        rows.append({
            "source": "kuadm",
            "academic_year": KUADM_YEAR,
            "source_record_id": f"{project_id}|{campus}|{name}|{crit_id}",
            "campus": norm_campus(campus),
            "faculty": faculty,
            "program_name": name,
            "major_key": major_key(name),
            "project": project,
            "seats": to_int(tds[1].get_text()),
            "applicants": None,
            "enrolled": None,
            "min_score": None,
            "max_score": None,
        })
    return pd.DataFrame(rows, columns=UNIFIED_COLUMNS)


def extract_kuadm_project(project_id: int) -> pd.DataFrame:
    time.sleep(1)  # เว้นระยะไม่ให้โหลดเว็บมหาวิทยาลัยหนักเกินไป
    html = http_get(f"{KUADM_BASE}/majors/project/{project_id}/", timeout=60).text
    df = parse_kuadm_project(html, project_id)
    log.info("โครงการ %s: %d แถว", project_id, len(df))
    return df
