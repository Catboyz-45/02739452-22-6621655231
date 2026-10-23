FROM apache/airflow:2.10.4-python3.12

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir "apache-airflow==2.10.4" -r /requirements.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.4/constraints-3.12.txt"
