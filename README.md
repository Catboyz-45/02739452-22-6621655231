# ความนิยมและคะแนนเข้าคณะ ป.ตรี ม.เกษตรศาสตร์

ข้อสอบปลายภาค 02739452 แพลตฟอร์มข้อมูลขนาดใหญ่และการวิเคราะห์ · ภาคต้น 2569
นายณัฐภัทร ยืนยง 6621655231 หมู่ 820 (ลำดับที่ 22)

## หัวข้อ
รวมข้อมูลจาก 3 แหล่งเพื่อตอบคำถาม "หลักสูตรไหนของ มก. คนแย่งกันเข้ามากที่สุด ต้องใช้คะแนนเท่าไร
และมีที่นั่ง/คนเข้าเรียนจริงเท่าไร" โดยใช้ Apache Airflow รวมข้อมูลลง PostgreSQL แล้วแสดงบน dashboard (Streamlit)

## แหล่งข้อมูล
| # | แหล่ง | วิธีดึง | ข้อมูลที่ใช้ |
|---|---|---|---|
| 1 | ทปอ. — [mytcas.com/stat](https://www.mytcas.com/stat/) | **web scraping** หน้าสถิติด้วย BeautifulSoup เพื่อหาลิงก์ไฟล์ แล้วดาวน์โหลด Excel | สถิติ TCAS รอบ 3 ปี 2567–2569: จำนวนรับ, ผู้สมัคร, คะแนนต่ำสุด/สูงสุด |
| 2 | สป.อว. — ชุดข้อมูล `univ_std_11_04` นักศึกษาเข้าใหม่ | CKAN API ของ [data.go.th](https://data.go.th/dataset/univ_std_11_04) หาลิงก์ แล้วดาวน์โหลด CSV | จำนวนนักศึกษาใหม่ ป.ตรี ปี 2567 รายหลักสูตร |
| 3 | [admission.ku.ac.th](https://admission.ku.ac.th/) | **web scraping** ตาราง HTML ทุกโครงการ (Dynamic Task Mapping) | จำนวนรับ TCAS70 แยกโครงการ/สาขา |

- ไม่ใช้ Selenium (ใช้ `requests` + `BeautifulSoup`)
- ตรวจ robots.txt แล้ว: mytcas.com `Allow: /`, data.go.th `Allow: /`, data.mhesi.go.th ห้ามเฉพาะ `/api/` (เราดาวน์โหลดไฟล์ ไม่เรียก API ของเว็บนี้), admission.ku.ac.th และ assets.mytcas.com ไม่มี robots.txt
- เป็นข้อมูลสถิติรวม ไม่มีข้อมูลส่วนบุคคล (PDPA) ข้อมูล อว. ที่แยกตามเพศถูกรวมเป็นยอดต่อหลักสูตรก่อนเก็บ

## วิธีรัน
ต้องมี Docker Desktop (หรือ Docker Engine + Compose v2)

```bash
cp .env.example .env          # แก้รหัสผ่านใน .env ได้ตามต้องการ (Linux: ตั้ง AIRFLOW_UID=$(id -u))
docker compose up -d --build  # ครั้งแรก build image ประมาณ 3–5 นาที
```

- Airflow: http://localhost:8080 (ผู้ใช้/รหัสผ่านตาม `AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` ใน `.env`)
  DAG `ku_faculty_popularity` ไม่ถูก pause และรันเองทันทีหนึ่งรอบ (กด ▶ Trigger เพื่อรันซ้ำได้)
- Dashboard: http://localhost:8501 (หน้า "สถานะ Pipeline" อยู่ในเมนูด้านซ้าย)
- PostgreSQL ปลายทาง: `localhost:${TARGET_DB_PORT}` (ค่าเริ่มต้น 5434)

ทดสอบกรณีแหล่งข้อมูลล่ม (ระดับ 3): ใน Airflow ไปที่ Admin → Variables เพิ่ม `kupop_simulate_down` = `mhesi`
(หรือ `tcas`, `kuadm`, คั่นด้วย comma) แล้ว Trigger DAG จะเห็น task ของแหล่งนั้นเป็นสีแดง แต่ DAG ยังรวมข้อมูลจากแหล่งที่เหลือ
และหน้า "สถานะ Pipeline" แสดงรอบนั้นเป็น `partial` (ลบ Variable ออกเพื่อกลับเป็นปกติ)

หยุดระบบ: `docker compose down` (ลบข้อมูลทั้งหมดด้วย `docker compose down -v`)

ไฟล์สรุป: [`docs/22_6621655231_summary.pdf`](docs/22_6621655231_summary.pdf)

## โครงสร้าง
```
dags/ku_faculty_popularity.py   DAG หลัก
dags/kupop/extract.py           ดึงข้อมูลจาก 3 แหล่ง
dags/kupop/transform.py         รวม ตัดซ้ำ ตรวจคุณภาพ สร้างตารางสรุป
dags/kupop/db.py                สร้างตาราง + UPSERT ลง PostgreSQL
web/                            Streamlit dashboard (อ่านจาก PostgreSQL โดยตรง)
docker-compose.yml, Dockerfile, requirements.txt
```

## DAG
```
start → create_tables → [TaskGroup extract: extract_tcas | extract_mhesi | list_kuadm_projects → extract_kuadm_project.expand() → combine_kuadm]
      → merge_and_transform (trigger_rule=all_done: แหล่งไหนล่มก็รวมจากแหล่งที่เหลือ)
      → quality_check (Branch) ─┬→ load_to_postgres ───────────────┐
                                ├→ quarantine_bad_rows → load_to_postgres → build_program_summary
                                └→ alert_insufficient_data ─────────┴→ record_pipeline_run → end
```

- **UPSERT**: `admission_stats` คีย์ `(source, academic_year, source_record_id)` และ `program_summary` คีย์ `(campus, major_key)` รันซ้ำกี่ครั้งจำนวนแถวก็ไม่เพิ่ม
- **ตัดซ้ำข้ามแหล่ง**: หลักสูตรเดียวกันจากทุกแหล่งถูกจับคู่ด้วย วิทยาเขต + ชื่อสาขาที่ normalize แล้ว (`major_key`) ให้เหลือ 1 แถวใน `program_summary`
- **ตรวจคุณภาพ**: ชื่อหลักสูตรว่าง, จำนวนติดลบ, จำนวนรับเป็น 0, คะแนนนอกช่วง 0–100, คะแนนต่ำสุดมากกว่าสูงสุด → แถวที่ไม่ผ่านไปเก็บที่ `dq_quarantine` ถ้าข้อมูลรวมน้อยกว่า 100 แถวจะไม่โหลดทับข้อมูลเดิม
