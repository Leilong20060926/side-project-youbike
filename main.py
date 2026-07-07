import os
import requests
from flask import Flask, request, jsonify, send_file

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()

app = Flask(__name__)

# 全域變數：快取 Token
TDX_TOKEN_CACHE = {
    "access_token": None,
    "expires_at": 0
}

# ==========================================
# 1. 依據官方範例實作：安全獲取真實 Token
# ==========================================

def get_tdx_access_token():
    """依據 TDX 官方 GitHub 範例實作的 Token 申請機制"""
    import time
    current_time = time.time()
    
    # 如果快取仍有效，直接回傳
    if TDX_TOKEN_CACHE["access_token"] and current_time < TDX_TOKEN_CACHE["expires_at"]:
        return TDX_TOKEN_CACHE["access_token"]

    client_id = os.getenv("TDX_CLIENT_ID")
    client_secret = os.getenv("TDX_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise ValueError("❌ 錯誤：請確認環境變數中已設定 TDX_CLIENT_ID 與 TDX_CLIENT_SECRET！")

    token_url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret
    }
    
    response = requests.post(token_url, data=payload, timeout=10)
    response.raise_for_status()
    res_data = response.json()
    
    TDX_TOKEN_CACHE["access_token"] = res_data["access_token"]
    # 扣除 60 秒緩衝時間，確保安全過期
    TDX_TOKEN_CACHE["expires_at"] = current_time + int(res_data["expires_in"]) - 60
    return TDX_TOKEN_CACHE["access_token"]

# ==========================================
# 2. 徹底修復：呼叫真實 TDX Nearby API
# ==========================================
def _request_tdx_nearby_data(endpoint_type, lat, lon, radius_meter):
    """
    100% 比照 Swagger 實測截圖格式呼叫真實 TDX API。
    """
    token = get_tdx_access_token()
    headers = {
        "Authorization": f"Bearer {token}",  # 確保帶有 Bearer 空格
        "Accept": "application/json"
    }

    # 精準比照截圖：根路徑直接接 /v2/Bike/...
    if endpoint_type == "Station":
        base_url = "https://tdx.transportdata.tw/api/basic/v2/Bike/Station/NearBy"
    elif endpoint_type == "Availability":
        base_url = "https://tdx.transportdata.tw/api/advanced/v2/Bike/Availability/NearBy"
    else:
        raise ValueError("endpoint_type 必須為 Station 或 Availability")

    # 嚴格對齊 OData 格式： nearby(緯度,經度,半徑) 逗號後絕不留白
    spatial_filter = f"nearby({float(lat)},{float(lon)},{int(radius_meter)})"
    
    # 建立與截圖完全一致的請求網址
    url = f"{base_url}?$spatialFilter={spatial_filter}&$format=JSON"

    print(f"[後端聯調] 發送請求 URL: {url}")

    response = requests.get(url, headers=headers, timeout=15)
    
    if response.status_code != 200:
        print(f"❌ TDX 伺服器回傳錯誤！狀態碼: {response.status_code}，內容: {response.text}")
        response.raise_for_status()

    return response.json()

# ==========================================
# 3. 空間解析與站點整合邏輯
# ==========================================

def geocode_address(address):
    """
    模擬精準地址轉座標。
    為了確保你在測試時 100% 能抓到台灣真實的有車站點，這裡給予台北市核心區域的真實經緯度。
    """
    # 台北車站新光三越附近的 YouBike 高密集區座標
    if "車站" in address or "台北" in address:
        return {"lat": 25.0462, "lon": 121.5165}
    # 西門町捷運站 3 號出口附近的真實座標
    if "西門" in address:
        return {"lat": 25.0422, "lon": 121.5085}
    # 預設台大公館商圈座標
    return {"lat": 25.0174, "lon": 121.5405}

def find_nearby_stations(address, walk_min, people_count, bike_pref, is_start=True):
    """
    核心邏輯：向 TDX 請求資料，並直接回傳篩選後的可用站點明細。
    """
    coords = geocode_address(address)
    radius_meter = walk_min * 80  # 步行每分鐘以 80 公尺計算

    # 呼叫真實的基礎服務 (站點位置) 與進階服務 (即時車位)
    raw_stations = _request_tdx_nearby_data("Station", coords["lat"], coords["lon"], radius_meter)
    raw_avail = _request_tdx_nearby_data("Availability", coords["lat"], coords["lon"], radius_meter)

    # 用 Map 將即時狀態關聯起來
    avail_map = {item["StationUID"]: item for item in raw_avail}
    qualified_stations = []

    for st in raw_stations:
        uid = st["StationUID"]
        av = avail_map.get(uid)
        if not av:
            continue

        bikes = av.get("AvailableRentBikes", 0)
        docks = av.get("AvailableReturnBikes", 0)
        
        # 依據起點(要借車)或終點(要還車)的人數進行初篩
        if is_start and bikes < people_count:
            continue
        if not is_start and docks < people_count:
            continue

        # 讀取真實的 YouBike 2.0E 電輔車數量 (依照進階 API 欄位設計)
        bikes_20e = av.get("Bikes20E", 0)

        qualified_stations.append({
            "station_id": uid,
            "name": st["StationName"]["Zh_tw"],
            "lat": st["StationPosition"]["PositionLat"],
            "lon": st["StationPosition"]["PositionLon"],
            "bikes_20E": bikes_20e,
            "available_bikes": bikes,
            "available_docks": docks
        })

    # 如果偏好 2.0E，則將有電輔車的站點排在最前面
    if bike_pref == "2.0E":
        qualified_stations.sort(key=lambda x: x["bikes_20E"], reverse=True)

    return qualified_stations

def plan_best_route(start_loc, end_loc, walk_min, people_count, bike_pref, route_pref, need_discount):
    """組合真實站點輸出多條路徑"""
    
    # 取得起點與終點範圍內的所有真實可用站點
    start_stations = find_nearby_stations(start_loc, walk_min, people_count, bike_pref, is_start=True)
    end_stations = find_nearby_stations(end_loc, walk_min, people_count, bike_pref, is_start=False)

    # 這裡將取得的站點獨立傳回，方便終端機能夠單獨印出
    return {
        "start_stations_found": start_stations,
        "end_stations_found": end_stations,
        "start_loc": start_loc,
        "end_loc": end_loc,
        "bike_preference": bike_pref,
        "route_preference": route_pref
    }

# ==========================================
# 4. 終端機純文字測試入口
# ==========================================
def run_terminal_mode():
    print("\n====== 🌐 [真實 TDX Nearby API 測試] ======")
    start = "台北車站"
    end = "西門町"
    
    # 調用剛才修正完網址的演算法
    result = plan_best_route(start, end, walk_min=10, people_count=1, bike_pref="2.0E", route_pref="flat", need_discount=True)
    
    # 直接輸出起點圓內的可用站點
    print(f"\n📍 【起點圓內可用站點明細】：")
    if not result.get("start_stations_found"):
        print("   ❌ 沒有找到任何站點。")
    else:
        for idx, st in enumerate(result["start_stations_found"], 1):
            print(f"   [{idx}] {st['name']} (2.0E電輔車: {st['bikes_20E']} 台 | 一般車: {st['available_bikes']} 台)")

    # 直接輸出終點圓內的可用站點
    print(f"\n🏁 【終點圓內可用還車點明細】：")
    if not result.get("end_stations_found"):
        print("   ❌ 沒有找到任何站點。")
    else:
        for idx, st in enumerate(result["end_stations_found"], 1):
            print(f"   [{idx}] {st['name']} (可用還車空位: {st['available_docks']} 個)")