import os
import requests
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)


# ==========================================
# 核心業務邏輯：YouBike 搜尋與路徑規劃演算法 
# ==========================================

def fetch_tdx_station_data():
    """取得 TDX YouBike 站點基本資料aaa"""
    print("[後端日誌] 呼叫 TDX API 取得站點資訊...")

    # TODO: 這裡實際串接 TDX API
    # 例如：
    #   app_id = os.getenv('TDX_APP_ID')
    #   app_key = os.getenv('TDX_APP_KEY')
    #   呼叫 TDX 官網授權 jwt 或直接帶 app_id/app_key
    #   並取得 Station 資料與 Availability 資料

    return [
        {
            "StationUID": "0001",
            "StationName": {"Zh_tw": "捷運中山站"},
            "StationPosition": {"PositionLat": 25.0522, "PositionLon": 121.5245},
            "ServiceType": 1,
        }
    ]


def fetch_tdx_availability_data():
    """取得 TDX YouBike 即時可用車輛與車位狀態"""
    print("[後端日誌] 呼叫 TDX API 取得可用車資訊...")

    # TODO: 實際串接 TDX API
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
    """整合站點資料與即時可用性"""
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
    """依據人數與即時車位預測過濾站點"""
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
    """
    綜合考量所有條件的演算法
    """
    print(f"\n===== [演算法啟動] 開始規劃 {start_loc} -> {end_loc} =====")
    print(f"參數限制: 步行最多 {walk_min} 分鐘 | 人數: {people_count} 人")
    print(f"使用者偏好: 車種={bike_pref} | 權重={route_pref} | 30分補助={need_discount}")

    stations = merge_tdx_data(fetch_tdx_station_data(), fetch_tdx_availability_data())
    usable_stations = filter_stations(stations, people_count, need_discount)

    print(f"[計算中] 共有 {len(usable_stations)} 個符合條件的站點可供規劃")
    print("[計算中] 正在計算平坦度權重與 30 分鐘補助轉乘點...")

    result_summary = {
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
    return result_summary


# ==========================================
# 網頁前端 API 路由（給你的夥伴串接用）
# ==========================================


@app.route('/')
def index():
    return send_file('index.html')


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


# ==========================================
# 終端機純文字運行模式（供你單獨開發測試）
# ==========================================


def run_terminal_mode():
    print("==================================================")
    print("【第一頁：基本條件】")
    start = input("請輸入起點座標或地名 (預設: 台北車站): ") or "台北車站"
    end = input("請輸入終點座標或地名 (預設: 西門町): ") or "西門町"
    walk = int(input("允許步行最多幾分鐘 (預設: 10): ") or 10)
    people = int(input("乘車人數 (預設: 1): ") or 1)
    predict = input("是否啟用即時車位預測 (Y/N, 預設: Y): ") or "Y"
    need_predict = True if predict.strip().upper() == "Y" else False

    print("\n【第二頁：進階偏好】")
    bike = input("車種偏好 (1: 優先 2.0E, 2: 一般 2.0, 預設: 1): ") or "1"
    bike_pref = "2.0E" if bike == "1" else "2.0"
    route = input("路徑權重 (1: 最快抵達, 2: 平坦優先, 預設: 2): ") or "2"
    route_pref = "fast" if route == "1" else "flat"
    discount = input("是否啟用 30 分鐘免費提醒 (Y/N, 預設: Y): ") or "Y"
    need_discount = True if discount.strip().upper() == "Y" else False

    final_result = plan_best_route(start, end, walk, people, bike_pref, route_pref, need_discount)

    print("\n================ 搜尋結果運行結果 ================")
    print(f"總預估時間: {final_result['total_time']}")
    print(f"提醒通知: {final_result['alert']}")
    print("詳細路徑規劃:")
    for idx, step in enumerate(final_result['recommended_route'], 1):
        print(f"  步驟 {idx}. [{step['type']}] ({step['duration']}) - {step['desc']}")
    print("==================================================")


if __name__ == '__main__':
    mode = input("請選擇運行模式 (1: 終端機純文字測試, 2: 啟動後端 API 伺服器): ")
    if mode.strip() == "1":
        run_terminal_mode()
    else:
        print("啟動 Flask 後端伺服器中... 夥伴的前端現在可以連線到 http://127.0.0.1:5000/api/search")
        app.run(debug=True, host='0.0.0.0', port=5000)
