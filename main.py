import os
import requests
import pandas as pd
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# ==============================================================================
# 1. การกำหนดค่า Metadata และแหล่งข้อมูลภาครัฐที่อ้างอิงจริง
# ==============================================================================
DATASET_METADATA = {
    "source": "องค์การสวนสัตว์แห่งประเทศไทย ในพระบรมราชูปถัมภ์ (Data.go.th)",
    "dataset_name": "zoo-visitors2569",
    "resource_id": "0ecc96cf-d914-42a1-b184-dbbd013c3c9c",
    "fiscal_year": "2569",
    "url": "https://data.go.th/dataset/zoo-visitors2569"
}

RESOURCE_FILE_PATH = "csv-.-..69.csv"
DATA_GO_TH_API_URL = "https://data.go.th/api/3/action/datastore_search"

# ==============================================================================
# 2. ฟังก์ชันช่วยจัดการและดึงข้อมูลจริง (Data Loaders & Cleaning)
# ==============================================================================
def clean_and_format_data(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """ทำความสะอาด DataFrame และตั้งชื่อคอลัมน์ให้อ่านง่าย"""
    # ลบคอลัมน์ที่เป็นค่าว่าง NaN ทั้งหมด
    df = df.dropna(how='all', axis=1)

    # ตั้งชื่อคอลัมน์มาตรฐาน
    column_mapping = [
        "item_type", "zoo_name", "fiscal_year",
        "oct_68", "nov_68", "dec_68", "jan_69", "feb_69",
        "mar_69", "apr_69", "may_69", "jun_69", "jul_69", "aug_69", "sep_69"
    ]

    if len(df.columns) >= len(column_mapping):
        df = df.iloc[:, :len(column_mapping)]
        df.columns = column_mapping

    # ตัดช่องว่างส่วนเกินของข้อความออก
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.strip()

    # แปลงข้อมูลเป็น List of Dictionaries
    return df.where(pd.notnull(df), None).to_dict(orient="records")


def load_from_local_csv() -> List[Dict[str, Any]]:
    """อ่านข้อมูลจริงจากไฟล์ CSV ที่ดาวน์โหลดมา"""
    if not os.path.exists(RESOURCE_FILE_PATH):
        raise FileNotFoundError(f"ไม่พบไฟล์ทรัพยากร {RESOURCE_FILE_PATH}")
    df = pd.read_csv(RESOURCE_FILE_PATH)
    return clean_and_format_data(df)


def fetch_from_datagoth_api(resource_id: str) -> Optional[List[Dict[str, Any]]]:
    """ดึงข้อมูลตัวเลขจริงโดยตรงจาก Data.go.th API"""
    try:
        response = requests.get(
            DATA_GO_TH_API_URL,
            params={"resource_id": resource_id, "limit": 1000},
            timeout=5
        )
        if response.status_code == 200:
            res_json = response.json()
            if res_json.get("success") and res_json.get("result", {}).get("records"):
                df = pd.DataFrame(res_json["result"]["records"])
                return clean_and_format_data(df)
    except Exception:
        pass
    return None

# ==============================================================================
# 3. สร้างและตั้งค่า FastAPI Application
# ==============================================================================
app = FastAPI(
    title="สถิติผู้เข้าชมสวนสัตว์ ปีงบประมาณ 2569 API",
    description="RESTful API ดึงข้อมูลจริงรายงานสถิติจำนวนผู้เข้าชมสวนสัตว์ จาก Data.go.th",
    version="1.0.0",
    docs_url="/docs",      # Swagger UI Endpoint
    redoc_url="/redoc"
)

# รองรับ CORS สำหรับการเรียกใช้งานจากต่าง Domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# 4. API Endpoints
# ==============================================================================
@app.get("/", summary="Root Endpoint")
def root():
    return {
        "message": "ยินดีต้อนรับสู่ API รายงานสถิติผู้เข้าชมสวนสัตว์ ปีงบประมาณ 2569",
        "swagger_docs": "/docs",
        "api_endpoint": "/api/zoo-visitors"
    }


@app.get("/api/zoo-visitors", summary="GET ข้อมูลสถิติผู้เข้าชมสวนสัตว์")
def get_zoo_visitors(
    limit: Optional[int] = Query(default=None, description="จำกัดจำนวนรายการข้อมูล")
):
    """
    ดึงข้อมูลสถิติจำนวนผู้เข้าชมสวนสัตว์ ปีงบประมาณ 2569 
    พร้อมแสดงอ้างอิงแหล่งข้อมูลภาครัฐ Data.go.th และคืนค่า JSON Response
    """
    # 1. พยายามดึงข้อมูลสดผ่าน Live API ของ Data.go.th ก่อน
    records = fetch_from_datagoth_api(DATASET_METADATA["resource_id"])
    data_source_mode = "Data.go.th Live API"

    # 2. หากดึง API ไม่สำเร็จ ให้สลับอ่านจากไฟล์ CSV ทรัพยากรจริงในเครื่อง (Fallback)
    if not records:
        try:
            records = load_from_local_csv()
            data_source_mode = f"Local Resource File ({RESOURCE_FILE_PATH})"
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการอ่านข้อมูล: {str(e)}")

    total_records = len(records)
    
    if limit and limit > 0:
        records = records[:limit]

    # คืนค่า JSON Response ตามโครงสร้างที่กำหนด
    return {
        "status": "success",
        "metadata": {
            **DATASET_METADATA,
            "data_fetch_mode": data_source_mode,
            "total_records": total_records,
            "returned_records": len(records)
        },
        "data": records
    }

# ==============================================================================
# 5. [ส่วนเสริม - Optional] การสาธิตการเชื่อมต่อ MySQL ด้วย Python/FastAPI
# ==============================================================================
@app.get("/api/demo-mysql-connect", summary="[Optional] ตัวอย่างการเชื่อมต่อ MySQL", tags=["Optional MySQL"])
def demo_mysql_connection():
    """
    ฟังก์ชันสาธิตการเชื่อมต่อ MySQL (ใช้อุปกรณ์เสริม กรณีมี DB ที่ผู้สอนจัดสรรให้)
    """
    import pymysql
    
    # อ่านการตั้งค่าจาก Environment Variables
    DB_HOST = os.getenv("MYSQL_HOST", "localhost")
    DB_USER = os.getenv("MYSQL_USER", "root")
    DB_PASSWORD = os.getenv("MYSQL_PASSWORD", "123456")
    DB_NAME = os.getenv("MYSQL_DB", "zoo_db")
    DB_PORT = int(os.getenv("MYSQL_PORT", 3306))

    try:
        connection = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
            cursorclass=pymysql.cursors.DictCursor
        )
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT VERSION() AS mysql_version;")
                result = cursor.fetchone()
                
        return {
            "status": "success",
            "message": "เชื่อมต่อฐานข้อมูล MySQL สำเร็จ!",
            "mysql_version": result.get("mysql_version")
        }
    except Exception as e:
        return {
            "status": "connection_failed",
            "message": f"ไม่สามารถเชื่อมต่อ MySQL ได้ (สามารถข้ามได้): {str(e)}"
        }

# ==============================================================================
# 6. สั่งรัน Server ด้วย Uvicorn เมื่อรันไฟล์โดยตรง
# ==============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)