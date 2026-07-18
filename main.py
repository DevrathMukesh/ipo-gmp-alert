import os
import re
from pathlib import Path
from datetime import datetime

import requests

from all_ipo import build_combined_dataset, parse_numeric_value


# -----------------------------
# ENV
# -----------------------------

def load_env_file():

    env_path = Path(__file__).resolve().parent / ".env"

    if not env_path.exists():
        return

    for line in env_path.read_text().splitlines():

        line = line.strip()

        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            continue

        key, value = line.split("=", 1)

        os.environ.setdefault(
            key.strip(),
            value.strip().strip('"').strip("'")
        )


load_env_file()


TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")



# -----------------------------
# FORMAT
# -----------------------------

def format_value(value):

    if value is None:
        return "-"

    return f"{value:.2f}%"



# -----------------------------
# HISTORY ANALYSIS
# -----------------------------

def parse_history_date(value):

    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text)

    for fmt in (
        "%d %b",
        "%d %B",
        "%d %b %Y",
        "%d %B %Y",
        "%d-%b",
        "%d-%B",
        "%d-%b-%Y",
        "%d-%B-%Y",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    return None


def summarize_history(history):


    history_items = list(history or [])


    parsed_items = []


    for idx, item in enumerate(history_items):

        value = parse_numeric_value(
            item.get("Gain")
        )

        if value is not None:

            parsed_items.append({

                "date": item.get("Date") or "-",
                "value": value,
                "_sort_date": parse_history_date(item.get("Date")),
                "_index": idx,

            })


    if not parsed_items:

        return {

            "start_gmp": None,
            "current_gmp": None,
            "highest_gmp": None,
            "lowest_gmp": None,
            "drop_from_high": None,
            "movement_lines": ["-"],
            "start_date": "-",
            "end_date": "-",
            "trend": "Neutral",
            "change": None,
            "new_high": False,
            "consistent_upward": False,
            "above_threshold": False,
            "near_high": False,
            "warning": False

        }



    parsed_items.sort(
        key=lambda item: (
            item["_sort_date"] is None,
            item["_sort_date"] or datetime.max,
            item["_index"],
        )
    )



    start_gmp = parsed_items[0]["value"]

    current_gmp = parsed_items[-1]["value"]

    highest_gmp = max(
        x["value"]
        for x in parsed_items
    )

    lowest_gmp = min(
        x["value"]
        for x in parsed_items
    )

    change = current_gmp - start_gmp
    drop_from_high = highest_gmp - current_gmp



    movement_lines = []


    up = 0
    down = 0



    for i,item in enumerate(parsed_items):


        arrow = ""


        if i > 0:

            previous = parsed_items[i-1]["value"]


            if item["value"] > previous:

                arrow=" ⬆️"
                up += 1


            elif item["value"] < previous:

                arrow=" ⬇️"
                down += 1


            else:

                arrow=" ➖"



        movement_lines.append(

            f"{item['date']} → {format_value(item['value'])}{arrow}"

        )



    if warning := (drop_from_high / highest_gmp > 0.25 if highest_gmp else False):

        trend="Falling"

    elif near_high := (highest_gmp > 0 and (drop_from_high / highest_gmp) <= 0.10):

        trend="Cooling but strong"

    elif up > down:

        trend="Rising"

    elif down > up:

        trend="Falling"

    else:

        trend="Mixed"



    if len(parsed_items) > 1:

        new_high = (

            current_gmp == highest_gmp

            and

            current_gmp > parsed_items[-2]["value"]

        )

    else:
        new_high = False



    consistent_upward = (

        up >= 2

        and

        down == 0

    )

    above_threshold = current_gmp > 10
    near_high = highest_gmp > 0 and (drop_from_high / highest_gmp) <= 0.10
    warning = above_threshold and (drop_from_high / highest_gmp) > 0.25



    return {


        "start_gmp": start_gmp,
        "current_gmp": current_gmp,
        "highest_gmp": highest_gmp,
        "lowest_gmp": lowest_gmp,
        "drop_from_high": drop_from_high,
        "movement_lines": movement_lines,
        "start_date": parsed_items[0]["date"],
        "end_date": parsed_items[-1]["date"],
        "trend": trend,
        "change": change,
        "new_high": new_high,
        "consistent_upward": consistent_upward,
        "above_threshold": above_threshold,
        "near_high": near_high,
        "warning": warning

    }





# -----------------------------
# TELEGRAM MESSAGE
# -----------------------------

def build_alert_message(rows):


    if not rows:

        return "No active IPOs with GMP above 10% found right now."



    blocks=[]



    for row in rows:


        summary = summarize_history(

            row.get("GMP History") or []

        )


        if summary["current_gmp"] is None:

            continue



        change_text=""


        if summary["drop_from_high"] is not None:

            if summary["drop_from_high"] > 0:

                change_text = (

                    f" (↓ {summary['drop_from_high']:.2f} from high)"

                )

            else:

                change_text = " 🔥 New High"



        lines=[]


        lines.append(

            f"🚀 {row.get('Company','UNKNOWN').upper()}"

        )


        lines.append(

            "━━━━━━━━━━━━━━━━"

        )


        lines.append(

            f"GMP: {format_value(summary['current_gmp'])}"

            f"{change_text}"

        )


        lines.append("")


        lines.append(

            f"📈 Trend: {summary['trend']}"

        )


        lines.append(

            f"📅 Period: {summary['start_date']} → {summary['end_date']}"

        )


        lines.append("")


        lines.append(

            "📊 GMP Snapshot"

        )


        lines.append(

            f"Start    : {format_value(summary['start_gmp'])}"

        )


        lines.append(

            f"Current  : {format_value(summary['current_gmp'])}"

        )


        lines.append(

            f"High     : {format_value(summary['highest_gmp'])}"

        )


        lines.append(

            f"Low      : {format_value(summary['lowest_gmp'])}"

        )


        lines.append("")


        lines.append(

            "📈 Movement"

        )


        lines.extend(

            summary["movement_lines"]

        )


        lines.append("")


        lines.append(

            "🚀 Signals"

        )


        if summary["new_high"]:

            lines.append(

                "📈 New GMP high"

            )


        if summary["near_high"]:

            lines.append(

                "📈 Trading near lifetime high"

            )


        if summary["warning"]:

            lines.append(

                "⚠️ Far below peak GMP"

            )


        if summary["above_threshold"]:

            lines.append(

                "✅ GMP above 10%"

            )


        if summary["above_threshold"] and (summary["near_high"] or not summary["warning"]):

            lines.append(

                "🔥 Strong grey market demand"

            )



        blocks.append(

            "\n".join(lines)

        )



    return "\n\n".join(blocks)




# -----------------------------
# SEND TELEGRAM
# -----------------------------

def send_telegram_message(text):


    if not TOKEN or not CHAT_ID:

        print(text)

        return



    url = (

        f"https://api.telegram.org/"

        f"bot{TOKEN}/sendMessage"

    )


    response=requests.post(

        url,

        json={

            "chat_id":CHAT_ID,

            "text":text

        },

        timeout=30

    )


    response.raise_for_status()



# -----------------------------
# MAIN
# -----------------------------

def main():


    df = build_combined_dataset()


    filtered=[]



    for _,row in df.iterrows():


        if row.get("Status") != "active":

            continue



        gmp_value = parse_numeric_value(

            row.get("Current GMP")

        )


        if gmp_value is not None and gmp_value > 10:

            filtered.append(row)



    if not filtered:

        print("No qualifying active IPOs found. Skipping Telegram message.")

        return



    message = build_alert_message(filtered)


    print(message)


    send_telegram_message(message)




if __name__ == "__main__":

    main()