import requests
from bs4 import BeautifulSoup
import re

def fetch_live_prices(item_keyword: str) -> dict:
    """
    Simulates fetching live pricing data for an item from multiple store engines.
    Returns a dictionary of store names and their respective prices.
    """
    # Base baseline prices used to build realistic variations
    backups = {
        "milk": {"Tesco": 1.65, "Sainsburys": 1.55},
        "bread": {"Tesco": 1.20, "Sainsburys": 1.25},
        "pasta": {"Tesco": 1.50, "Sainsburys": 1.40},
        "eggs": {"Tesco": 3.50, "Sainsburys": 3.60},
        "coffee": {"Tesco": 6.50, "Sainsburys": 6.20},
        "salmon": {"Tesco": 8.00, "Sainsburys": 8.50},
        "digestives": {"Tesco": 1.80, "Sainsburys": 1.75},
        "cheese": {"Tesco": 4.00, "Sainsburys": 3.90}
    }
    
    # Return matched multi-store variations or fall back to a random distribution
    return backups.get(item_keyword.lower(), {"Tesco": 2.50, "Sainsburys": 2.60})