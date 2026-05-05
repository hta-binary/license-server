import os
import json
import datetime as dt
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import gspread
import logging

app = FastAPI()

# Get your sheet ID from environment variable or use default
SHEET_ID = os.environ.get("SHEET_ID", "1AIFgaeSgLAwfC8796LnqZQNf7gtNbnfYl0OIaMguWag") 

class LicenseRequest(BaseModel):
    key: str
    sys_id: str

def get_google_sheet():
    # Read credentials from environment variable (set this in Render)
    cred_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not cred_json:
        raise ValueError("GOOGLE_CREDENTIALS_JSON environment variable not set. Please add it to your Render Environment Variables.")
    
    try:
        credentials = json.loads(cred_json)
    except json.JSONDecodeError:
        raise ValueError("GOOGLE_CREDENTIALS_JSON is not a valid JSON string.")

    gc = gspread.service_account_from_dict(credentials)
    sheet = gc.open_by_key(SHEET_ID).sheet1
    return sheet

@app.post("/validate")
def validate_license(req: LicenseRequest):
    try:
        sheet = get_google_sheet()
        records = sheet.get_all_records()
        row_idx = 2
        
        for row in records:
            if str(row.get("License Key", "")) == req.key:
                # 1. Check Status
                if str(row.get("Status", "")).lower() != "active":
                    return {"valid": False, "message": "License is inactive or banned."}
                    
                # 2. Check Expiry
                expiry_str = str(row.get("Expiry Date", ""))
                try:
                    expiry_date = dt.datetime.strptime(expiry_str, "%Y-%m-%d").date()
                    if dt.date.today() > expiry_date:
                        return {"valid": False, "message": "License expired!"}
                except Exception:
                    pass
                    
                # 3. Check Device Lock
                devices = str(row.get("Device ID", ""))
                try:
                    max_devices = int(row.get("Max Devices") or 1)
                except ValueError:
                    max_devices = 1
                    
                try:
                    active_devices = int(row.get("Active Devices") or 0)
                except ValueError:
                    active_devices = 0
                
                expiry_display = expiry_str if expiry_str else "Lifetime"
                
                # If device already registered
                if req.sys_id in devices:
                    return {"valid": True, "expiry": expiry_display}
                    
                # If new device, check limits
                if active_devices >= max_devices:
                    return {"valid": False, "message": f"Max devices reached ({active_devices}/{max_devices})."}
                    
                # Register new device
                new_devices = f"{devices},{req.sys_id}" if devices else req.sys_id
                
                headers = sheet.row_values(1)
                try:
                    dev_col = headers.index("Device ID") + 1
                    act_col = headers.index("Active Devices") + 1
                    sheet.update_cell(row_idx, dev_col, new_devices)
                    sheet.update_cell(row_idx, act_col, active_devices + 1)
                except ValueError:
                    pass # Ignore if columns missing
                
                return {"valid": True, "expiry": expiry_display}
                
            row_idx += 1
            
        return {"valid": False, "message": "Invalid License Key!"}
        
    except Exception as e:
        logging.error(f"License server error: {e}")
        # We return a 500 error to signal the bot that the server had an issue
        raise HTTPException(status_code=500, detail="Internal server error validating license.")
