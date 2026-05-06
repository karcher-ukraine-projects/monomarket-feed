import xml.etree.ElementTree as ET
import re

def clean_cdata(text):
    if not text: return ""
    return text.replace("<![CDATA[", "").replace("]]>", "").strip()

def format_description_html(raw_text):
    text = clean_cdata(raw_text)
    # Розбиваємо текст на речення
    parts = re.split(r'\. (?=[A-ZА-ЯІ])', text)
    
    html = f"<h5>Опис</h5>\n<p>{parts[0].strip()}.</p>\n<br>\n"
    html += "<h5>Характеристики та особливості</h5>\n<ul>\n"
    for part in parts[1:]:
        content = part.strip().rstrip('.')
        if content:
            html += f"  <li>{content}</li>\n"
    html += "</ul>"
    return html

def generate_mono_content_xml():
    print("📦 Формуємо ідеальний контентний фід для Monomarket...")
    
    tree = ET.parse('feed.xml')
    root = tree.getroot()
    ns = {'g': 'http://base.google.com/ns/1.0', 'atom': 'http://www.w3.org/2005/Atom'}
    entries = root.findall('.//atom:entry', ns) or root.findall('.//entry')

    # Створюємо нову структуру за вимогами Мономаркету
    new_root = ET.Element("Market")
    offers = ET.SubElement(new_root, "offers")

    # Словник для збереження чистих HTML описів
    descriptions_map = {}

    for entry in entries:
        def find_v(tag):
            el = entry.find(f'g:{tag}', ns)
            if el is None: el = entry.find(tag, ns)
            if el is None: el = entry.find(tag)
            return el.text if el is not None else ""

        # Відсіюємо товари, яких немає в наявності (вимога Мономаркету)
        avail = (find_v('availability') or "").lower()
        if "in stock" not in avail:
            continue

        offer = ET.SubElement(offers, "offer")
        item_id = find_v('id')
        
        # Обов'язкові ідентифікатори
        ET.SubElement(offer, "id").text = item_id
        ET.SubElement(offer, "code").text = item_id
        ET.SubElement(offer, "vendor_code").text = item_id
        
        ET.SubElement(offer, "title").text = clean_cdata(find_v('title'))
        
        # Баркод (GTIN)
        barcode = find_v('gtin')
        ET.SubElement(offer, "barcode").text = barcode if barcode else item_id
        
        # Категорія (беремо останнє слово з ланцюжка)
        full_cat = find_v('custom_label_0') or find_v('product_type')
        category = full_cat.split('>')[-1].strip() if '>' in full_cat else full_cat
        ET.SubElement(offer, "category").text = category if category else "Kärcher"
        
        ET.SubElement(offer, "brand").text = find_v('brand') or "Kärcher"
        ET.SubElement(offer, "availability").text = "в наявності"
        
        # Фотографії у правильному форматі
        image_link = ET.SubElement(offer, "image_link")
        ET.SubElement(image_link, "picture").text = clean_cdata(find_v('image_link'))
        
        # Опис (використовуємо тимчасовий плейсхолдер, щоб уникнути пошкодження дужок)
        desc_html = format_description_html(find_v('description'))
        placeholder = f"___DESC_{item_id}___"
        descriptions_map[placeholder] = f"<![CDATA[\n{desc_html}\n]]>"
        ET.SubElement(offer, "description").text = placeholder

    # Конвертуємо XML в рядок
    xml_str = ET.tostring(new_root, encoding="utf-8").decode("utf-8")
    
    # Замінюємо плейсхолдери на реальні CDATA-блоки
    for placeholder, cdata_content in descriptions_map.items():
        xml_str = xml_str.replace(placeholder, cdata_content)

    # Додаємо правильний заголовок XML
    final_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str

    # Зберігаємо готовий файл
    with open('monomarket_content.xml', "w", encoding="utf-8") as f:
        f.write(final_xml)

    print(f"✅ Готово! Створено файл 'monomarket_content.xml'.")
    print(f"📊 Додано товарів у фід: {len(descriptions_map)} (тільки ті, що в наявності).")

if __name__ == '__main__':
    generate_mono_content_xml()