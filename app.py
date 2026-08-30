import os
import requests
from datetime import date, timedelta
from flask import Flask, jsonify, request, send_file

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def num(value):
    if value is None:
        return None

    value = str(value).strip().replace(",", "")

    if value in ("", "--", "---", "－", "—", "None"):
        return None

    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def get_twse(date_string):
    url = "https://www.twse.com.tw/exchangeReport/MI_INDEX"

    params = {
        "response": "json",
        "date": date_string,
        "type": "ALLBUT0999"
    }

    try:
        response = requests.get(
            url,
            params=params,
            headers=HEADERS,
            timeout=30
        )

        response.raise_for_status()
        payload = response.json()

        result = {}

        for table in payload.get("tables", []):
            fields = table.get("fields", [])
            rows = table.get("data", [])

            if not fields or not rows:
                continue

            field_map = {
                str(field).strip(): index
                for index, field in enumerate(fields)
            }

            code_index = field_map.get("證券代號")
            name_index = field_map.get("證券名稱")
            high_index = field_map.get("最高價")
            close_index = field_map.get("收盤價")

            if None in (
                code_index,
                name_index,
                high_index,
                close_index
            ):
                continue

            for row in rows:
                if len(row) <= max(
                    code_index,
                    name_index,
                    high_index,
                    close_index
                ):
                    continue

                code = str(row[code_index]).strip()

                if not code.isdigit():
                    continue

                close = num(row[close_index])
                high = num(row[high_index])

                if close is None or high is None:
                    continue

                result[code] = {
                    "code": code,
                    "name": str(row[name_index]).strip(),
                    "close": close,
                    "high": high,
                    "market": "上市"
                }

        return result

    except Exception:
        return {}


def get_tpex(date_string):
    url = "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes"

    formatted_date = (
        date_string[:4]
        + "/"
        + date_string[4:6]
        + "/"
        + date_string[6:]
    )

    params = {
        "response": "json",
        "date": formatted_date
    }

    try:
        response = requests.get(
            url,
            params=params,
            headers=HEADERS,
            timeout=30
        )

        response.raise_for_status()
        payload = response.json()

        result = {}

        for table in payload.get("tables", []):
            fields = table.get("fields", [])
            rows = table.get("data", [])

            if not fields or not rows:
                continue

            field_map = {
                str(field).strip(): index
                for index, field in enumerate(fields)
            }

            code_index = None
            name_index = None
            high_index = None
            close_index = None

            for key in (
                "證券代號",
                "SecuritiesCompanyCode",
                "Code"
            ):
                if key in field_map:
                    code_index = field_map[key]
                    break

            for key in (
                "證券名稱",
                "Name"
            ):
                if key in field_map:
                    name_index = field_map[key]
                    break

            for key in (
                "最高價",
                "High",
                "HighestPrice"
            ):
                if key in field_map:
                    high_index = field_map[key]
                    break

            for key in (
                "收盤價",
                "Close",
                "ClosingPrice"
            ):
                if key in field_map:
                    close_index = field_map[key]
                    break

            if None in (
                code_index,
                name_index,
                high_index,
                close_index
            ):
                continue

            for row in rows:
                if len(row) <= max(
                    code_index,
                    name_index,
                    high_index,
                    close_index
                ):
                    continue

                code = str(row[code_index]).strip()

                if not code.isdigit():
                    continue

                close = num(row[close_index])
                high = num(row[high_index])

                if close is None or high is None:
                    continue

                result[code] = {
                    "code": code,
                    "name": str(row[name_index]).strip(),
                    "close": close,
                    "high": high,
                    "market": "上櫃"
                }

        return result

    except Exception:
        return {}


def get_market_day(date_string):
    market = {}

    market.update(get_twse(date_string))
    market.update(get_tpex(date_string))

    return market


def get_history(days):
    history = []

    current = date.today()

    max_days = days * 4 + 20
    checked = 0

    while len(history) < days + 1 and checked < max_days:
        date_string = current.strftime("%Y%m%d")

        market = get_market_day(date_string)

        if market:
            history.append(
                (date_string, market)
            )

        current -= timedelta(days=1)
        checked += 1

    return history


def scan_market(days, pct):
    history = get_history(days)

    if len(history) < days + 1:
        return {
            "error": "取得不到足夠的歷史交易資料",
            "results": []
        }

    today_string, today_market = history[0]

    previous_days = history[1:days + 1]

    historical_highs = {}

    for _, market in previous_days:
        for code, stock in market.items():

            high = stock["high"]

            if high is None:
                continue

            historical_highs.setdefault(
                code,
                []
            ).append(high)

    results = []

    for code, stock in today_market.items():

        highs = historical_highs.get(code, [])

        if len(highs) < days:
            continue

        previous_high = max(highs)

        current_price = stock["close"]

        if current_price <= 0:
            continue

        distance = (
            (previous_high - current_price)
            / current_price
            * 100
        )

        # 已創新高或等於前高，排除
        if distance <= 0:
            continue

        # 超過設定距離，排除
        if distance > pct:
            continue

        # 越接近突破，分數越高
        score = round(
            100 - (distance / pct * 100)
        )

        score = max(0, min(score, 100))

        if score >= 70:
            grade = "a"
        elif score >= 40:
            grade = "b"
        else:
            grade = "c"

        results.append({
            "code": code,
            "name": stock["name"],
            "market": stock["market"],
            "price": current_price,
            "high": round(previous_high, 2),
            "dist": round(distance, 2),
            "score": score,
            "grade": grade
        })

    results.sort(
        key=lambda item: (
            -item["score"],
            item["dist"]
        )
    )

    return {
        "date": today_string,
        "days": days,
        "pct": pct,
        "count": len(results),
        "results": results
    }


@app.route("/")
def home():
    return send_file("index.html")


@app.route("/api/scan")
def api_scan():
    try:
        days = int(
            request.args.get(
                "days",
                20
            )
        )

        pct = float(
            request.args.get(
                "pct",
                10
            )
        )

        days = max(
            2,
            min(days, 120)
        )

        pct = max(
            0.1,
            min(pct, 100)
        )

        result = scan_market(
            days,
            pct
        )

        return jsonify(result)

    except Exception as error:

        return jsonify({
            "error": str(error),
            "results": []
        }), 500


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "TW Breakout Radar"
    })


if __name__ == "__main__":
    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
