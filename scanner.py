import requests
from bs4 import BeautifulSoup
import re
import xml.etree.ElementTree as ET
import time

HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 10


# ---------------- SITEMAP ----------------

def parse_sitemap(url):
    urls = []

    try:
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        root = ET.fromstring(res.content)

        for child in root:
            for sub in child:
                if "loc" in sub.tag:
                    urls.append(sub.text.strip())

        return urls

    except:
        return []


def get_all_urls(domain):
    sitemap_url = domain.rstrip("/") + "/sitemap.xml"
    first_level = parse_sitemap(sitemap_url)

    all_urls = []

    for url in first_level:
        if url.endswith(".xml"):
            sub_urls = parse_sitemap(url)
            all_urls.extend(sub_urls)
        else:
            all_urls.append(url)

    # Duplicate URL temizle
    return list(set(all_urls))


# ---------------- SAYFA TARAMA ----------------

def scan_page(url):
    """
    Tek bir URL'yi tarar.
    Kod bulursa (code, url) döndürür.
    """
    try:
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)

        if res.status_code != 200:
            return None

        soup = BeautifulSoup(res.text, "html.parser")
        footer = soup.find("footer")

        if not footer:
            return None

        footer_text = footer.get_text(separator="\n")

        if "Instagram Hediye Kodu" not in footer_text:
            return None

        parts = footer_text.split("Instagram Hediye Kodu", 1)

        if len(parts) > 1:
            after_text = parts[1].strip()
            first_line = after_text.split("\n")[0].strip()

            # 6 karakter alfanumerik kod
            if re.fullmatch(r"[A-Za-z0-9]{6}", first_line):
                return (first_line, url)

        return None

    except:
        return None


# ---------------- DOMAIN TARAMA ----------------

def scan_domain(domain):
    """
    Domain içindeki tüm URL'leri tarar.
    (code, source_url) listesi döndürür.
    """

    
  print("SCAN_DOMAIN BAŞLADI")

    found_codes = []
    seen_codes = set()

    urls = get_all_urls(domain)

    print("URL SAYISI:", len(urls))  
    

    urls = get_all_urls(domain)

    for url in urls:
        result = scan_page(url)

        if result:
            code, source_url = result

            # Aynı tarama içinde duplicate engelle
            if code not in seen_codes:
                seen_codes.add(code)
                found_codes.append((code, source_url))

        time.sleep(0.5)  # Sunucuya yük bindirmemek için

    return found_codes
