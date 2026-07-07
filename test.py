import os
import secrets

from flask import Flask, request, jsonify, send_from_directory, session
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)

# session 需要一把固定的 secret_key，否則每次重啟 process 都會換一把，
# 使用者的登入 session 會全部失效。正式環境請用環境變數注入固定值。
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))

GOOGLE_CLIENT_ID = os.getenv(
    "GOOGLE_CLIENT_ID",
    "424327968016-1p0rlo8hdl5skgrn8su81fsqog3qcccs.apps.googleusercontent.com",
)

# Demo 用的記憶體儲存區：用 Google sub (使用者唯一 ID) 當 key 存進度。
# 正式環境請換成資料庫（SQLite/Postgres/Firestore...），process 重啟資料就會消失。
USER_PROGRESS_STORE = {}

google_request_adapter = google_requests.Request()


def fetch_tdx_station_data():
    return [
        {
            "StationUID": "0001",
            "StationName": {"Zh_tw": "捷運中山站"},
            "StationPosition": {"PositionLat": 25.0522, "PositionLon": 121.5245},
            "ServiceType": 1,
        }
    ]


def fetch_tdx_availability_data():
    return [
        {
            "StationUID": "0001",
            "AvailableRentBikes": 5,
            "AvailableReturnBikes": 12,
            "StationAddress": "台北市大同區",
            "ServiceStatus": 1,
        }
    ]


def merge_tdx_data(stations, availability):
    availability_map = {item["StationUID"]: item for item in availability}
    merged = []
    for station in stations:
        uid = station.get("StationUID")
        avail = availability_map.get(uid, {})
        merged.append(
            {
                "station_id": uid,
                "name": station.get("StationName", {}).get("Zh_tw", "Unknown"),
                "lat": station.get("StationPosition", {}).get("PositionLat"),
                "lon": station.get("StationPosition", {}).get("PositionLon"),
                "bikes": avail.get("AvailableRentBikes", 0),
                "docks": avail.get("AvailableReturnBikes", 0),
                "service_status": avail.get("ServiceStatus", 0),
                "type": "2.0E",
                "slope": 2,
            }
        )
    return merged


def filter_stations(stations, people_count, require_real_time):
    filtered = []
    for station in stations:
        if station["bikes"] < 3:
            continue
        if station["bikes"] < people_count:
            continue
        full_rate = 0.5
        if require_real_time and full_rate > 0.8:
            continue
        filtered.append(station)
    return filtered


def plan_best_route(start_loc, end_loc, walk_min, people_count, bike_pref, route_pref, need_discount):
    stations = merge_tdx_data(fetch_tdx_station_data(), fetch_tdx_availability_data())
    usable_stations = filter_stations(stations, people_count, need_discount)
    return {
        "status": "success",
        "recommended_route": [
            {"type": "walk", "duration": "5 mins", "desc": "從起點步行至最近有車站點"},
            {"type": "ride", "duration": "22 mins", "desc": "騎乘 YouBike 2.0E（避開陡坡平坦路徑）"},
            {"type": "walk", "duration": "3 mins", "desc": "還車後步行至終點"},
        ],
        "total_time": "30 mins",
        "alert": "提示：預估騎乘時間 22 分鐘，在 30 分鐘免費優惠時間內，免中途還車。",
        "stations_checked": len(usable_stations),
    }


@app.route('/api/google-config')
def api_google_config():
    return jsonify({"client_id": GOOGLE_CLIENT_ID})


# ─────────────────────────────
#  Google 登入：後端驗證 + session
# ─────────────────────────────
@app.route('/api/auth/google', methods=['POST'])
def api_auth_google():
    data = request.get_json(silent=True) or {}
    credential = data.get('credential')
    if not credential:
        return jsonify({"status": "error", "message": "缺少 credential"}), 400

    try:
        # 這一步會向 Google 驗證 JWT 的簽章、audience(client_id)、issuer、是否過期，
        # 前端自己 atob() 解碼只是「看得到內容」，並不代表這個 token 是合法、未被竄改的。
        payload = google_id_token.verify_oauth2_token(
            credential, google_request_adapter, GOOGLE_CLIENT_ID
        )
    except ValueError as e:
        return jsonify({"status": "error", "message": f"Token 驗證失敗: {e}"}), 401

    user = {
        "sub": payload.get("sub"),
        "email": payload.get("email"),
        "name": payload.get("name") or payload.get("given_name") or "Google User",
        "picture": payload.get("picture"),
    }

    # 建立伺服器端 session（Flask 會用簽章過的 cookie 存 session id，
    # 使用者關掉分頁再回來、重新整理，只要 cookie 還在就維持登入狀態）
    session['user'] = user
    session.permanent = True

    return jsonify({"status": "success", "user": user})


@app.route('/api/auth/me')
def api_auth_me():
    user = session.get('user')
    if not user:
        return jsonify({"status": "error", "message": "未登入"}), 401
    return jsonify({"status": "success", "user": user})


@app.route('/api/auth/logout', methods=['POST'])
def api_auth_logout():
    session.pop('user', None)
    return jsonify({"status": "success"})


# ─────────────────────────────
#  進度存 / 讀（示範用記憶體儲存，重啟會清空）
# ─────────────────────────────
@app.route('/api/progress', methods=['GET'])
def api_progress_get():
    user = session.get('user')
    if not user:
        return jsonify({"status": "error", "message": "未登入"}), 401
    progress = USER_PROGRESS_STORE.get(user['sub'])
    return jsonify({"status": "success", "progress": progress})


@app.route('/api/progress', methods=['POST'])
def api_progress_save():
    user = session.get('user')
    if not user:
        return jsonify({"status": "error", "message": "未登入"}), 401
    data = request.get_json(silent=True) or {}
    USER_PROGRESS_STORE[user['sub']] = data.get('progress')
    return jsonify({"status": "success"})


@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'test2.html')


@app.route('/test2.html')
def test2_page():
    return send_from_directory(BASE_DIR, 'test2.html')


@app.route('/api/search', methods=['POST'])
def api_search():
    data = request.get_json() or {}
    start_loc = data.get('start_loc')
    end_loc = data.get('end_loc')
    walk_min = int(data.get('walk_min', 10))
    people_count = int(data.get('people_count', 1))
    bike_pref = data.get('bike_pref', '2.0E')
    route_pref = data.get('route_pref', 'flat')
    need_discount = bool(data.get('need_discount', True))
    result = plan_best_route(start_loc, end_loc, walk_min, people_count, bike_pref, route_pref, need_discount)
    return jsonify(result)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)