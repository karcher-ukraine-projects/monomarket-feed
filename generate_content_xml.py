import xml.etree.ElementTree as ET
import re
import requests
import urllib3
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FEED_URL = "https://globalweb-webservice.app.kaercher.com/api/v2/shared/datafeed/2/07c2ca4b/google+uk-UA/uk-UA_google_shopping_feed.xml"
USERNAME = os.environ.get("KARCHER_USER")
PASSWORD = os.environ.get("KARCHER_PASS")
LOCAL_XML = 'feed.xml'

def download_latest_feed():
    print("📥 Завантажуємо свіжий фід для XML контенту...")
    try:
        response = requests.get(FEED_URL, auth=(USERNAME, PASSWORD), verify=False)
        response.raise_for_status()
        with open(LOCAL_XML, 'wb') as f:
            f.write(response.content)
        print("✅ Фід завантажено!")
        return True
    except Exception as e:
        print(f"❌ Помилка завантаження: {e}")
        return False

def clean_cdata(text):
    if not text: return ""
    return text.replace("<![CDATA[", "").replace("]]>", "").strip()

def format_description_html(raw_text):
    text = clean_cdata(raw_text)
    parts = re.split(r'\. (?=[A-ZА-ЯІ])', text)
    if not parts: return ""
    
    html = f"<h5>Опис</h5>\n<p>{parts[0].strip()}.</p>\n<br>\n"
    if len(parts) > 1:
        html += "<h5>Характеристики та особливості</h5>\n<ul>\n"
        for part in parts[1:]:
            content = part.strip().rstrip('.')
            if content:
                html += f"  <li>{content}</li>\n"
        html += "</ul>"
    return html

def parse_dimensions_and_weight(text):
    """Функція для вилучення габаритів та ваги з тексту опису"""
    weight, length, width, height = "", "", "", ""
    if not text: return weight, length, width, height
    
    # Шукаємо вагу (напр. "Вага: 650 г" або "Вага: 1.5 кг")
    w_match = re.search(r'Вага.*?([\d\.,]+)\s*(кг|г)', text, re.IGNORECASE)
    if w_match:
        try:
            val = float(w_match.group(1).replace(',', '.'))
            if w_match.group(2).lower() == 'г':
                val = val / 1000 # Переводимо в кг для Мономаркету
            weight = str(round(val, 3))
        except: pass
        
    # Шукаємо розміри (напр. "Розмір: 46 х 33 х 21 см")
    d_match = re.search(r'(?:Розмір|Габарити).*?([\d\.,]+)\s*[xхХ*]\s*([\d\.,]+)\s*[xхХ*]\s*([\d\.,]+)\s*(см|мм|м)', text, re.IGNORECASE)
    if d_match:
        try:
            v1 = float(d_match.group(1).replace(',', '.'))
            v2 = float(d_match.group(2).replace(',', '.'))
            v3 = float(d_match.group(3).replace(',', '.'))
            unit = d_match.group(4).lower()
            
            # Переводимо все в сантиметри
            if unit == 'мм':
                v1, v2, v3 = v1/10, v2/10, v3/10
            elif unit == 'м':
                v1, v2, v3 = v1*100, v2*100, v3*100
                
            length = str(round(v1, 2))
            width = str(round(v2, 2))
            height = str(round(v3, 2))
        except: pass
        
    return weight, length, width, height

def generate_mono_content_xml():
    print("📦 Формуємо ідеальний контентний фід...")
    if not os.path.exists(LOCAL_XML):
        print("❌ Файл feed.xml не знайдено!")
        return

    tree = ET.parse(LOCAL_XML)
    root = tree.getroot()
    ns = {'g': 'http://base.google.com/ns/1.0', 'atom': 'http://www.w3.org/2005/Atom'}
    entries = root.findall('.//atom:entry', ns) or root.findall('.//entry')

    new_root = ET.Element("Market")
    offers = ET.SubElement(new_root, "offers")
    descriptions_map = {}

    for entry in entries:
        def find_v(tag):
            el = entry.find(f'g:{tag}', ns)
            if el is None: el = entry.find(tag, ns)
            if el is None: el = entry.find(tag)
            return el.text if el is not None else ""

        avail = (find_v('availability') or "").lower()
        if "in stock" not in avail:
            continue

        offer = ET.SubElement(offers, "offer")
        item_id = find_v('id')
        ET.SubElement(offer, "id").text = item_id
        ET.SubElement(offer, "code").text = item_id
        ET.SubElement(offer, "vendor_code").text = item_id
        
        # ВИПРАВЛЕННЯ ДУБЛІКАТІВ: Додаємо артикул у назву
        title = clean_cdata(find_v('title'))
        if item_id not in title:
            title = f"{title} ({item_id})"
        ET.SubElement(offer, "title").text = title
        
        barcode = find_v('gtin')
        ET.SubElement(offer, "barcode").text = barcode if barcode else item_id
        
        full_cat = find_v('custom_label_0') or find_v('product_type')
        category = full_cat.split('>')[-1].strip() if '>' in full_cat else full_cat
        ET.SubElement(offer, "category").text = category if category else "Kärcher"
        
        ET.SubElement(offer, "brand").text = find_v('brand') or "Kärcher"
        ET.SubElement(offer, "availability").text = "в наявності"
        
        # ВИПРАВЛЕННЯ ВГХ: витягуємо габарити і створюємо правильні теги
        desc_text = find_v('description')
        w_val, l_val, w2_val, h_val = parse_dimensions_and_weight(desc_text)
        
        if w_val: ET.SubElement(offer, "weight").text = w_val
        if h_val: ET.SubElement(offer, "height").text = h_val
        if w2_val: ET.SubElement(offer, "width").text = w2_val
        if l_val: ET.SubElement(offer, "length").text = l_val
        
        image_link = ET.SubElement(offer, "image_link")
        ET.SubElement(image_link, "picture").text = clean_cdata(find_v('image_link'))
        
        desc_html = format_description_html(desc_text)
        placeholder = f"___DESC_{item_id}___"
        descriptions_map[placeholder] = f"<![CDATA[\n{desc_html}\n]]>"
        ET.SubElement(offer, "description").text = placeholder

    xml_str = ET.tostring(new_root, encoding="utf-8").decode("utf-8")
    for placeholder, cdata_content in descriptions_map.items():
        xml_str = xml_str.replace(placeholder, cdata_content)

    final_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str
    with open('monomarket_content.xml', "w", encoding="utf-8") as f:
        f.write(final_xml)
    print(f"✅ Файл monomarket_content.xml створено!")

if __name__ == '__main__':
    if download_latest_feed():
        generate_mono_content_xml()