import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import re
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import os

# Налаштування доступу до SAP Karcher
FEED_URL = "https://globalweb-webservice.app.kaercher.com/api/v2/shared/datafeed/2/07c2ca4b/google+uk-UA/uk-UA_google_shopping_feed.xml"
USERNAME = os.environ.get("KARCHER_USER")  # Тепер беремо логін із секретів
PASSWORD = os.environ.get("KARCHER_PASS")  # Тепер беремо пароль із секретів

LOCAL_XML = 'feed.xml'
OUTPUT_JSON = 'monomarket_offers.json'

def download_latest_feed():
    print("📥 Завантажуємо свіжий фід із серверів Karcher...")
    try:
        response = requests.get(FEED_URL, auth=(USERNAME, PASSWORD), verify=False)
        response.raise_for_status() # Перевіряє, чи правильний логін/пароль
        
        with open(LOCAL_XML, 'wb') as f:
            f.write(response.content)
        print("✅ Фід успішно завантажено та оновлено!")
        return True
    except Exception as e:
        print(f"❌ Помилка завантаження фіду: {e}")
        return False

def convert_to_offers_json():
    print(f"🔄 Починаємо генерацію JSON-фіду пропозицій...")
    
    try:
        tree = ET.parse(LOCAL_XML)
        root = tree.getroot()
        
        ns = {'g': 'http://base.google.com/ns/1.0', 'atom': 'http://www.w3.org/2005/Atom'}
        entries = root.findall('.//atom:entry', ns) or root.findall('.//entry')

        product_list = []

        for entry in entries:
            def find_val(tag):
                el = entry.find(f'g:{tag}', ns)
                if el is None: el = entry.find(tag)
                return el.text if el is not None else ""

            price_raw = find_val('price')
            price_match = re.search(r'(\d+)', price_raw.replace(' ', '')) if price_raw else None
            price_val = int(price_match.group(1)) if price_match else 0
            
            avail_str = (find_val('availability') or "").lower()
            is_available = "in stock" in avail_str

            item = {
                "code": find_val('id'),
                "price": price_val,
                "old_price": None,
                "availability": is_available,
                "stock": 10 if is_available else 0,
                "warehouses": None,
                "warranty_type": "manufacturer",
                "warranty_period": 12,
                "max_pay_in_parts": 12,
                "delivery_methods": [
                    {"method": "nova-post:branch", "price": 0},
                    {"method": "nova-post:cargo_branch", "price": 0},
                    {"method": "nova-post:postomat", "price": 0},
                    {"method": "courier:nova-post", "price": 0}
                ],
                "days_to_dispatch": 0,
                "manufacture": None
            }
            product_list.append(item)

        feed_data = {
            "updatedAt": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            "total": len(product_list),
            "data": product_list
        }

        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(feed_data, f, ensure_ascii=False, indent=4)

        print(f"✅ Успішно створено: {OUTPUT_JSON} ({len(product_list)} товарів)")

    except Exception as e:
        print(f"❌ Виникла помилка при обробці: {e}")

if __name__ == "__main__":
    # Спочатку качаємо свіжий фід, а якщо успішно - генеруємо JSON
    if download_latest_feed():
        convert_to_offers_json()