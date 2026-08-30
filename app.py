import os
import requests
from datetime import date, timedelta
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)


# =========================
# 基本設定
# =========================

HEADERS = {
    "User-Agent": "TW-Breakout-Radar/1.0"
}


# =========================
# 工具
# =========================

def num(value):
    if value is None:
        return None

    value = str(value).strip().replace(",", "")

    if value in ("", "--", "---", "－", "—"):
        return None

    try:
        return float(value)
    except Exception:
        return None


# =========================
# TWSE 上市資料
# =========================

def get_twse(date_string):

    url = "https://www.twse.com.tw/exchangeReport/MI_INDEX"

    params = {
        "response": "json",
        "date": date_string,
        "type": "ALLBUT0999"
    }

    try:
        r = requests.get(
            url,
            params=params,
            headers=HEADERS,
            timeout=30
        )

        r.raise_for_status()

        payload = r.json()

        result = {}

        for table in payload.get("tables", []):

            fields = table.get("fields", [])
            rows = table.get("data", [])

            if not fields or not rows:
                continue

            field_map = {
                str(v).strip(): i
                for i, v in enumerate(fields)
            }

            code_i = field_map.get("證券代號")
            name_i = field_map.get("證券名稱")
            high_i = field_map.get("最高價")
            close_i = field_map.get("收盤價")

            if None in (code_i, name_i, high_i, close_i):
                continue

            for row in rows:

                if len(row) <= max(
                    code_i,
                    name_i,
                    high_i,
                    close_i
                ):
                    continue

                code = str(row[code_i]).strip()

                if not code.isdigit():
                    continue

                close = num(row[close_i])
                high = num(row[high_i])

                if close is None or high is None:
                    continue

                result[code] = {
                    "code": code,
                    "name": str(row[name_i]).strip(),
                    "close": close,
                    "high": high,
                    "market": "上市"
                }

        return result

    except Exception:

        return {}


# =========================
# TPEx 上櫃資料
# =========================

def get_tpex(date_string):

    url = "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes"

    formatted = (
        date_string[:4]
        + "/"
        + date_string[4:6]
        + "/"
        + date_string[6:]
    )

    params = {
        "response": "json",
        "date": formatted
    }

    try:

        r = requests.get(
            url,
            params=params,
            headers=HEADERS,
            timeout=30
        )

        r.raise_for_status()

        payload = r.json()

        result = {}

        tables = payload.get("tables", [])

        for table in tables:

            fields = table.get("fields", [])
            rows = table.get("data", [])

            if not fields or not rows:
                continue

            field_map = {
                str(v).strip(): i
                for i, v in enumerate(fields)
            }

            code_i = None
            name_i = None
            high_i = None
            close_i = None

            for key in [
                "證券代號",
                "SecuritiesCompanyCode",
                "Code"
            ]:
                if key in field_map:
                    code_i = field_map[key]
                    break

            for key in [
                "證券名稱",
                "Name"
            ]:
                if key in field_map:
                    name_i = field_map[key]
                    break

            for key in [
                "最高價",
                "High",
                "HighestPrice"
            ]:
                if key in field_map:
                    high_i = field_map[key]
                    break

            for key in [
                "收盤價",
                "Close",
                "ClosingPrice"
            ]:
                if key in field_map:
                    close_i = field_map[key]
                    break

            if None in (
                code_i,
                name_i,
                high_i,
                close_i
            ):
                continue

            for row in rows:

                if len(row) <= max(
                    code_i,
                    name_i,
                    high_i,
                    close_i
                ):
                    continue

                code = str(row[code_i]).strip()

                if not code.isdigit():
                    continue

                close = num(row[close_i])
                high = num(row[high_i])

                if close is None or high is None:
                    continue

                result[code] = {
                    "code": code,
                    "name": str(row[name_i]).strip(),
                    "close": close,
                    "high": high,
                    "market": "上櫃"
                }

        return result

    except Exception:

        return {}


# =========================
# 取得某一天完整市場資料
# =========================

def get_market_day(date_string):

    data = {}

    twse = get_twse(date_string)

    tpex = get_tpex(date_string)

    data.update(twse)
    data.update(tpex)

    return data


# =========================
# 找最近交易日
# =========================

def get_history(days):

    history = []

    current = date.today()

    max_calendar_days = days * 4 + 20

    checked = 0

    while (
        len(history) < days + 1
        and checked < max_calendar_days
    ):

        date_string = current.strftime("%Y%m%d")

        market = get_market_day(date_string)

        if market:

            history.append(
                (
                    date_string,
                    market
                )
            )

        current -= timedelta(days=1)

        checked += 1

    return history


# =========================
# 突破雷達
# =========================

def scan_market(days=20, pct=10):

    history = get_history(days)

    if len(history) < days + 1:

        return {
            "error": "目前取得不到足夠的歷史交易資料",
            "results": []
        }

    today_string, today_data = history[0]

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

    for code, stock in today_data.items():

        highs = historical_highs.get(
            code,
            []
        )

        if len(highs) < days:
            continue

        previous_high = max(highs)

        current_price = stock["close"]

        if current_price <= 0:
            continue

        # 距離前 X 日最高價還差多少 %
        distance = (
            (previous_high - current_price)
            / current_price
            * 100
        )

        # 已經創新高 / 等於前高 → 排除
        if distance <= 0:
            continue

        # 超過使用者設定距離 → 排除
        if distance > pct:
            continue

        # 越接近突破，分數越高
        score = round(
            max(
                0,
                100 - distance / pct * 100
            )
        )

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

            "high": round(
                previous_high,
                2
            ),

            "dist": round(
                distance,
                2
            ),

            "score": score,

            "grade": grade

        })

    results.sort(
        key=lambda x: (
            -x["score"],
            x["dist"]
        )
    )

    return {

        "date": today_string,

        "days": days,

        "pct": pct,

        "count": len(results),

        "results": results

    }


# =========================
# 網頁首頁
# =========================

HTML = r"""
<!doctype html>

<html lang="zh-Hant">

<head>

<meta charset="utf-8">

<meta name="viewport"
content="width=device-width,initial-scale=1">

<title>TW Breakout Radar</title>

<style>

*{
    box-sizing:border-box
}

body{
    margin:0;
    background:#0b0f14;
    color:#f4f7fa;
    font-family:
    -apple-system,
    BlinkMacSystemFont,
    "Noto Sans TC",
    sans-serif
}

.wrap{
    max-width:680px;
    margin:auto;
    padding:14px
}

.card{
    background:#121820;
    border:1px solid #28323d;
    border-radius:16px;
    padding:15px;
    margin-bottom:12px
}

.head{
    display:flex;
    justify-content:space-between;
    margin-bottom:14px;
    font-weight:900
}

.brand b{
    color:#62e0aa
}

.sub,
.rule,
.meta,
.reason,
.note{
    color:#87929d;
    font-size:11px;
    line-height:1.5
}

h1{
    font-size:21px;
    margin:0 0 5px
}

.grid{
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:9px;
    margin-top:13px
}

.label{
    font-size:11px;
    color:#9aa6b0
}

.input{
    width:100%;
    margin-top:6px;
    padding:12px;
    border-radius:10px;
    border:1px solid #34404c;
    background:#0b1016;
    color:#fff;
    font-size:16px;
    font-weight:700
}

.check{
    display:block;
    margin-top:12px;
    font-size:12px
}

.scan{
    width:100%;
    margin-top:12px;
    padding:12px;
    border:0;
    border-radius:10px;
    background:#62e0aa;
    font-weight:900
}

.tabs{
    display:flex;
    gap:6px;
    margin-bottom:10px
}

.tab{
    flex:1;
    padding:10px 3px;
    border-radius:9px;
    border:1px solid #2b3742;
    background:#151d25;
    color:#aab5be
}

.active{
    color:#62e0aa!important;
    border-color:#62e0aa!important
}

.empty{
    padding:14px;
    background:#0e141b;
    border-radius:10px;
    color:#87929d;
    font-size:12px
}

.stock{
    padding:13px 2px;
    border-bottom:1px solid #252e37
}

.top{
    display:flex;
    justify-content:space-between
}

.name{
    font-weight:850
}

.code{
    color:#9eabb6;
    margin-right:6px
}

.score{
    font-size:18px;
    font-weight:900;
    color:#62e0aa
}

.meta{
    display:flex;
    flex-wrap:wrap;
    gap:6px 12px;
    margin-top:7px
}

.near{
    color:#fff;
    font-weight:800
}

.reason{
    margin-top:6px
}

.note{
    margin-top:10px;
    color:#65717d
}

</style>

</head>

<body>

<main class="wrap">

<div class="head">

<div class="brand">
TW <b>BREAKOUT</b> RADAR
</div>

<div>🎯</div>

</div>

<section class="card">

<h1>台股突破雷達</h1>

<div class="sub">
找出尚未創高、但距離 X 日高點很近的股票。
</div>

<div class="grid">

<label class="label">

回溯高點（交易日）

<input
class="input"
id="days"
type="number"
value="20"
min="2">

</label>

<label class="label">

距離高點（%）

<input
class="input"
id="pct"
type="number"
value="10"
step=".1"
min=".1">

</label>

</div>

<label class="check">

<input
id="exclude"
type="checkbox"
checked>

排除已創 X 日新高

</label>

<div
class="rule"
id="rule">
</div>

<button
class="scan"
id="scan">

🔍 開始掃描

</button>

</section>

<section class="card">

<div class="tabs">

<button
class="tab active"
data-t="all">
全部
</button>

<button
class="tab"
data-t="a">
🟢 A級
</button>

<button
class="tab"
data-t="b">
🟡 B級
</button>

<button
class="tab"
data-t="c">
🔴 C級
</button>

</div>

<div
id="summary"
class="empty">

尚未掃描。

</div>

<div id="results"></div>

<div class="note">
資料來源：TWSE／TPEx。
條件：今日尚未創 X 日高點，
且距離前 X 個交易日高點不超過設定百分比。
</div>

</section>

</main>

<script>

const $ =
x => document.getElementById(x);

let tab = "all";

function rule(){

    let d =
    +$("days").value;

    let p =
    +$("pct").value;

    $("rule").textContent =
    `前 ${d} 個交易日高點；
    距離 ≤ ${p}%；高點不含今天。`;
}

async function scan(){

    let d =
    +$("days").value;

    let p =
    +$("pct").value;

    $("summary").textContent =
    "正在取得台股資料，請稍候…";

    $("results").innerHTML = "";

    try{

        const response =
        await fetch(
            `/api/scan?days=${d}&pct=${p}`
        );

        const data =
        await response.json();

        if(data.error){

            $("summary").textContent =
            data.error;

            return;
        }

        render(data);

    }catch(error){

        $("summary").textContent =
        "掃描失敗，請稍後再試。";

    }

}

function render(data){

    let r =
    data.results.filter(x =>

        tab === "all"
        || x.grade === tab

    );

    $("summary").textContent =
    `${data.date}｜條件 ${data.days} 日 / ${data.pct}%｜符合 ${data.count} 檔`;

    $("results").innerHTML =

    r.map(x => `

        <div class="stock">

            <div class="top">

                <div class="name">

                    <span class="code">
                        ${x.code}
                    </span>

                    ${x.name}

                </div>

                <div class="score">
                    ${x.score}
                </div>

            </div>

            <div class="meta">

                <span>
                    ${x.market}
                </span>

                <span>
                    現價 ${x.price}
                </span>

                <span>
                    ${data.days}日高 ${x.high}
                </span>

                <span class="near">
                    還需 +${x.dist}%
                </span>

            </div>

            <div class="reason">

                距離前 ${data.days} 日高點
                ${x.dist}%，
                尚未創新高。

            </div>

        </div>

    `).join("")

    ||

    '<div class="empty">沒有符合條件的股票。</div>';

}

$("days").oninput =
rule;

$("pct").oninput =
rule;

$("scan").onclick =
scan;

document
.querySelectorAll(".tab")
.forEach(button => {

    button.onclick = () => {

        document
        .querySelectorAll(".tab")
        .forEach(
            x =>
            x.classList.remove("active")
        );

        button.classList.add("active");

        tab =
        button.dataset.t;

        scan();

    };

});

rule();

</script>

</body>

</html>
"""


@app.route("/")
def home():

    return render_template_string(
        HTML
    )


# =========================
# API
# =========================

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

        result =
        scan_market(
            days,
            pct
        )

        return jsonify(result)

    except Exception as e:

        return jsonify({
            "error": str(e),
            "results": []
        }), 500


@app.route("/health")
def health():

    return jsonify({
        "status": "ok",
        "service": "TW Breakout Radar"
    })


# =========================
# 啟動
# =========================

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
