import io
import re
import cv2
import uuid
import numpy as np
from PIL import Image
import pytesseract
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from database import init_db, save_optimization_record

app = FastAPI()
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAPPING_DICTIONARY = {
    "milk": {"clean_name": "Whole Milk", "category": "dairy"},
    "cheddar chs": {"clean_name": "Cheddar Cheese", "category": "protein"},
    "eggs": {"clean_name": "Free Range Eggs", "category": "protein"},
    "wht brd": {"clean_name": "White Bread", "category": "carb"},
    "pasta": {"clean_name": "Dry Pasta", "category": "carb"},
    "coffee": {"clean_name": "Premium Coffee", "category": "treat"}
}

def preprocess_image_for_ocr(image_bytes: bytes) -> str:
    """Uses OpenCV to optimize contrast and filter image noise for Tesseract."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return ""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    processed_img = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C_16, cv2.THRESH_BINARY, 11, 2
    )
    custom_config = r'--oem 3 --psm 4'
    return pytesseract.image_to_string(processed_img, config=custom_config)

def detect_store_brand(raw_text: str) -> str:
    """Parses text flags to find out which store the receipt came from."""
    text_lower = raw_text.lower()
    if "tesco" in text_lower:
        return "Tesco"
    elif "asda" in text_lower:
        return "Asda"
    elif "sainsbury" in text_lower:
        return "Sainsburys"
    return "Local Store"

@app.post("/api/mobile/scan-receipt")
async def triage_receipt(
    file: UploadFile = File(...),
    budget: float = Form(50.00),
    user_id: str = Form("1"),
    user_tier: str = Form("free")
):
    try:
        # Generate tracking specs
        current_session_id = str(uuid.uuid4())
        rfc3339_timestamp = datetime.now(timezone.utc).isoformat()
        
        file_bytes = await file.read()
        raw_text = preprocess_image_for_ocr(file_bytes)
        
        if not raw_text.strip():
            raise HTTPException(status_code=400, detail="Could not read any text from the receipt photo.")
            
        assigned_store = detect_store_brand(raw_text)
        
        # Core receipt text parsing logic engine loop
        parsed_basket = {}
        raw_lines = raw_text.split("\n")
        junk_keywords = ["total", "subtotal", "balance", "change", "vat", "visa", "card", "thank you", "---"]

        for line in raw_lines:
            clean_line = line.strip().lower()
            if not clean_line or any(junk in clean_line for junk in junk_keywords):
                continue
            
            price_match = re.search(r"£?(\d+\.\d{2})", line)
            if price_match:
                clean_line_text = line.replace("£" + price_match.group(1), "").replace(price_match.group(1), "").strip().lower()
                clean_line_text = re.sub(r'[^a-zA-Z\s]', '', clean_line_text).strip()
                raw_extracted_price = float(price_match.group(1))
                if len(clean_line_text) < 3:
                    continue
            else:
                continue

            final_name = clean_line_text.title()
            final_category = "General Groceries"

            for shorthand, details in MAPPING_DICTIONARY.items():
                if shorthand in clean_line_text:
                    final_name = details["clean_name"]
                    final_category = details.get("category", "Groceries")
                    break

            if final_name in parsed_basket:
                parsed_basket[final_name]["quantity"] += 1
            else:
                parsed_basket[final_name] = {
                    "price": raw_extracted_price,
                    "quantity": 1,
                    "category": final_category
                }

        scanned_total = sum(d["price"] * d["quantity"] for d in parsed_basket.values())
        if scanned_total == 0:
            raise HTTPException(status_code=400, detail="No valid items extracted.")

        cards = []
        for item_name, details in parsed_basket.items():
            cards.append({
                "title": f"{item_name} (x{details['quantity']})",
                "subtitle": f"Extracted price: £{details['price']:.2f} at {assigned_store}",
                "price": round(details['price'] * details['quantity'], 2),
                "store": assigned_store,
                "category": details['category']
            })
        
        try:
            save_optimization_record(
                user_id=int(user_id),
                scanned_total=scanned_total,
                optimized_total=scanned_total,
                triage_applied="No",
                session_id=current_session_id,
                timestamp=rfc3339_timestamp,
                store_name=assigned_store
            )
        except Exception as db_err:
            print(f"⚠️ Database write error trace: {db_err}")

        return {
            "success": True,
            "mobile_user_tier": user_tier,
            "session_meta": {
                "session_id": current_session_id,
                "timestamp": rfc3339_timestamp
            },
            "metrics": {
                "target_budget": budget,
                "scanned_total": scanned_total,
                "optimized_total": scanned_total,
                "store_detected": assigned_store
            },
            "mobile_list_cards": cards
        }
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Core vision runtime fault: {str(err)}")

@app.get("/", response_class=HTMLResponse)
def serve_home_page():
    """Serves the main application front-end container webpage."""
    try:
        with open("index.html", "r", encoding="utf-8") as file:
            return HTMLResponse(content=file.read(), status_code=200)
    except Exception:
        raise HTTPException(status_code=500, detail="Front-end index file missing from directory structure.")