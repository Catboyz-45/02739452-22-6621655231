import os

import pandas as pd
import psycopg2
import streamlit as st


def _connect():
    return psycopg2.connect(
        host=os.environ.get("TARGET_DB_HOST", "localhost"),
        port=int(os.environ.get("TARGET_DB_PORT", "5434")),
        dbname=os.environ.get("TARGET_DB_NAME", "kupop"),
        user=os.environ.get("TARGET_DB_USER", "kupop"),
        password=os.environ.get("TARGET_DB_PASSWORD", ""),
    )


@st.cache_data(ttl=30, show_spinner=False)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    """อ่านข้อมูลจาก PostgreSQL โดยตรงทุกครั้ง (cache 30 วินาที)"""
    with _connect() as conn:
        return pd.read_sql_query(sql, conn, params=params or None)


def safe_query(sql: str, params: tuple = ()):
    try:
        return query(sql, params), None
    except Exception as exc:  # ตารางยังไม่ถูกสร้าง หรือ DB ยังไม่พร้อม
        return pd.DataFrame(), str(exc)
