import re
from pipeline import get_state_url, get_pdf_urls
from pdf_parser import download_pdf, extract_text, extract_indicators, INDICATOR_IDS

urls = [u for u in get_pdf_urls("Andhra Pradesh", "andhra-pradesh", "slug") if u.endswith('.pdf')]
if urls:
    print(f"Testing with: {urls[0]}")
    pdf_bytes = download_pdf(urls[0])
    text = extract_text(pdf_bytes)
    with open("data/_raw_ap.txt", "w", encoding="utf-8") as f:
        f.write(text)
    print("--- RAW TEXT SAVED TO data/_raw_ap.txt ---")
    
    print("\n--- EXTRACTED INDICATORS ---")
    results = extract_indicators(text)
    found_count = sum(1 for v in results.values() if v["found"])
    print(f"Total found: {found_count}/26")
    
    # Track missing
    for ind in INDICATOR_IDS:
        if not results[ind]["found"]:
            print(f"Missing: {ind}")
