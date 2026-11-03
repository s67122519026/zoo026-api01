import os
import requests
import pandas as pd
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

DATASET_METADATA = {
    "source": "องค์การสวนสัตว์แห่งประเทศไทย ในพระบรมราชูปถัมภ์ (Data.go.th)",
    "dataset_name": "zoo-visitors2569",
    "resource_id": "0ecc96cf-d914-42a1-b184-dbbd013c3c9c",
    "fiscal_year": "2569",
    "url": "https://data.go.th/dataset/zoo-visitors2569"
}

PROVINCE_MAP = {
    "สวนสัตว์เปิดเขาเขียว": "ชลบุรี",
    "สวนสัตว์เชียงใหม่": "เชียงใหม่",
    "สวนสัตว์นครราชสีมา": "นครราชสีมา",
    "สวนสัตว์สงขลา": "สงขลา",
    "สวนสัตว์อุบลราชธานี": "อุบลราชธานี",
    "สวนสัตว์ขอนแก่น": "ขอนแก่น",
    "โครงการคชอาณาจักร จังหวัดสุรินทร์": "สุรินทร์"
}

# กำหนดชื่อไฟล์ CSV ให้อ่านจากโฟลเดอร์ปัจจุบัน
RESOURCE_FILE_PATH = "csv-.-..69.csv"
DATA_GO_TH_API_URL = "https://data.go.th/api/3/action/datastore_search"


def clean_dataframe(df: pd.DataFrame) -> List[Dict[str, Any]]:
    df = df.dropna(how='all', axis=1)

    column_mapping = [
        "item_type", "zoo_name", "fiscal_year",
        "oct_68", "nov_68", "dec_68", "jan_69", "feb_69",
        "mar_69", "apr_69", "may_69", "jun_69", "jul_69", "aug_69", "sep_69"
    ]

    if len(df.columns) >= len(column_mapping):
        df = df.iloc[:, :len(column_mapping)]
        df.columns = column_mapping

    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.strip()

    df["province"] = df["zoo_name"].map(lambda x: PROVINCE_MAP.get(str(x), "ไม่ระบุ"))

    return df.where(pd.notnull(df), None).to_dict(orient="records")


def load_local_csv() -> List[Dict[str, Any]]:
    # ค้นหาไฟล์ CSV ทั้งในโฟลเดอร์ปัจจุบัน และโฟลเดอร์ย่อย
    target_path = RESOURCE_FILE_PATH
    if not os.path.exists(target_path):
        # ค้นหาไฟล์ .csv ทุกไฟล์ที่มีอยู่ใน Repository เผื่อชื่อไฟล์ไม่ตรง
        files = [f for f in os.listdir('.') if f.endswith('.csv')]
        if files:
            target_path = files[0]
        else:
            raise FileNotFoundError(f"ไม่พบไฟล์ CSV บน Server (ค้นหาชื่อ {RESOURCE_FILE_PATH})")

    for enc in ['utf-8-sig', 'utf-8', 'cp874', 'tis-620']:
        try:
            df = pd.read_csv(target_path, encoding=enc)
            return clean_dataframe(df)
        except Exception:
            continue

    df = pd.read_csv(target_path)
    return clean_dataframe(df)


def fetch_live_api(resource_id: str) -> Optional[List[Dict[str, Any]]]:
    try:
        res = requests.get(
            DATA_GO_TH_API_URL,
            params={"resource_id": resource_id, "limit": 1000},
            timeout=4
        )
        if res.status_code == 200:
            data = res.json()
            if data.get("success") and data.get("result", {}).get("records"):
                return clean_dataframe(pd.DataFrame(data["result"]["records"]))
    except Exception:
        pass
    return None


app = FastAPI(
    title="สถิติผู้เข้าชมสวนสัตว์ ปีงบประมาณ 2569 API",
    version="1.0.0",
    docs_url="/docs"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": "Welcome to Zoo Visitors FY2569 API",
        "docs_url": "/docs",
        "api_endpoint": "/api/zoo-visitors"
    }


@app.get("/api/zoo-visitors", summary="GET ข้อมูลสถิติผู้เข้าชมสวนสัตว์")
def get_zoo_visitors(limit: Optional[int] = Query(default=None)):
    records = fetch_live_api(DATASET_METADATA["resource_id"])
    source_mode = "Data.go.th Live API"

    if not records:
        try:
            records = load_local_csv()
            source_mode = f"Local Resource File ({RESOURCE_FILE_PATH})"
        except Exception as e:
            # คืนค่า Error Detail แบบชัดเจนออกมาให้ทราบหากเกิดปัญหา
            raise HTTPException(status_code=500, detail=f"Data Load Error: {str(e)}")

    total = len(records)
    if limit and limit > 0:
        records = records[:limit]

    return {
        "status": "success",
        "metadata": {
            **DATASET_METADATA,
            "data_fetch_mode": source_mode,
            "total_records": total,
            "returned_records": len(records)
        },
        "data": records
    }
