import json
import os
import tempfile
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Query, Header, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from gpycraft.googleSheet.gsheetsdb import gsheetsdb as gb
from gpycraft.fireStore.firestoreupload import firestoreupload
from gpycraft.app_config import Admin


app = FastAPI()

# ================= CORS =================
origins = [
    "https://biblemind.onrender.com",
    "https://biblemind.netlify.app",
    "https://your-project-name.vercel.app",  # 🔁 replace after deploy
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= ENV SETUP =================
os.environ["SHEET_NUMBER"] = os.getenv("SHEET_NUMBER", "1")
sheet_number = os.environ.get("SHEET_NUMBER")

# ================= LOAD GOOGLE CREDS SECURELY =================
creds_json_str = os.getenv("GOOGLE_CREDS_JSON")

if not creds_json_str:
    raise RuntimeError("GOOGLE_CREDS_JSON environment variable not set in Vercel")

creds_dict = json.loads(creds_json_str)

temp_cred_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
with open(temp_cred_file.name, "w") as f:
    json.dump(creds_dict, f)

credentials_path = temp_cred_file.name

# ================= ADMIN CONFIG =================
admin_instance = Admin()
sheet_url = admin_instance.sheet_url(sheet_number=sheet_number)

storage_bucket = os.getenv("FIREBASE_STORAGE_BUCKET", admin_instance.storage_bucket)

# ================= INIT SERVICES =================
gsheets_instance = gb(credentials_path, sheet_url, sheet_number=sheet_number)
fire_instance = firestoreupload(storage_bucket=storage_bucket, credentials_path=credentials_path)

# ================= API KEY SECURITY =================
API_KEY = os.getenv("BIBLEMIND_API_KEY")
API_KEY_NAME = "X-API-Key"

def verify_api_key(x_api_key: str = Header(...)):
    if not API_KEY or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    return x_api_key

# ================= ROUTES =================
@app.get("/daily-readings")
async def get_sheet_data(
    date: Optional[str] = Query(None, description="Date in DD-MM-YYYY format"),
    api_key: str = Depends(verify_api_key)
):
    try:
        raw_data = gsheets_instance.in_json()

        all_data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data

        # Format requested date
        if date:
            try:
                datetime.strptime(date, "%d-%m-%Y")
                day, month, year = date.split("-")
                query_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            except ValueError:
                return JSONResponse(
                    content={"error": "Invalid date format. Use DD-MM-YYYY."},
                    status_code=400
                )
        else:
            query_date = datetime.utcnow().strftime("%Y-%m-%d")

        matched_entry = None

        for entry in all_data:
            entry_date_raw = entry.get("date")
            if not entry_date_raw:
                continue
            try:
                day, month, year = entry_date_raw.split("/")
                entry_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            except Exception:
                continue

            if entry_date == query_date:
                matched_entry = entry
                break

        if matched_entry:
            return JSONResponse(content=matched_entry)

        fallback_date = date if date else datetime.utcnow().strftime("%d-%m-%Y")

        return JSONResponse(content={
            "ot": f"No Old Testament reading available for {fallback_date}.",
            "gospel": f"No Gospel reading available for {fallback_date}.",
            "pope": f"No Pope reflection available for {fallback_date}.",
            "date": fallback_date
        })

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


# ================= VERCEL HANDLER =================
handler = Mangum(app)
