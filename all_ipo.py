import re
from datetime import date, datetime, timedelta

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dateutil import parser
import re
from datetime import date


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    )
}



def fetch_ipo_master(url: str = "https://ipowatch.in/upcoming-ipo-list/") -> list[dict]:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", id="tablepress-22")
    if not table:
        raise Exception("IPO table not found")

    data = []
    # today = date.today()
    today = date.today() + timedelta(days=1)  # Adjust for timezone if needed
    

    for row in table.find("tbody").find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 5:
            continue

        company_cell = cols[0]
        ipo_link = company_cell.find("a")["href"] if company_cell.find("a") else ""
        company = company_cell.get_text(" ", strip=True)

        ipo_date_text = cols[1].get_text(" ", strip=True)
        print(repr(ipo_date_text))
        ipo_size = cols[2].get_text(" ", strip=True)
        price_band = cols[3].get_text(" ", strip=True)
        apply_link = cols[4].find("a")["href"] if cols[4].find("a") else ""

        open_date, close_date = parse_ipo_dates(ipo_date_text)
        print(
            f"{company:30} | "
            f"{ipo_date_text:15} | "
            f"{open_date} -> {close_date}"
        )
        status = "future"
        if open_date and close_date:
            if open_date <= today <= close_date:
                status = "active"
            elif close_date < today:
                status = "closed"

        gmp_url = build_gmp_url(ipo_link)

        data.append(
            {
                "Company": company,
                "IPO Date": ipo_date_text,
                "IPO Size": ipo_size,
                "Price Band": price_band,
                "Apply Link": apply_link,
                "IPO Link": ipo_link,
                "GMP URL": gmp_url,
                "Status": status,
                "Open Date": open_date.strftime("%Y-%m-%d") if open_date else None,
                "Close Date": close_date.strftime("%Y-%m-%d") if close_date else None,
            }
        )

    return data


from calendar import month_name

MONTH_NUMBERS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

def parse_ipo_dates(text):
    text = text.strip()

    m = re.search(
        r"(\d+)\s*-\s*(\d+)\s*"
        r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)",
        text,
        re.I,
    )

    if not m:
        return None, None

    start_day = int(m.group(1))
    end_day = int(m.group(2))

    end_month = MONTH_NUMBERS[m.group(3)[:3].lower()]
    start_month = end_month

    year = date.today().year

    if end_day < start_day:
        start_month -= 1
        if start_month == 0:
            start_month = 12
            year -= 1

    return (
        date(year, start_month, start_day),
        date(year, end_month, end_day),
    )


def build_gmp_url(ipo_link: str) -> str:
    if not ipo_link:
        return ""
    slug = ipo_link.rstrip("/").split("/")[-1]
    return f"https://ipowatch.in/{slug}-gmp-grey-market-premium/"


def fetch_gmp_data(gmp_url: str) -> dict:
    if not gmp_url:
        return {
            "Current GMP": None,
            "Latest Gain %": None,
            "Last Updated": None,
            "GMP History": [],
        }

    try:
        response = requests.get(gmp_url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return {
            "Current GMP": None,
            "Latest Gain %": None,
            "Last Updated": None,
            "GMP History": [],
        }

    soup = BeautifulSoup(response.text, "html.parser")
    gmp_table = None

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            headers = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
            if "IPO GMP" in headers and "GMP Trend" in headers:
                gmp_table = table
                break
        if gmp_table:
            break

    if not gmp_table:
        return {
            "Current GMP": None,
            "Latest Gain %": None,
            "Last Updated": None,
            "GMP History": [],
        }

    history = []
    rows = gmp_table.find_all("tr")[1:]
    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 5:
            history.append(
                {
                    "Date": cols[0].get_text(" ", strip=True),
                    "IPO GMP": cols[1].get_text(" ", strip=True),
                    "Trend": cols[2].get_text(" ", strip=True),
                    "Gain": cols[3].get_text(" ", strip=True),
                    "Last Updated": cols[4].get_text(" ", strip=True),
                }
            )

    latest = history[0] if history else {}

    return {
        "Current GMP": latest.get("IPO GMP"),
        "Latest Gain %": latest.get("Gain"),
        "Last Updated": latest.get("Last Updated"),
        "GMP History": history,
    }


def parse_numeric_value(raw_value):
    if raw_value is None:
        return None

    text = str(raw_value).strip()
    if not text:
        return None

    text = text.replace("₹", "").replace("%", "").replace(",", "")
    numbers = re.findall(r"[-+]?\d*\.?\d+", text)
    if not numbers:
        return None

    return float(numbers[0])


def build_combined_dataset() -> pd.DataFrame:
    ipo_rows = fetch_ipo_master()
    active = [row for row in ipo_rows if row["Status"] == "active"]

    print(f"Today's date: {date.today()}")
    print(f"Active IPOs: {len(active)}")

    for row in active:
        print(row["Company"], row["Open Date"], row["Close Date"])
    print(f"Found {len(ipo_rows)} IPOs")

    enriched_rows = []

    EMPTY_GMP = {
        "Current GMP": None,
        "Latest Gain %": None,
        "Last Updated": None,
        "GMP History": [],
    }

    for row in ipo_rows:
        if row["Status"] == "active":
            gmp_data = fetch_gmp_data(row["GMP URL"])
        else:
            gmp_data = EMPTY_GMP.copy()

        enriched_rows.append({**row, **gmp_data})
    return pd.DataFrame(enriched_rows)


def main() -> None:
    df = build_combined_dataset()
    print(df[["Company", "Status", "IPO Date", "Current GMP", "Latest Gain %", "Last Updated"]].head(10))
    df.to_csv("upcoming_ipos.csv", index=False)
    print("\nSaved upcoming_ipos.csv")


if __name__ == "__main__":
    main()