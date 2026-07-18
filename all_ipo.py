import re
from datetime import date, datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup


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
    today = date.today()

    for row in table.find("tbody").find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 5:
            continue

        company_cell = cols[0]
        ipo_link = company_cell.find("a")["href"] if company_cell.find("a") else ""
        company = company_cell.get_text(" ", strip=True)

        ipo_date_text = cols[1].get_text(" ", strip=True)
        ipo_size = cols[2].get_text(" ", strip=True)
        price_band = cols[3].get_text(" ", strip=True)
        apply_link = cols[4].find("a")["href"] if cols[4].find("a") else ""

        open_date, close_date = parse_ipo_dates(ipo_date_text)
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


def parse_ipo_dates(ipo_date_text: str):
    if not ipo_date_text:
        return None, None

    text = ipo_date_text.strip()
    year = date.today().year
    month_match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)",
        text,
        re.IGNORECASE,
    )
    month_name = month_match.group(1).title() if month_match else None

    if not month_name:
        month_name = date.today().strftime("%B")

    numbers = re.findall(r"\d+", text)
    if not numbers:
        return None, None

    try:
        start_day = int(numbers[0])
        end_day = int(numbers[1]) if len(numbers) > 1 else start_day
        start_date = datetime.strptime(f"{year} {month_name} {start_day}", "%Y %B %d").date()
        end_date = datetime.strptime(f"{year} {month_name} {end_day}", "%Y %B %d").date()
        return start_date, end_date
    except ValueError:
        return None, None


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
    enriched_rows = []

    for row in ipo_rows:
        gmp_data = fetch_gmp_data(row["GMP URL"]) if row["Status"] == "active" else {}
        enriched_rows.append({**row, **gmp_data})

    return pd.DataFrame(enriched_rows)


def main() -> None:
    df = build_combined_dataset()
    print(df[["Company", "Status", "IPO Date", "Current GMP", "Latest Gain %", "Last Updated"]].head(10))
    df.to_csv("upcoming_ipos.csv", index=False)
    print("\nSaved upcoming_ipos.csv")


if __name__ == "__main__":
    main()