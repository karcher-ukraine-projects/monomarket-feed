import xml.etree.ElementTree as ET
import re
import requests
import urllib3
import os
import csv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FEED_URL = "https://globalweb-webservice.app.kaercher.com/api/v2/shared/datafeed/2/07c2ca4b/google+uk-UA/uk-UA_google_shopping_feed.xml"
USERNAME = os.environ.get("KARCHER_USER")
PASSWORD = os.environ.get("KARCHER_PASS")
LOCAL_XML = 'feed.xml'
CSV_FILE = 'enrichment.csv'

def download_latest_feed():
    print("📥 Завантажуємо свіжий фід...")
    try:
        response = requests.get(FEED_URL, auth=(USERNAME, PASSWORD), verify=False)
        response.raise_for_status()
        with open(LOCAL_XML, 'wb') as f:
            f.write(response.content)
        return True
    except:
        return False

def clean_cdata(text):
    if not text: return ""
    return text.replace("<![CDATA[", "").replace("]]>", "").strip()

def format_description_html(raw_text):
    text = clean_cdata(raw_text)
    text = re.sub(r'(?i)(?:вага|вес)[\s:.-]*\d+[.,]?\d*\s*(?:кг|г)\b', '', text)
    text = re.sub(r'(?i)(?:розмір|розміри|габарити|размер)[\s:.-]*\d+[.,]?\d*\s*[xхХ*×]\s*\d+[.,]?\d*(?:\s*[xхХ*×]\s*\d+[.,]?\d*)?\s*(?:см|мм|м)\b', '', text)
    parts = re.split(r'\. (?=[A-ZА-ЯІЄЇҐ])', text)
    clean_parts = [p.strip() for p in parts if p.strip() and len(p) > 2]
    
    if not clean_parts: return ""
    html = f"<h5>Опис</h5>\n<p>{clean_parts[0].rstrip('.')}.</p>\n"
    if len(clean_parts) > 1:
        html += "<br>\n<h5>Характеристики та особливості</h5>\n<ul>\n"
        for part in clean_parts[1:]:
            content = part.strip().rstrip('.')
            if content: html += f"  <li>{content}</li>\n"
        html += "</ul>"
    return html

def load_csv_data():
    """Завантажує дані з CSV файлу і повертає словник за артикулами"""
    csv_data = {}
    if not os.path.exists(CSV_FILE):
        print(f"⚠️ Файл {CSV_FILE} не знайдено, збагачення даних пропущено.")
        return csv_data
        
    print("📊 Зчитуємо дані з таблиці enrichment.csv...")
    try:
        with open(CSV_FILE, mode='r', encoding='utf-8-sig') as f:
            # Excel може зберігати CSV з комами або крапками з комою, пробуємо автоматично визначити
            sample = f.read(1024)
            f.seek(0)
            delimiter = ';' if ';' in sample else ','
            
            reader = csv.reader(f, delimiter=delimiter)
            for row in reader:
                if len(row) < 11: continue  # Пропускаємо неповні рядки
                
                raw_id = row[0]
                if not raw_id or raw_id.lower() == 'матеріал': continue
                
                # Очищаємо ID (0.010-109.0 -> 00101090)
                clean_id = re.sub(r'\D', '', raw_id)
                # Якщо ID починається з нулів і обрізався, це ок, бо у фіді вони теж обрізані або співпадуть
                
                weight = row[2].replace(',', '.') if row[2] else ""  # Беремо Вага брутто (стовпець C)
                if not weight and row[1]: weight = row[1].replace(',', '.') # Або нетто (B)
                if float(weight) == 0.0 if weight.replace('.','',1).isdigit() else True: weight = ""
                
                dims = row[8].upper() # Розмір/габарити (стовпець I)
                barcode = row[10] # EAN/UPC (стовпець K)
                
                l, w, h = "", "", ""
                if dims and 'X' in dims:
                    parts = dims.split('X')
                    try:
                        # Ділимо на 10, щоб перевести міліметри в сантиметри
                        l = str(round(float(re.sub(r'\D', '', parts[0])) / 10, 2))
                        if len(parts) > 1: w = str(round(float(re.sub(r'\D', '', parts[1])) / 10, 2))
                        if len(parts) > 2: h = str(round(float(re.sub(r'\D', '', parts[2])) / 10, 2))
                    except: pass
                
                csv_data[clean_id] = {
                    'weight': weight, 'length': l, 'width': w, 'height': h, 'barcode': barcode
                }
    except Exception as e:
        print(f"❌ Помилка читання CSV: {e}")
        
    return csv_data

def parse_dimensions_from_text(text, entry, ns):
    """Стара функція резервного парсингу з тексту, якщо в CSV нічого немає"""
    weight, length, width, height = "", "", "", ""
    def find_tag(tag):
        el = entry.find(f'g:{tag}', ns)
        return el.text if el is not None else ""

    g_weight = find_tag('shipping_weight') or find_tag('product_weight')
    if g_weight:
        w_m = re.search(r'([\d\.,]+)', g_weight)
        if w_m: weight = w_m.group(1).replace(',', '.')

    if text:
        if not weight:
            w_match = re.search(r'(\d+[.,]?\d*)\s*(кг|г)\b', text, re.IGNORECASE)
            if w_match:
                try:
                    val = float(w_match.group(1).replace(',', '.'))
                    if w_match.group(2).lower() == 'г': val = val / 1000
                    weight = str(round(val, 3))
                except: pass
                
        d_match = re.search(r'(\d+[.,]?\d*)\s*[xхХ*×]\s*(\d+[.,]?\d*)(?:\s*[xхХ*×]\s*(\d+[.,]?\d*))?\s*(см|мм|м)\b', text, re.IGNORECASE)
        if d_match:
            try:
                v1 = float(d_match.group(1).replace(',', '.'))
                v2 = float(d_match.group(2).replace(',', '.'))
                v3 = float(d_match.group(3).replace(',', '.')) if d_match.group(3) else None
                unit = d_match.group(4).lower()
                
                if unit == 'мм':
                    v1, v2 = v1/10, v2/10
                    if v3 is not None: v3 = v3/10
                elif unit == 'м':
                    v1, v2 = v1*100, v2*100
                    if v3 is not None: v3 = v3*100
                    
                length, width = str(round(v1, 2)), str(round(v2, 2))
                if v3 is not None: height = str(round(v3, 2))
            except: pass
    return weight, length, width, height

def generate_mono_content_xml():
    print("📦 Формуємо ідеальний контентний фід...")
    if not os.path.exists(LOCAL_XML): return

    csv_data = load_csv_data() # Завантажуємо таблицю з даними!

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
        if "in stock" not in avail: continue

        offer = ET.SubElement(offers, "offer")
        item_id = find_v('id')
        # Нормалізуємо ID для пошуку в CSV (на випадок якщо у фіді є тире)
        clean_item_id = re.sub(r'\D', '', item_id)
        
        # Витягуємо дані з таблиці, якщо вони є
        table_info = csv_data.get(clean_item_id, {})

        ET.SubElement(offer, "id").text = item_id
        ET.SubElement(offer, "code").text = item_id
        ET.SubElement(offer, "vendor_code").text = item_id
        
        title = clean_cdata(find_v('title'))
        if item_id not in title: title = f"{title} ({item_id})"
        ET.SubElement(offer, "title").text = title
        
        # Штрихкод: Спочатку з фіду, якщо нема - з ТАБЛИЦІ
        barcode = find_v('gtin')
        if not barcode: barcode = table_info.get('barcode', '')
        ET.SubElement(offer, "barcode").text = barcode if barcode else item_id
        
        full_cat = find_v('custom_label_0') or find_v('product_type')
        category = full_cat.split('>')[-1].strip() if '>' in full_cat else full_cat
        ET.SubElement(offer, "category").text = category if category else "Kärcher"
        
        ET.SubElement(offer, "brand").text = find_v('brand') or "Kärcher"
        ET.SubElement(offer, "availability").text = "в наявності"
        
        # Габарити: Спочатку з ТАБЛИЦІ, якщо нема - парсимо з тексту
        desc_text = find_v('description')
        w_val = table_info.get('weight', '')
        l_val = table_info.get('length', '')
        w2_val = table_info.get('width', '')
        h_val = table_info.get('height', '')

        # Якщо таблиця порожня, пробуємо резервний метод (з тексту)
        if not w_val or not l_val:
            txt_w, txt_l, txt_w2, txt_h = parse_dimensions_from_text(desc_text, entry, ns)
            if not w_val: w_val = txt_w
            if not l_val: l_val, w2_val, h_val = txt_l, txt_w2, txt_h
        
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
    print("✅ Файл monomarket_content.xml створено із заповненими даними з таблиці!")

if __name__ == '__main__':
    if download_latest_feed():
        generate_mono_content_xml()
