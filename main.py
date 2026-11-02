import os
import requests
import pandas as pd
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# Metadata อ้างอิงแหล่งข้อมูลภาครัฐ Data.go.th
DATASET_METADATA = {
    "source": "องค์การสวนสัตว์แห่งประเทศไทย ในพระบรมราชูปถัมภ์ (Data.go.th)",
    "dataset_name": "zoo-visitors2569",
    "resource_id": "0ecc96cf-d914-42a1-b184-dbbd013c3c9c",
    "fiscal_year": "2569",
    "url": "https://data.go.th/dataset/zoo-visitors2569"
}

RESOURCE_FILE_PATH = "csv-.-..69.csv"
DATA_GO_TH_API_URL = "https://data.go.th/api/3/action/datastore_search"


def clean_dataframe(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """ทำความสะอาด DataFrame ตัดคอลัมน์ว่าง และตั้งชื่อฟิลด์มาตรฐาน"""
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

    return df.where(pd.notnull(df), None).to_dict(orient="records")


def load_local_csv() -> List[Dict[str, Any]]:
    """อ่านข้อมูลจริงจากไฟล์ CSV ทรัพยากรในเครื่อง พร้อมรองรับ Encoding ภาษาไทย"""
    if not os.path.exists(RESOURCE_FILE_PATH):
        raise FileNotFoundError(f"ไม่พบไฟล์ทรัพยากร {RESOURCE_FILE_PATH}")
    
    # วนลูปทดสอบ encoding ภาษาไทยเพื่อป้องกันตัวอักษรกลายเป็น ????
    for enc in ['cp874', 'utf-8-sig', 'tis-620', 'utf-8']:
        try:
            df = pd.read_csv(RESOURCE_FILE_PATH, encoding=enc)
            if df.columns[0] and '?' not in str(df.columns[0]):
                return clean_dataframe(df)
        except Exception:
            continue

    df = pd.read_csv(RESOURCE_FILE_PATH)
    return clean_dataframe(df)


def fetch_live_api(resource_id: str) -> Optional[List[Dict[str, Any]]]:
    """ดึงข้อมูลตัวเลขจริงโดยตรงจาก Data.go.th CKAN API"""
    try:
        response = requests.get(
            DATA_GO_TH_API_URL,
            params={"resource_id": resource_id, "limit": 1000},
            timeout=4
        )
        if response.status_code == 200:
            res = response.json()
            if res.get("success") and res.get("result", {}).get("records"):
                return clean_dataframe(pd.DataFrame(res["result"]["records"]))
    except Exception:
        pass
    return None


app = FastAPI(
    title="สถิติผู้เข้าชมสวนสัตว์ ปีงบประมาณ 2569 API",
    description="RESTful API ข้อมูลสถิติจำนวนผู้เข้าชมสวนสัตว์ อ้างอิง Data.go.th",
    version="1.0.0",
    docs_url="/docs"
)

# รองรับ CORS เพื่อให้เรียกใช้งานจากภายนอกได้
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", summary="Root Endpoint")
def root():
    return {
        "message": "Welcome to Zoo Visitors FY2569 API",
        "docs_url": "/docs",
        "api_endpoint": "/api/zoo-visitors"
    }


@app.get("/api/zoo-visitors", summary="GET ข้อมูลสถิติผู้เข้าชมสวนสัตว์")
def get_zoo_visitors(
    limit: Optional[int] = Query(default=None, description="จำกัดจำนวนรายการที่ต้องการแสดง")
):
    # 1. พยายามดึงผ่าน Live API ก่อน
    records = fetch_live_api(DATASET_METADATA["resource_id"])
    source_mode = "Data.go.th Live API"

    # 2. หากดึง API ไม่สำเร็จ ให้ fallback อ่านไฟล์ CSV ทรัพยากรจริงในเครื่อง
    if not records:
        try:
            records = load_local_csv()
            source_mode = f"Local Resource File ({RESOURCE_FILE_PATH})"
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    total_records = len(records)
    if limit and limit > 0:
        records = records[:limit]

    return {
        "status": "success",
        "metadata": {
            **DATASET_METADATA,
            "data_fetch_mode": source_mode,
            "total_records": total_records,
            "returned_records": len(records)
        },
        "data": records
    }


@app.get("/api/demo-mysql-connect", summary="[Optional] ตัวอย่างการเชื่อมต่อ MySQL", tags=["Optional MySQL"])
def demo_mysql():
    import pymysql
    try:
        conn = pymysql.connect(
            host=os.getenv("MYSQL_HOST", "localhost"),
            user=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD", "123456"),
            database=os.getenv("MYSQL_DB", "zoo_db"),
            port=int(os.getenv("MYSQL_PORT", 3306)),
            cursorclass=pymysql.cursors.DictCursor
        )
        with conn.cursor() as cursor:
            cursor.execute("SELECT VERSION() AS version;")
            res = cursor.fetchone()
        return {"status": "success", "mysql_version": res.get("version")}
    except Exception as e:
        return {"status": "failed", "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
