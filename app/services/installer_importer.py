import csv
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

UPNEDA_URL = "https://upnedasolarrooftopportal.com/Approved-Firms"


def clean_text(value):
    if value is None:
        return None
    value = re.sub(r"\s+", " ", str(value)).replace("\ufffd", "-").strip()
    return value or None


def parse_upneda_html(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table#example") or soup.select_one("table")
    if table is None:
        raise ValueError("UPNEDA approved-firms table was not found.")

    records = []
    for row in table.select("tbody tr"):
        cells = row.find_all(["td", "th"])
        values = [clean_text(cell.get_text(" ", strip=True)) for cell in cells]
        if len(values) < 7:
            continue
        vendor_code = clean_text(values[2])
        name = clean_text(values[1])
        if not vendor_code or not name:
            continue
        records.append({
            "name": name,
            "vendor_code": vendor_code,
            "phone": clean_text(values[3]),
            "email": clean_text(values[4]),
            "district": clean_text(values[5]),
            "address": clean_text(values[6]),
            "approved_at": clean_text(values[7]) if len(values) > 7 else None,
        })
    return records


def fetch_upneda_records():
    response = requests.get(UPNEDA_URL, timeout=60)
    response.raise_for_status()
    return parse_upneda_html(response.text)


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        records = list(csv.DictReader(handle))
    return [record for record in records if clean_text(record.get("name")) and clean_text(record.get("vendor_code"))]


def approved_datetime(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(str(value).strip(), "%Y-%m-%d")
        except ValueError:
            return None
