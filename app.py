from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn
import re
import json
import os
from database import init_db, save_optimization_record, get_history_logs, verify_user_login

app = FastAPI()
init_db()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows any mobile device to connect
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simulated active login session state (Defaults to premium_user for testing)
CURRENT_SESSION = {"id": 2, "username": "premium_user", "tier": "premium"}

MAPPING_DICTIONARY = {
    "milk": {"clean_name": "Whole Milk", "category": "dairy"},
    "cheddar chs": {"clean_name": "Cheddar Cheese", "category": "protein"},
    "eggs": {"clean_name": "Free Range Eggs", "category": "protein"},
    "wht brd": {"clean_name": "White Bread", "category": "carb"},
    "pasta": {"clean_name": "Dry Pasta", "category": "carb"},
    "coffee": {"clean_name": "Premium Coffee", "category": "treat"},
    "slmn fllts": {"clean_name": "Fresh Salmon Fillets", "category": "protein"},
    "choc digestives": {"clean_name": "Chocolate Digestives", "category": "treat"}
}

def fetch_live_prices(shorthand_key: str) -> dict:
    """
    Looks up real-time competitive pricing matrices across supermarkets
    from our local grocery price repository.
    """
    try:
        file_path = os.path.join(os.path.dirname(__file__), "grocery_prices.json")
        with open(file_path, "r", encoding="utf-8") as f:
            full_market_data = json.load(f)
            
        if shorthand_key in full_market_data:
            return full_market_data[shorthand_key]
            
    except Exception as e:
        # Actually print 'e' so Python knows it's actively used
        print(f"Database read error: {e}")
        
    return {"Tesco": 2.50, "Asda": 2.50, "Sainsburys": 2.50}

@app.get("/", response_class=HTMLResponse)
def home():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/switch-user")
def switch_user(data: dict):
    """Changes the current simulation user profile between free and premium accounts."""
    global CURRENT_SESSION
    username = data.get("username")
    password = "password123" if username == "free_user" else "secure456"
    
    user = verify_user_login(username, password)
    if user:
        CURRENT_SESSION = user
        return {"status": "success", "user": CURRENT_SESSION}
    raise HTTPException(status_code=401, detail="Authentication failed")

@app.get("/get-current-user")
def get_current_user():
    return CURRENT_SESSION

@app.post("/api/mobile/scan-receipt")
def triage_receipt(receipt_data: dict):
    raw_text = receipt_data.get("text", "")
    budget_limit = float(receipt_data.get("budget", 50.00))

    parsed_basket = {}

    # 1. Break the camera scan text into individual rows
    raw_lines = raw_text.strip().split("\n")
    lines = []

    # 2. Define our receipt junk metadata filter words
    junk_keywords = ["total", "subtotal", "balance", "change", "vat", "visa", "card", "shop", "thank you", "items", "---"]

    # 3. Filter the lines aggressively before evaluating products
    for line in raw_lines:
        clean_line = line.strip().lower()
        if not clean_line or any(junk in clean_line for junk in junk_keywords):
            continue
        lines.append(line)

    # 4. Run your evaluation loops on only the clean lines
    for line in lines:
        # --- PARSING LAYER ---
        price_match = re.search(r"£?(\d+\.\d{2})", line)
        
        if price_match:
            clean_line_text = line.replace("*", "").replace("£" + price_match.group(1), "").strip().lower()
            clean_line_text = re.sub(r'\s+[v]$', '', clean_line_text).strip()
            raw_extracted_price = float(price_match.group(1))
        else:
            # Fallback if the user just types plain words without a price attached
            clean_line_text = line.strip().lower()
            raw_extracted_price = 2.50 # Default baseline dummy price

        # Default assumptions using the text extracted straight from the receipt line
    final_name = clean_line_text.title()
    final_category = "General Groceries"
    
    # Use the lowercase text as a fallback shorthand lookup key
    shorthand_key = clean_line_text.strip().lower()

    # Try to find a precise name/category override in your custom dictionary
    matched_predefined = False
    for shorthand, details in MAPPING_DICTIONARY.items():
        if shorthand in clean_line_text:
            final_name = details["clean_name"]
            final_category = details.get("category", "Groceries")
            shorthand_key = shorthand
            matched_predefined = True
            break
            
    # If it's a completely new item, clean up stray characters for the card display
    if not matched_predefined:
        # Removes numbers or trailing single letters left over from receipt text lines
        final_name = re.sub(r'\d+', '', final_name).replace('.', '').strip()

        # Move the basket assignment out of the price_match block so it runs for ALL items
        if final_name in parsed_basket:
            parsed_basket[final_name]["quantity"] += 1
        else:
            pack_multiplier = 1
            pack_match = re.search(r"(\d+)\s*pk", clean_line_text)
            if pack_match:
                pack_multiplier = int(pack_match.group(1))

            if receipt_data.get("user_tier") == "premium":
                market_data = fetch_live_prices(shorthand_key)
                temp_matrix = {
                    "Sainsburys": float(market_data.get("Sainsburys", 2.50)),
                    "Tesco": float(market_data.get("Tesco", 2.40)),
                    "Asda": float(market_data.get("Asda", 2.20))
                }
                best_store = min(temp_matrix, key=temp_matrix.get)
                best_price = temp_matrix[best_store]
            else:
                best_store = "TESCO"
                best_price = raw_extracted_price
                if shorthand_key == "milk": best_price = 1.65
                if shorthand_key == "bread": best_price = 1.20
                if shorthand_key == "pasta": best_price = 1.50

            parsed_basket[final_name] = {
                "price": best_price,
                "quantity": 1,
                "pack_units": pack_multiplier,
                "category": final_category,
                "assigned_store": best_store
            }

# === PASTE THE NEW FINALIZE LAYER RIGHT HERE ===
    cards = []
    for item_name, details in parsed_basket.items():
        cards.append({
            "title": item_name,
            "subtitle": f"Best price: £{details['price']:.2f} at {details['assigned_store']}",
            "price": details['price'],
            "store": details['assigned_store'],
            "category": details['category']
        })

    # --- STEP 3: TRIAGE BUDGET ENGINE ---
    scanned_total = sum(d["price"] * d["quantity"] for d in parsed_basket.values())
    optimized_total = scanned_total  # Baseline tracker
    triage_was_applied = "No"

    # If the user is over budget, trigger the automated triage alerts
    if scanned_total > budget_limit:
        triage_was_applied = "Yes"
        
        # Loop through your basket to attach custom UI budget warn-flags
        for item_name, details in parsed_basket.items():
            if details["price"] > 2.00:
                details["category"] = details.get("category", "other") + " ⚠️ (Budget Alert)"

    # --- NEW STEP 4: DATABASE PERSISTENCE ---
    try:
        # Pull the active user ID from your session state
        user_id = CURRENT_SESSION.get("id", 1)
        
        # Save this basket run to your supershopper.db database log
        save_optimization_record(
            user_id=user_id,
            scanned_total=scanned_total,
            optimized_total=optimized_total,
            triage_applied=triage_was_applied
        )
        print("📊 Basket successfully archived to database log!")
    except Exception as db_err:
        print(f"⚠️ Database archiving failed: {db_err}")

    # Now return the clean metrics payload
    return {
        "success": True,
        "mobile_user_tier": receipt_data.get("user_tier", "free"),
        "metrics": {
            "target_budget": budget_limit,
            "scanned_total": scanned_total,
            "optimized_total": optimized_total,
            "savings_found": round(max(0.0, scanned_total - optimized_total), 2),
            "triage_applied": triage_was_applied
        },
        "mobile_list_cards": cards
    }

    # --- CORE CALCULATION & BUDGET TRIAGE PIPELINE ---
    def get_total():
        return sum(d["price"] * d["quantity"] for d in parsed_basket.values())

    initial_total = get_total()
    triage_triggered = False

    if initial_total > budget_limit:
        triage_triggered = True
        for name, details in parsed_basket.items():
            if details["category"] == "treat":
                details["quantity"] = 0

        while get_total() > budget_limit:
            reduced_any = False
            for name, details in parsed_basket.items():
                if details["category"] == "carb" and details["quantity"] > 1:
                    details["quantity"] -= 1
                    reduced_any = True
                    if get_total() <= budget_limit: 
                        break
            if not reduced_any:
                break

    # --- FORMAT OUTPUT DISPLAY ARRAY ---
    final_items = []
    for name, details in parsed_basket.items():
        if details["quantity"] > 0:
            pack_units = details.get("pack_units", 1)
            pack_label = f" ({pack_units}x Pack)" if pack_units > 1 else ""
            
            final_items.append({
                "item_name": f"{name}{pack_label}",
                "quantity": details["quantity"],
                "unit_price": details["price"],
                "subtotal": round(details["price"] * details["quantity"], 2),
                "assigned_store": details["assigned_store"]
            })

    # --- AUDIT PERSISTENCE LAYER ---
    save_optimization_record(
        user_id=CURRENT_SESSION["id"],
        budget=budget_limit,
        initial=round(initial_total, 2),
        final=round(get_total(), 2),
        triaged=triage_triggered
    )

    return {
        "budget_limit": budget_limit,
        "initial_total": round(initial_total, 2),
        "final_total": round(get_total(), 2),
        "triage_applied": triage_triggered,
        "optimized_basket": final_items
    }

    def get_total():
        return sum(d["price"] * d["quantity"] for d in parsed_basket.values())

    initial_total = get_total()
    triage_triggered = False

    if initial_total > budget_limit:
        triage_triggered = True
        for name, details in parsed_basket.items():
            if details["category"] == "treat":
                details["quantity"] = 0
                
        while get_total() > budget_limit:
            reduced_any = False
            for name, details in parsed_basket.items():
                if details["category"] == "carb" and details["quantity"] > 1:
                    details["quantity"] -= 1
                    reduced_any = True
                    if get_total() <= budget_limit: break
            if not reduced_any:
                break

    final_items = []
    for name, details in parsed_basket.items():
        if details["quantity"] > 0:
            pack_units = details.get("pack_units", 1)
            pack_label = f" ({pack_units}x Pack)" if pack_units > 1 else ""
            
            final_items.append({
                "item_name": f"{name}{pack_label}",
                "quantity": details["quantity"],
                "unit_price": details["price"],
                "subtotal": round(details["price"] * details["quantity"], 2),
                "assigned_store": details["assigned_store"]
            })

    # Save to SQLite attached to the active user profile identification
    save_optimization_record(
        user_id=CURRENT_SESSION["id"],
        budget=budget_limit,
        initial=round(initial_total, 2),
        final=round(get_total(), 2),
        triaged=triage_triggered
    )

    return {
        "budget_limit": budget_limit,
        "initial_total": round(initial_total, 2),
        "final_total": round(get_total(), 2),
        "triage_applied": triage_triggered,
        "optimized_basket": final_items
    }

@app.get("/get-history")
def get_history():
    """Fetches history records filtering specifically by the active session profile identification."""
    raw_logs = get_history_logs(user_id=CURRENT_SESSION["id"])
    formatted_logs = []
    for row in raw_logs:
        formatted_logs.append({
            "id": row[0],
            "timestamp": row[1],
            "budget": row[2],
            "initial": row[3],
            "final": row[4],
            "triaged": "⚠️ YES" if row[5] == 1 else "✅ NO"
        })
    return formatted_logs

# --- MOBILE APP INTEGRATION ENDPOINT (API GATEWAY) ---
@app.post("/api/mobile/scan-receipt")
def mobile_api_scan(payload: dict):
    """
    Receives incoming text payloads directly from a mobile camera scan stream,
    extracts user attributes dynamically from the request, runs the matrix pipeline,
    and returns native-friendly JSON data.
    """
    raw_text = payload.get("text", "")
    budget_limit = payload.get("budget", 50.00)
    
    # DYNAMIC AUTH: Read user details from the phone's request instead of a global variable
    mobile_user_id = payload.get("user_id", 1)  # Defaults to user 1 if not provided
    mobile_tier = payload.get("user_tier", "free")  # Defaults to "free" tier
    
    # Temporarily mock the session context just for the duration of this specific function run
    global CURRENT_SESSION
    original_session = CURRENT_SESSION.copy()
    CURRENT_SESSION = {"id": mobile_user_id, "username": f"mobile_user_{mobile_user_id}", "tier": mobile_tier}
    
    try:
        receipt_data = {"text": raw_text, "budget": budget_limit}
        result = triage_receipt(receipt_data)
        savings = round(result["initial_total"] - result["final_total"], 2)
        
        return {
            "success": True,
            "mobile_user_tier": mobile_tier,
            "metrics": {
                "target_budget": result["budget_limit"],
                "scanned_total": result["initial_total"],
                "optimized_total": result["final_total"],
                "savings_found": savings,
                "triage_applied": result["triage_applied"]
            },
            "mobile_list_cards": result["optimized_basket"]
        }
    finally:
        # Restore the default session state so the web dashboard doesn't break
        CURRENT_SESSION = original_session

        from fastapi.responses import HTMLResponse
import os

@app.get("/", response_class=HTMLResponse)
def read_root():
    # Looks for your index.html file in the same directory
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Supper-Shopper API is running!</h1><p>Visit /docs for the interactive portal.</p>"

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)