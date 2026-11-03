import os
import requests
import pandas as pd
from fastapi import FastAPI, HTTPException
from typing import Optional, Dict, Any

app = FastAPI(
    title="รายงานสถิติจำนวนผู้เข้าชมสวนสัตว์ API",
    description="API ให้บริการข้อมูลรายงานสถิติจำนวนผู้เข้าชมสวนสัตว์ ปีงบประมาณ 2569 ขององค์การสวนสัตว์แห่งประเทศไทย ในพระบรมราชูปถัมภ์ จาก Data.go.th",
    version="1.0.0"
)

# ข้อมูลเมทาดาตาอ้างอิง Data.go.th
DATASET_METADATA = {
    "source": "https://data.go.th",
    "organization": "องค์การสวนสัตว์แห่งประเทศไทย ในพระบรมราชูปถัมภ์",
    "dataset_name": "zoo-visitors2569",
    "resource_id": "0ecc96cf-d914-42a1-b184-dbbd013c3c9c",
    "fiscal_year": 2569
}

CSV_FILE_PATH = "csv-.-..69.csv"
DATA_GO_TH_API_URL = f"https://data.go.th/api/3/action/datastore_search?resource_id={DATASET_METADATA['resource_id']}"


def fetch_data_from_local_csv():
    """ฟังก์ชันอ่านและจัดการข้อมูลจากไฟล์ local CSV"""
    if not os.path.exists(CSV_FILE_PATH):
        return None
    
    # อ่านไฟล์ CSV และคัดกรองคอลัมน์เปล่า
    df = pd.read_csv(CSV_FILE_PATH)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    
    # แปลง NaN เป็น None เพื่อให้ส่งเป็น JSON null ได่อย่างถูกต้อง
    records = df.where(pd.notnull(df), None).to_dict(orient="records")
    
    # Clean whitespace ใน keys และ string values
    cleaned_records = []
    for row in records:
        cleaned_row = {}
        for k, v in row.items():
            key = k.strip() if isinstance(k, str) else k
            val = v.strip() if isinstance(v, str) else v
            cleaned_row[key] = val
        cleaned_records.append(cleaned_row)
        
    return cleaned_records


def fetch_data_from_api():
    """ฟังก์ชันดึงข้อมูลจาก Data.go.th ผ่าน API"""
    try:
        response = requests.get(DATA_GO_TH_API_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                return data["result"]["records"]
    except Exception:
        pass
    return None


@app.get("/")
def read_root():
    return {
        "message": "ยินดีต้อนรับสู่ Zoo Visitors 2569 API",
        "documentation": "/docs",
        "endpoint": "/api/zoo-visitors"
    }


@app.get("/api/zoo-visitors", response_model=Dict[str, Any])
def get_zoo_visitors(zoo_name: Optional[str] = None):
    """
    GET /api/zoo-visitors
    ส่งคืนข้อมูล JSON รายงานสถิติจำนวนผู้เข้าชมสวนสัตว์ ปีงบประมาณ 2569
    """
    # ลำดับการดึงข้อมูล: ดึงจาก API Data.go.th ก่อน หากไม่ได้ให้ใช้อ่านจาก CSV
    records = fetch_data_from_api()
    data_source_used = "Data.go.th CKAN API"

    if not records:
        records = fetch_data_from_local_csv()
        data_source_used = "Local Resource File (csv-.-..69.csv)"

    if not records:
        raise HTTPException(
            status_code=500, 
            detail="ไม่สามารถดึงข้อมูลสถิติผู้เข้าชมสวนสัตว์ได้"
        )

    # กรองข้อมูลตามชื่อสวนสัตว์ (ถ้ามีการระบุ query parameter zoo_name)
    if zoo_name:
        records = [
            r for r in records 
            if r.get("สวนสัตว์") and zoo_name in str(r.get("สวนสัตว์"))
        ]

    return {
        "metadata": {
            "source": DATASET_METADATA["source"],
            "organization": DATASET_METADATA["organization"],
            "dataset": DATASET_METADATA["dataset_name"],
            "resource_id": DATASET_METADATA["resource_id"],
            "fiscal_year": DATASET_METADATA["fiscal_year"],
            "data_source_used": data_source_used,
            "total_records": len(records)
        },
        "data": records
    }
