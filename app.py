import os
import requests
from datetime import date, timedelta
from flask import Flask, jsonify, request

app = Flask(__name__)

HEADERS = {
    "User-Agent": "TW-Breakout-Radar/1.0"
}


def num(value):
    if value is None:
        return None

    value = str(value).strip().replace(",", "")

    if value in ("", "--", "---", "－", "—"):
        return None

    try:
        return float(value)
    except:
        return None


def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk(value)

    elif isinstance(obj, list):
        for value in obj:
            yield from walk(value)


def extract(payload, code_names, close_names, high_names):

    result = []

    for table in walk(payload):

        if not isinstance(table, dict):
            continue

        fields = table.get("fields")
        data = table.get("data")

        if not isinstance(fields, list):
            continue

        if not isinstance(data, list):
            continue

        fields = [str(x).strip() for x in fields]

        for row in data:

            if not isinstance(row, list):
                continue

            if len(row) != len(fields):
                continue

            item = dict(zip(fields, row))

            code = None
            close = None
            high = None
            name = ""

            for key in code_names:
                if key in item:
                    code = item[key]
                    break

            for key in close_names:
                if key in item:
                    close = item[key]
                    break

            for key in high_names:
                if key in item:
                    high = item[key]
                    break

            for key in ["證券名稱", "Name"]:
                if key in item:
                    name = item[key]
                    break

            if code is None:
                continue

            close = num(close)
            high = num(high)

            if close is None or high is None:
                continue

            code = str(code).strip()

            if not code.isdigit():
                continue

            result.append({
                "code": code,
                "name": str(name).strip(),
                "close": close,
                "high": high
            })

    return result


def twse(date_string):

    url = "https://www.twse.com.tw/exchangeReport/MI_INDEX"

    params = {
        "response": "json",
        "date": date_string,
        "type": "ALLBUT0999"
    }

    r = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=30
    )

    r.raise_for_status()

    payload = r.json()

    rows = extract(
        payload,
        ["證券代號"],
        ["收盤價"],
        ["最高價"]
    )

    return {
        x["code"]: {
            **x,
            "market": "TWSE"
        }
        for x in rows
    }


def tpex(date_string):

    d = (
        date_string[:4]
        + "/"
        + date_string[4:6]
        + "/"
        + date_string[6:]
    )

    url = "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes"

    params = {
        "response": "json",
        "date": d
    }

    r = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=30
    )

    r.raise_for_status()

    payload = r.json()

    rows = extract(
        payload,
        ["證券代號", "SecuritiesCompanyCode", "Code"],
        ["收盤價", "Close", "ClosingPrice"],
        ["最高價", "最高價", "High", "HighestPrice"]
    )

    return {
        x["code"]: {
            **x,
            "market": "TPEx"
        }
        for x in rows
    }


def get_day(d):

    twse_data = {}
    tpex_data = {}

    try:
        twse_data = twse(d)
    except:
        pass

    try:
        tpex_data = tpex(d)
    except:
        pass

    return {
        **twse_data,
        **tpex_data
    }


@app.get("/health")
def health():

    return {
        "status": "ok",
        "service": "TW Breakout Radar"
    }


@app.get("/api/scan")
def scan():

    days = int(request.args.get("days", 20))
    pct = float(request.args.get("pct", 10))

    days = max(2, min(days, 120))
    pct = max(0.1, min(pct, 100))

    sessions = []

    current = date.today()

    while len(sessions) < days + 1:

        d = current.strftime("%Y%m%d")

        market = get_day(d)

        if market:
            sessions.append((d, market))

        current -= timedelta(days=1)

        if (date.today() - current).days > days * 4:
            break

    if len(sessions) < days + 1:

        return jsonify({
            "error": "取得不到足夠的歷史交易資料"
        }), 503

    today_date, today_data = sessions[0]

    previous_sessions = sessions[1:days + 1]

    highs = {}

    for _, market in previous_sessions:

        for code, row in market.items():

            if row["high"] is not None:

                highs.setdefault(code, []).append(
                    row["high"]
                )

    results = []

    for code, row in today_data.items():

        values = highs.get(code, [])

        if len(values) < days:
            continue

        previous_high = max(values)

        price = row["close"]

        if price <= 0:
            continue

        distance = (
            (previous_high - price)
            / price
            * 100
        )

        # 排除已經突破前高的股票
        if distance <= 0:
            continue

        if distance > pct:
            continue

        score = round(
            100 - (distance / pct * 100)
        )

        if score >= 65:
            grade = "a"
        elif score >= 30:
            grade = "b"
        else:
            grade = "c"

        results.append({

            "code": code,

            "name": row["name"],

            "price": price,

            "high": previous_high,

            "dist": round(distance, 2),

            "score": score,

            "grade": grade,

            "market": row["market"],

            "reason":
                f"距離前 {days} 日高點 "
                f"{distance:.2f}%"

        })

    results.sort(
        key=lambda x: x["dist"]
    )

    return jsonify({

        "date": today_date,

        "days": days,

        "pct": pct,

        "count": len(results),

        "results": results

    })


if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
