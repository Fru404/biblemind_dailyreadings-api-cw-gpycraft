# api/index.py

import os
import json
import tempfile
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Query, Header, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from gpycraft.googleSheet.gsheetsdb import gsheetsdb as gb
from gpycraft.app_config import Admin

# -----------------------
# Setup FastAPI app
# -----------------------
app = FastAPI()
origins = [
    "https://biblemind.onrender.com",
    "https://biblemind.netlify.app",
    "https://your-vercel-domain.vercel.app"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# -----------------------
# Secure Google credentials
# -----------------------
creds_json_str = os.getenv("GOOGLE_CREDS_JSON")
if not creds_json_str:
    raise RuntimeError("GOOGLE_CREDS_JSON env var missing")
creds_dict = json.loads(creds_json_str)
tmp_cred_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
with open(tmp_cred_file.name, "w") as f:
    json.dump(creds_dict, f)
credentials_path = tmp_cred_file.name

# -----------------------
# Google Sheets instance
# -----------------------
admin_instance = Admin()
sheet_number = os.getenv("SHEET_NUMBER", "1")
sheet_url = admin_instance.sheet_url(sheet_number=sheet_number)
gsheets_instance = gb(credentials_path, sheet_url, sheet_number=sheet_number)

# -----------------------
# API key security
# -----------------------
API_KEY = os.getenv("BIBLEMIND_API_KEY")
def verify_api_key(x_api_key: str = Header(...)):
    if not API_KEY or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return x_api_key

# -----------------------
# Routes
# -----------------------
@app.get("/daily-readings")
async def get_daily_readings(date: Optional[str] = None, api_key: str = Depends(verify_api_key)):
    raw_data = gsheets_instance.in_json()
    all_data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
    query_date = datetime.utcnow().strftime("%Y-%m-%d") if not date else "-".join(reversed(date.split("-")))
    matched_entry = next((e for e in all_data if e.get("date") and "-".join(reversed(e.get("date").split("/"))) == query_date), None)
    if matched_entry:
        return JSONResponse(content=matched_entry)
    fallback_date = date if date else datetime.utcnow().strftime("%d-%m-%Y")
    return JSONResponse(content={
        "ot": f"No Old Testament reading for {fallback_date}.",
        "gospel": f"No Gospel reading for {fallback_date}.",
        "pope": f"No Pope reflection for {fallback_date}.",
        "date": fallback_date
    })

# -----------------------
# Vercel handler
# -----------------------
handler = Mangum(app)
