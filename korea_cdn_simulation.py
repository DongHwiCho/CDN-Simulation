import numpy as np
import random
import os
from collections import OrderedDict
from korean_geocoding.geocoding import KoreanGeocoding
import korean_geocoding.geocoding as kg_module

import matplotlib
matplotlib.use('Agg') # Headless environment support
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.colors as mcolors

# --- 한글 폰트 설정 (matplotlib 글자 깨짐 방지) ---
try:
    font_path = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
    fm.fontManager.addfont(font_path)
    plt.rcParams['font.family'] = 'Noto Sans CJK JP'
    plt.rcParams['axes.unicode_minus'] = False  # 마이너스 기호 깨짐 방지
    print("한글 폰트 설정 완료: Noto Sans CJK JP")
except Exception as e:
    print(f"한글 폰트 설정 중 오류 발생: {e}")

# --- 시뮬레이션 설정 ---
RANDOM_SEED = 42
NUM_REQUESTS = 100000  # 총 요청 수
CONTENT_COUNT = 5000   # 전체 콘텐츠 라이브러리 크기
ZIPF_ALPHA = 1.2       # Zipf 분포 지수

# 캐시 용량 (콘텐츠 개수 기준)
CAPACITY_LOCAL = 50       # L1 읍/면/동 (소용량 에지: 1%)
CAPACITY_REGIONAL = 300   # L2 시/군/구 (중용량 에지: 6%)
CAPACITY_NATIONAL = 1500  # L3 시/도 (대용량 광역 에지: 30%)

# 노드 구축 비용 계수 (가상 단위: 억 원)
COST_LOCAL_NODE = 5       # L1 노드당 비용
COST_REGIONAL_NODE = 25   # L2 노드당 비용
COST_NATIONAL_NODE = 120  # L3 노드당 비용

# --- 대한민국 실제 인구 데이터 ---
POPULATIONS = {
    "서울특별시": 9400000,
    "부산광역시": 3300000,
    "대구광역시": 2400000,
    "인천광역시": 3000000,
    "광주광역시": 1400000,
    "대전광역시": 1400000,
    "울산광역시": 1100000,
    "세종특별자치시": 390000,
    "경기도": 13600000,
    "강원도": 1530000,
    "충청북도": 1600000,
    "충청남도": 2120000,
    "전라북도": 1770000,
    "전라남도": 1810000,
    "경상북도": 2580000,
    "경상남도": 3270000,
    "제주특별자치도": 670000
}

class LRUCache:
    def __init__(self, capacity):
        self.capacity = capacity
        self.cache = OrderedDict()

    def get(self, key):
        if key in self.cache:
            self.cache.move_to_end(key)
            return True
        return False

    def put(self, key):
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            self.cache[key] = True
            if len(self.cache) > self.capacity:
                self.cache.popitem(last=False)

def haversine_distance(coord1, coord2):
    """두 위경도 좌표 간의 대원 거리(km) 계산"""
    lat1, lon1 = np.radians(coord1[0]), np.radians(coord1[1])
    lat2, lon2 = np.radians(coord2[0]), np.radians(coord2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2)**2
    c = 2 * np.arcsin(np.sqrt(a))
    return 6371.0 * c

# --- 위치 Fallback 처리 함수 ---
def get_l2_coordinates(kg, query, parent_coords):
    try:
        coords = kg.get_coordinates(query)
        if coords is not None:
            return coords
    except Exception:
        pass
    try:
        children = kg.get_under_districts(query)
        for child in children:
            try:
                coords = kg.get_coordinates(f"{query} {child}")
                if coords is not None:
                    return coords
            except Exception:
                pass
    except Exception:
        pass
    return parent_coords

def get_l1_coordinates(kg, query, parent_coords):
    try:
        coords = kg.get_coordinates(query)
        if coords is not None:
            return coords
    except Exception:
        pass
    parts = query.split(' ')
    if len(parts) >= 2:
        parent_query = ' '.join(parts[:-1])
        dong_name = parts[-1]
        try:
            sibling_names = kg.get_under_districts(parent_query)
            prefix = dong_name[:2]
            for sib in sibling_names:
                if sib != dong_name and sib.startswith(prefix):
                    try:
                        coords = kg.get_coordinates(f"{parent_query} {sib}")
                        if coords is not None:
                            return coords
                    except Exception:
                        pass
        except Exception:
            pass
    if parent_coords:
        angle = random.uniform(0, 2 * np.pi)
        dist_km = random.uniform(2.0, 3.5)
        lat_offset = (dist_km / 111.0) * np.sin(angle)
        lon_offset = (dist_km / (111.0 * np.cos(np.radians(parent_coords[0])))) * np.cos(angle)
        return (parent_coords[0] + lat_offset, parent_coords[1] + lon_offset)
    return None

# --- 계층 구조 데이터 생성 ---
print("1단계: korean-geocoding DB 가동 및 100% 실존하는 L3(시/도)->L2(시/군/구)->L1(읍/면/동) 위상 데이터 빌드 중...")
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

kg = KoreanGeocoding()
sido_keys = list(kg_module.SIDO_DICT.keys())

client_nodes = []
servers_l3 = {}
servers_l2 = {}
servers_l1 = {}

for sido in sido_keys:
    coords_l3 = kg.get_coordinates(sido)
    if coords_l3 is None:
        continue
        
    sido_pop = POPULATIONS.get(sido, 1000000)
    servers_l3[sido] = {"name": sido, "coords": coords_l3, "level": "L3"}
    
    if sido == "세종특별자치시":
        dongs = kg.get_under_districts(sido)
        l2_id = "Sejong_0"
        servers_l2[l2_id] = {"name": "세종특별자치시청", "coords": coords_l3, "l3_id": sido, "level": "L2"}
        
        valid_l1_count = 0
        for dong_name in dongs:
            coords_l1 = get_l1_coordinates(kg, f"{sido} {dong_name}", coords_l3)
            if coords_l1 is None:
                continue
                
            l1_id = f"{l2_id}_{valid_l1_count}"
            
            client_angle = random.uniform(0, 2 * np.pi)
            client_dist_km = random.uniform(1.2, 2.2)
            client_lat = (client_dist_km / 111.0) * np.sin(client_angle)
            client_lon = (client_dist_km / (111.0 * np.cos(np.radians(coords_l1[0])))) * np.cos(client_angle)
            client_coords = (coords_l1[0] + client_lat, coords_l1[1] + client_lon)
            
            servers_l1[l1_id] = {"name": f"{sido} {dong_name} 에지센터", "coords": coords_l1, "l2_id": l2_id, "l3_id": sido, "level": "L1"}
            
            client_nodes.append({
                "id": l1_id,
                "name": f"{sido} {dong_name}",
                "coords": coords_l1,
                "client_coords": client_coords,
                "pop": int(sido_pop / len(dongs)),
                "l2_id": l2_id,
                "l3_id": sido,
                "latencies_list_direct": [], "latencies_list_l3": [], "latencies_list_l2": [], "latencies_list_l1": [], "latencies_list_depth": [], "latencies_list_l1_l3": [], "latencies_list_l1_l2": [], "latencies_list_l2_l3": [],
                "ttff_list_direct": [], "ttff_list_l3": [], "ttff_list_l2": [], "ttff_list_l1": [], "ttff_list_depth": [], "ttff_list_l1_l3": [], "ttff_list_l1_l2": [], "ttff_list_l2_l3": [],
                "rebuff_list_direct": [], "rebuff_list_l3": [], "rebuff_list_l2": [], "rebuff_list_l1": [], "rebuff_list_depth": [], "rebuff_list_l1_l3": [], "rebuff_list_l1_l2": [], "rebuff_list_l2_l3": [],
                "hits": {"l3": 0, "l2": 0, "l1": 0},
                "depth_hits": {"l3": 0, "l2": 0, "l1": 0},
                "l1_l3_hits": {"l1": 0, "l3": 0},
                "l1_l2_hits": {"l1": 0, "l2": 0},
                "l2_l3_hits": {"l2": 0, "l3": 0},
                "total_requests": 0
            })
            valid_l1_count += 1
    else:
        districts = kg.get_under_districts(sido)
        for dist_name in districts:
            sub_dists = kg.get_under_districts(f"{sido} {dist_name}")
            has_gu = False
            if sub_dists:
                if any(sd.endswith('구') for sd in sub_dists):
                    has_gu = True
            
            if has_gu:
                for gu_name in sub_dists:
                    l2_id = f"{sido}_{dist_name}_{gu_name}"
                    coords_l2 = get_l2_coordinates(kg, f"{sido} {dist_name} {gu_name}", coords_l3)
                    servers_l2[l2_id] = {"name": f"{sido} {dist_name} {gu_name}청", "coords": coords_l2, "l3_id": sido, "level": "L2"}
                    
                    dongs = kg.get_under_districts(f"{sido} {dist_name} {gu_name}")
                    valid_l1_count = 0
                    for dong_name in dongs:
                        coords_l1 = get_l1_coordinates(kg, f"{sido} {dist_name} {gu_name} {dong_name}", coords_l2)
                        if coords_l1 is None:
                            continue
                            
                        l1_id = f"{l2_id}_{valid_l1_count}"
                        
                        client_angle = random.uniform(0, 2 * np.pi)
                        client_dist_km = random.uniform(1.2, 2.2)
                        client_lat = (client_dist_km / 111.0) * np.sin(client_angle)
                        client_lon = (client_dist_km / (111.0 * np.cos(np.radians(coords_l1[0])))) * np.cos(client_angle)
                        client_coords = (coords_l1[0] + client_lat, coords_l1[1] + client_lon)
                        
                        servers_l1[l1_id] = {"name": f"{sido} {dist_name} {gu_name} {dong_name} 에지센터", "coords": coords_l1, "l2_id": l2_id, "l3_id": sido, "level": "L1"}
                        
                        client_nodes.append({
                            "id": l1_id,
                            "name": f"{sido} {dist_name} {gu_name} {dong_name}",
                            "coords": coords_l1,
                            "client_coords": client_coords,
                            "pop": max(500, int((sido_pop / len(districts)) / (len(sub_dists) * len(dongs)))),
                            "l2_id": l2_id,
                            "l3_id": sido,
                            "latencies_list_direct": [], "latencies_list_l3": [], "latencies_list_l2": [], "latencies_list_l1": [], "latencies_list_depth": [], "latencies_list_l1_l3": [], "latencies_list_l1_l2": [], "latencies_list_l2_l3": [],
                            "ttff_list_direct": [], "ttff_list_l3": [], "ttff_list_l2": [], "ttff_list_l1": [], "ttff_list_depth": [], "ttff_list_l1_l3": [], "ttff_list_l1_l2": [], "ttff_list_l2_l3": [],
                            "rebuff_list_direct": [], "rebuff_list_l3": [], "rebuff_list_l2": [], "rebuff_list_l1": [], "rebuff_list_depth": [], "rebuff_list_l1_l3": [], "rebuff_list_l1_l2": [], "rebuff_list_l2_l3": [],
                            "hits": {"l3": 0, "l2": 0, "l1": 0},
                            "depth_hits": {"l3": 0, "l2": 0, "l1": 0},
                            "l1_l3_hits": {"l1": 0, "l3": 0},
                            "l1_l2_hits": {"l1": 0, "l2": 0},
                            "l2_l3_hits": {"l2": 0, "l3": 0},
                            "total_requests": 0
                        })
                        valid_l1_count += 1
            else:
                l2_id = f"{sido}_{dist_name}"
                coords_l2 = get_l2_coordinates(kg, f"{sido} {dist_name}", coords_l3)
                servers_l2[l2_id] = {"name": f"{sido} {dist_name}청", "coords": coords_l2, "l3_id": sido, "level": "L2"}
                
                dongs = sub_dists
                valid_l1_count = 0
                for dong_name in dongs:
                    coords_l1 = get_l1_coordinates(kg, f"{sido} {dist_name} {dong_name}", coords_l2)
                    if coords_l1 is None:
                        continue
                        
                    l1_id = f"{l2_id}_{valid_l1_count}"
                    
                    client_angle = random.uniform(0, 2 * np.pi)
                    client_dist_km = random.uniform(1.2, 2.2)
                    client_lat = (client_dist_km / 111.0) * np.sin(client_angle)
                    client_lon = (client_dist_km / (111.0 * np.cos(np.radians(coords_l1[0])))) * np.cos(client_angle)
                    client_coords = (coords_l1[0] + client_lat, coords_l1[1] + client_lon)
                    
                    servers_l1[l1_id] = {"name": f"{sido} {dist_name} {dong_name} 에지센터", "coords": coords_l1, "l2_id": l2_id, "l3_id": sido, "level": "L1"}
                    
                    client_nodes.append({
                        "id": l1_id,
                        "name": f"{sido} {dist_name} {dong_name}",
                        "coords": coords_l1,
                        "client_coords": client_coords,
                        "pop": max(500, int((sido_pop / len(districts)) / len(dongs))),
                        "l2_id": l2_id,
                        "l3_id": sido,
                        "latencies_list_direct": [], "latencies_list_l3": [], "latencies_list_l2": [], "latencies_list_l1": [], "latencies_list_depth": [], "latencies_list_l1_l3": [], "latencies_list_l1_l2": [], "latencies_list_l2_l3": [],
                        "ttff_list_direct": [], "ttff_list_l3": [], "ttff_list_l2": [], "ttff_list_l1": [], "ttff_list_depth": [], "ttff_list_l1_l3": [], "ttff_list_l1_l2": [], "ttff_list_l2_l3": [],
                        "rebuff_list_direct": [], "rebuff_list_l3": [], "rebuff_list_l2": [], "rebuff_list_l1": [], "rebuff_list_depth": [], "rebuff_list_l1_l3": [], "rebuff_list_l1_l2": [], "rebuff_list_l2_l3": [],
                        "hits": {"l3": 0, "l2": 0, "l1": 0},
                        "depth_hits": {"l3": 0, "l2": 0, "l1": 0},
                        "l1_l3_hits": {"l1": 0, "l3": 0},
                        "l1_l2_hits": {"l1": 0, "l2": 0},
                        "l2_l3_hits": {"l2": 0, "l3": 0},
                        "total_requests": 0
                    })
                    valid_l1_count += 1

print(f"-> 완성된 계층 트리 노드 수 - L3: {len(servers_l3)}개, L2: {len(servers_l2)}개, L1: {len(servers_l1)}개")

# 서울 중앙 오리진 서버 좌표
origin_coords = servers_l3["서울특별시"]["coords"]

# --- 시뮬레이션 환경 구축 및 캐시 초기화 ---
print(f"2단계: 캐시 및 비디오 QoS 시뮬레이션 가동 (총 요청: {NUM_REQUESTS}건)...")
cache_width_l3 = {l3_id: LRUCache(CAPACITY_NATIONAL) for l3_id in servers_l3}
cache_width_l2 = {l2_id: LRUCache(CAPACITY_REGIONAL) for l2_id in servers_l2}
cache_width_l1 = {l1_id: LRUCache(CAPACITY_LOCAL) for l1_id in servers_l1}

cache_depth_l3 = {l3_id: LRUCache(CAPACITY_NATIONAL) for l3_id in servers_l3}
cache_depth_l2 = {l2_id: LRUCache(CAPACITY_REGIONAL) for l2_id in servers_l2}
cache_depth_l1 = {l1_id: LRUCache(CAPACITY_LOCAL) for l1_id in servers_l1}

cache_l1_l3_l3 = {l3_id: LRUCache(CAPACITY_NATIONAL) for l3_id in servers_l3}
cache_l1_l3_l1 = {l1_id: LRUCache(CAPACITY_LOCAL) for l1_id in servers_l1}

cache_l1_l2_l2 = {l2_id: LRUCache(CAPACITY_REGIONAL) for l2_id in servers_l2}
cache_l1_l2_l1 = {l1_id: LRUCache(CAPACITY_LOCAL) for l1_id in servers_l1}

cache_l2_l3_l3 = {l3_id: LRUCache(CAPACITY_NATIONAL) for l3_id in servers_l3}
cache_l2_l3_l2 = {l2_id: LRUCache(CAPACITY_REGIONAL) for l2_id in servers_l2}

zipf_weights = 1.0 / (np.arange(1, CONTENT_COUNT + 1) ** ZIPF_ALPHA)
zipf_weights /= np.sum(zipf_weights)

l1_populations = [node["pop"] for node in client_nodes]
l1_probs = np.array(l1_populations) / sum(l1_populations)

content_requests = np.random.choice(range(CONTENT_COUNT), size=NUM_REQUESTS, p=zipf_weights)
node_requests = np.random.choice(range(len(client_nodes)), size=NUM_REQUESTS, p=l1_probs)

for i in range(NUM_REQUESTS):
    content_id = content_requests[i]
    node_idx = node_requests[i]
    node = client_nodes[node_idx]
    
    l1_id = node["id"]
    l2_id = node["l2_id"]
    l3_id = node["l3_id"]
    
    # 1. 오리진 직접 연결 (Direct)
    lat_direct = 3.0 + 0.04 * haversine_distance(node["client_coords"], origin_coords)
    ttff_direct = 3.5 * lat_direct + 30.0
    rebuff_direct = max(0.1, 1.0 + 0.08 * lat_direct + random.uniform(-0.1, 0.1))
    
    node["latencies_list_direct"].append(lat_direct)
    node["ttff_list_direct"].append(ttff_direct)
    node["rebuff_list_direct"].append(rebuff_direct)
    
    # 2. L3 에지 CDN (시/도 단위 - Width 단층형)
    l3_coords = servers_l3[l3_id]["coords"]
    l3_dist = haversine_distance(node["client_coords"], l3_coords)
    if cache_width_l3[l3_id].get(content_id):
        lat_l3 = 3.0 + 0.04 * l3_dist
        ttff_l3 = 3.5 * lat_l3 + 15.0
        rebuff_l3 = max(0.1, 0.3 + 0.08 * lat_l3 + random.uniform(-0.05, 0.05))
        node["hits"]["l3"] += 1
    else:
        cache_width_l3[l3_id].put(content_id)
        lat_l3 = (3.0 + 0.04 * l3_dist) + (3.0 + 0.04 * haversine_distance(l3_coords, origin_coords))
        ttff_l3 = 3.5 * lat_l3 + 15.0 + 30.0
        rebuff_l3 = max(0.1, 1.0 + 0.08 * lat_l3 + random.uniform(-0.1, 0.1))
        
    node["latencies_list_l3"].append(lat_l3)
    node["ttff_list_l3"].append(ttff_l3)
    node["rebuff_list_l3"].append(rebuff_l3)
    
    # 3. L2 에지 CDN (시/군/구 단위 - Width)
    l2_coords = servers_l2[l2_id]["coords"]
    l2_dist = haversine_distance(node["client_coords"], l2_coords)
    if cache_width_l2[l2_id].get(content_id):
        lat_l2 = 2.0 + 0.04 * l2_dist
        ttff_l2 = 3.5 * lat_l2 + 10.0
        rebuff_l2 = max(0.1, 0.2 + 0.08 * lat_l2 + random.uniform(-0.05, 0.05))
        node["hits"]["l2"] += 1
    else:
        cache_width_l2[l2_id].put(content_id)
        lat_l2 = (2.0 + 0.04 * l2_dist) + (3.0 + 0.04 * haversine_distance(l2_coords, origin_coords))
        ttff_l2 = 3.5 * lat_l2 + 10.0 + 30.0
        rebuff_l2 = max(0.1, 1.0 + 0.08 * lat_l2 + random.uniform(-0.1, 0.1))
        
    node["latencies_list_l2"].append(lat_l2)
    node["ttff_list_l2"].append(ttff_l2)
    node["rebuff_list_l2"].append(rebuff_l2)
    
    # 4. L1 에지 CDN (읍/면/동 단위 - Width)
    l1_coords = servers_l1[l1_id]["coords"]
    l1_dist = haversine_distance(node["client_coords"], l1_coords)
    if cache_width_l1[l1_id].get(content_id):
        lat_l1 = 1.0 + 0.04 * l1_dist
        ttff_l1 = 3.5 * lat_l1 + 5.0
        rebuff_l1 = max(0.1, 0.1 + 0.08 * lat_l1 + random.uniform(-0.02, 0.02))
        node["hits"]["l1"] += 1
    else:
        cache_width_l1[l1_id].put(content_id)
        lat_l1 = (1.0 + 0.04 * l1_dist) + (3.0 + 0.04 * haversine_distance(l1_coords, origin_coords))
        ttff_l1 = 3.5 * lat_l1 + 5.0 + 30.0
        rebuff_l1 = max(0.1, 1.0 + 0.08 * lat_l1 + random.uniform(-0.1, 0.1))
        
    node["latencies_list_l1"].append(lat_l1)
    node["ttff_list_l1"].append(ttff_l1)
    node["rebuff_list_l1"].append(rebuff_l1)
    
    # 5. 계층형 CDN (Depth: Client -> L1 -> L2 -> L3 -> Origin)
    lat_hop_l1 = 1.0 + 0.04 * l1_dist
    lat_hop_l2 = 1.0 + 0.04 * haversine_distance(l1_coords, l2_coords)
    lat_hop_l3 = 1.0 + 0.04 * haversine_distance(l2_coords, l3_coords)
    lat_hop_origin = 3.0 + 0.04 * haversine_distance(l3_coords, origin_coords)
    
    if cache_depth_l1[l1_id].get(content_id):
        lat_depth = lat_hop_l1
        ttff_depth = 3.5 * lat_depth + 5.0
        rebuff_depth = max(0.1, 0.1 + 0.08 * lat_depth + random.uniform(-0.02, 0.02))
        node["depth_hits"]["l1"] += 1
    elif cache_depth_l2[l2_id].get(content_id):
        lat_depth = lat_hop_l1 + lat_hop_l2
        ttff_depth = 3.5 * lat_depth + 5.0 + 10.0
        rebuff_depth = max(0.1, 0.2 + 0.08 * lat_depth + random.uniform(-0.05, 0.05))
        cache_depth_l1[l1_id].put(content_id)
        node["depth_hits"]["l2"] += 1
    elif cache_depth_l3[l3_id].get(content_id):
        lat_depth = lat_hop_l1 + lat_hop_l2 + lat_hop_l3
        ttff_depth = 3.5 * lat_depth + 5.0 + 10.0 + 15.0
        rebuff_depth = max(0.1, 0.3 + 0.08 * lat_depth + random.uniform(-0.05, 0.05))
        cache_depth_l2[l2_id].put(content_id)
        cache_depth_l1[l1_id].put(content_id)
        node["depth_hits"]["l3"] += 1
    else:
        lat_depth = lat_hop_l1 + lat_hop_l2 + lat_hop_l3 + lat_hop_origin
        ttff_depth = 3.5 * lat_depth + 5.0 + 10.0 + 15.0 + 30.0
        rebuff_depth = max(0.1, 1.0 + 0.08 * lat_depth + random.uniform(-0.1, 0.1))
        cache_depth_l3[l3_id].put(content_id)
        cache_depth_l2[l2_id].put(content_id)
        cache_depth_l1[l1_id].put(content_id)
        
    node["latencies_list_depth"].append(lat_depth)
    node["ttff_list_depth"].append(ttff_depth)
    node["rebuff_list_depth"].append(rebuff_depth)
    
    # 6. l1_l3계층형 CDN (Client -> L1 -> L3 -> Origin)
    lat_hop_l1_to_l3 = 1.0 + 0.04 * haversine_distance(l1_coords, l3_coords)
    if cache_l1_l3_l1[l1_id].get(content_id):
        lat_l1_l3 = lat_hop_l1
        ttff_l1_l3 = 3.5 * lat_l1_l3 + 5.0
        rebuff_l1_l3 = max(0.1, 0.1 + 0.08 * lat_l1_l3 + random.uniform(-0.02, 0.02))
        node["l1_l3_hits"]["l1"] += 1
    elif cache_l1_l3_l3[l3_id].get(content_id):
        lat_l1_l3 = lat_hop_l1 + lat_hop_l1_to_l3
        ttff_l1_l3 = 3.5 * lat_l1_l3 + 5.0 + 15.0
        rebuff_l1_l3 = max(0.1, 0.3 + 0.08 * lat_l1_l3 + random.uniform(-0.05, 0.05))
        cache_l1_l3_l1[l1_id].put(content_id)
        node["l1_l3_hits"]["l3"] += 1
    else:
        lat_l1_l3 = lat_hop_l1 + lat_hop_l1_to_l3 + lat_hop_origin
        ttff_l1_l3 = 3.5 * lat_l1_l3 + 5.0 + 15.0 + 30.0
        rebuff_l1_l3 = max(0.1, 1.0 + 0.08 * lat_l1_l3 + random.uniform(-0.1, 0.1))
        cache_l1_l3_l3[l3_id].put(content_id)
        cache_l1_l3_l1[l1_id].put(content_id)
        
    node["latencies_list_l1_l3"].append(lat_l1_l3)
    node["ttff_list_l1_l3"].append(ttff_l1_l3)
    node["rebuff_list_l1_l3"].append(rebuff_l1_l3)

    # 7. l1_l2계층형 CDN (Client -> L1 -> L2 -> Origin)
    lat_hop_l2_to_origin = 3.0 + 0.04 * haversine_distance(l2_coords, origin_coords)
    if cache_l1_l2_l1[l1_id].get(content_id):
        lat_l1_l2 = lat_hop_l1
        ttff_l1_l2 = 3.5 * lat_l1_l2 + 5.0
        rebuff_l1_l2 = max(0.1, 0.1 + 0.08 * lat_l1_l2 + random.uniform(-0.02, 0.02))
        node["l1_l2_hits"]["l1"] += 1
    elif cache_l1_l2_l2[l2_id].get(content_id):
        lat_l1_l2 = lat_hop_l1 + lat_hop_l2
        ttff_l1_l2 = 3.5 * lat_l1_l2 + 5.0 + 10.0
        rebuff_l1_l2 = max(0.1, 0.2 + 0.08 * lat_l1_l2 + random.uniform(-0.05, 0.05))
        cache_l1_l2_l1[l1_id].put(content_id)
        node["l1_l2_hits"]["l2"] += 1
    else:
        lat_l1_l2 = lat_hop_l1 + lat_hop_l2 + lat_hop_l2_to_origin
        ttff_l1_l2 = 3.5 * lat_l1_l2 + 5.0 + 10.0 + 30.0
        rebuff_l1_l2 = max(0.1, 1.0 + 0.08 * lat_l1_l2 + random.uniform(-0.1, 0.1))
        cache_l1_l2_l2[l2_id].put(content_id)
        cache_l1_l2_l1[l1_id].put(content_id)
        
    node["latencies_list_l1_l2"].append(lat_l1_l2)
    node["ttff_list_l1_l2"].append(ttff_l1_l2)
    node["rebuff_list_l1_l2"].append(rebuff_l1_l2)

    # 8. l2_l3계층형 CDN (Client -> L2 -> L3 -> Origin)
    lat_hop_l2_client = 2.0 + 0.04 * l2_dist
    lat_hop_l2_to_l3 = 1.0 + 0.04 * haversine_distance(l2_coords, l3_coords)
    if cache_l2_l3_l2[l2_id].get(content_id):
        lat_l2_l3 = lat_hop_l2_client
        ttff_l2_l3 = 3.5 * lat_l2_l3 + 10.0
        rebuff_l2_l3 = max(0.1, 0.2 + 0.08 * lat_l2_l3 + random.uniform(-0.05, 0.05))
        node["l2_l3_hits"]["l2"] += 1
    elif cache_l2_l3_l3[l3_id].get(content_id):
        lat_l2_l3 = lat_hop_l2_client + lat_hop_l2_to_l3
        ttff_l2_l3 = 3.5 * lat_l2_l3 + 10.0 + 15.0
        rebuff_l2_l3 = max(0.1, 0.3 + 0.08 * lat_l2_l3 + random.uniform(-0.05, 0.05))
        cache_l2_l3_l2[l2_id].put(content_id)
        node["l2_l3_hits"]["l3"] += 1
    else:
        lat_l2_l3 = lat_hop_l2_client + lat_hop_l2_to_l3 + lat_hop_origin
        ttff_l2_l3 = 3.5 * lat_l2_l3 + 10.0 + 15.0 + 30.0
        rebuff_l2_l3 = max(0.1, 1.0 + 0.08 * lat_l2_l3 + random.uniform(-0.1, 0.1))
        cache_l2_l3_l3[l3_id].put(content_id)
        cache_l2_l3_l2[l2_id].put(content_id)
        
    node["latencies_list_l2_l3"].append(lat_l2_l3)
    node["ttff_list_l2_l3"].append(ttff_l2_l3)
    node["rebuff_list_l2_l3"].append(rebuff_l2_l3)
    
    node["total_requests"] += 1

# --- 결과 요약 데이터 생성 ---
print("3단계: 시뮬레이션 결과 데이터 요약 및 시각화 준비...")
total_lats = {"direct": 0, "l3": 0, "l2": 0, "l1": 0, "depth": 0, "l1_l3": 0, "l1_l2": 0, "l2_l3": 0}
total_ttffs = {"direct": 0, "l3": 0, "l2": 0, "l1": 0, "depth": 0, "l1_l3": 0, "l1_l2": 0, "l2_l3": 0}
total_rebuffs = {"direct": 0, "l3": 0, "l2": 0, "l1": 0, "depth": 0, "l1_l3": 0, "l1_l2": 0, "l2_l3": 0}
total_hits = {"l3": 0, "l2": 0, "l1": 0}
total_depth_hits = {"l3": 0, "l2": 0, "l1": 0}
total_l1_l3_hits = {"l3": 0, "l1": 0}
total_l1_l2_hits = {"l2": 0, "l1": 0}
total_l2_l3_hits = {"l3": 0, "l2": 0}
total_req_count = 0

regional_results = {sido: {strat: [] for strat in ["direct", "l3", "l2", "l1", "depth", "l1_l3", "l1_l2", "l2_l3"]} for sido in servers_l3}
regional_rebuffs = {sido: {strat: [] for strat in ["direct", "l3", "l2", "l1", "depth", "l1_l3", "l1_l2", "l2_l3"]} for sido in servers_l3}

for node in client_nodes:
    req_count = node["total_requests"]
    sido = node["l3_id"]
    if req_count > 0:
        total_lats["direct"] += sum(node["latencies_list_direct"])
        total_lats["l3"] += sum(node["latencies_list_l3"])
        total_lats["l2"] += sum(node["latencies_list_l2"])
        total_lats["l1"] += sum(node["latencies_list_l1"])
        total_lats["depth"] += sum(node["latencies_list_depth"])
        total_lats["l1_l3"] += sum(node["latencies_list_l1_l3"])
        total_lats["l1_l2"] += sum(node["latencies_list_l1_l2"])
        total_lats["l2_l3"] += sum(node["latencies_list_l2_l3"])
        
        total_ttffs["direct"] += sum(node["ttff_list_direct"])
        total_ttffs["l3"] += sum(node["ttff_list_l3"])
        total_ttffs["l2"] += sum(node["ttff_list_l2"])
        total_ttffs["l1"] += sum(node["ttff_list_l1"])
        total_ttffs["depth"] += sum(node["ttff_list_depth"])
        total_ttffs["l1_l3"] += sum(node["ttff_list_l1_l3"])
        total_ttffs["l1_l2"] += sum(node["ttff_list_l1_l2"])
        total_ttffs["l2_l3"] += sum(node["ttff_list_l2_l3"])
        
        total_rebuffs["direct"] += sum(node["rebuff_list_direct"])
        total_rebuffs["l3"] += sum(node["rebuff_list_l3"])
        total_rebuffs["l2"] += sum(node["rebuff_list_l2"])
        total_rebuffs["l1"] += sum(node["rebuff_list_l1"])
        total_rebuffs["depth"] += sum(node["rebuff_list_depth"])
        total_rebuffs["l1_l3"] += sum(node["rebuff_list_l1_l3"])
        total_rebuffs["l1_l2"] += sum(node["rebuff_list_l1_l2"])
        total_rebuffs["l2_l3"] += sum(node["rebuff_list_l2_l3"])
        
        total_hits["l3"] += node["hits"]["l3"]
        total_hits["l2"] += node["hits"]["l2"]
        total_hits["l1"] += node["hits"]["l1"]
        
        total_depth_hits["l1"] += node["depth_hits"]["l1"]
        total_depth_hits["l2"] += node["depth_hits"]["l2"]
        total_depth_hits["l3"] += node["depth_hits"]["l3"]
        total_l1_l3_hits["l1"] += node["l1_l3_hits"]["l1"]
        total_l1_l3_hits["l3"] += node["l1_l3_hits"]["l3"]
        total_l1_l2_hits["l1"] += node["l1_l2_hits"]["l1"]
        total_l1_l2_hits["l2"] += node["l1_l2_hits"]["l2"]
        total_l2_l3_hits["l2"] += node["l2_l3_hits"]["l2"]
        total_l2_l3_hits["l3"] += node["l2_l3_hits"]["l3"]
        
        total_req_count += req_count
        
        for strat in ["direct", "l3", "l2", "l1", "depth", "l1_l3", "l1_l2", "l2_l3"]:
            regional_results[sido][strat].extend(node[f"latencies_list_{strat}"])
            regional_rebuffs[sido][strat].extend(node[f"rebuff_list_{strat}"])

# 글로벌 통계
global_avg_latency = {
    "direct": total_lats["direct"] / total_req_count,
    "l3": total_lats["l3"] / total_req_count,
    "l2": total_lats["l2"] / total_req_count,
    "l1": total_lats["l1"] / total_req_count,
    "depth": total_lats["depth"] / total_req_count,
    "l1_l3": total_lats["l1_l3"] / total_req_count,
    "l1_l2": total_lats["l1_l2"] / total_req_count,
    "l2_l3": total_lats["l2_l3"] / total_req_count,
}
global_avg_ttff = {
    "direct": total_ttffs["direct"] / total_req_count,
    "l3": total_ttffs["l3"] / total_req_count,
    "l2": total_ttffs["l2"] / total_req_count,
    "l1": total_ttffs["l1"] / total_req_count,
    "depth": total_ttffs["depth"] / total_req_count,
    "l1_l3": total_ttffs["l1_l3"] / total_req_count,
    "l1_l2": total_ttffs["l1_l2"] / total_req_count,
    "l2_l3": total_ttffs["l2_l3"] / total_req_count,
}
global_avg_rebuff = {
    "direct": total_rebuffs["direct"] / total_req_count,
    "l3": total_rebuffs["l3"] / total_req_count,
    "l2": total_rebuffs["l2"] / total_req_count,
    "l1": total_rebuffs["l1"] / total_req_count,
    "depth": total_rebuffs["depth"] / total_req_count,
    "l1_l3": total_rebuffs["l1_l3"] / total_req_count,
    "l1_l2": total_rebuffs["l1_l2"] / total_req_count,
    "l2_l3": total_rebuffs["l2_l3"] / total_req_count,
}
# 글로벌 캐시 적중률 및 오리진 부하 절감률 정의
global_hit_rate = {
    "direct": 0.0,
    "l3": (total_hits["l3"] / total_req_count) * 100.0,
    "l2": (total_hits["l2"] / total_req_count) * 100.0,
    "l1": (total_hits["l1"] / total_req_count) * 100.0,
    "depth": ((total_depth_hits["l1"] + total_depth_hits["l2"] + total_depth_hits["l3"]) / total_req_count) * 100.0,
    "l1_l3": ((total_l1_l3_hits["l1"] + total_l1_l3_hits["l3"]) / total_req_count) * 100.0,
    "l1_l2": ((total_l1_l2_hits["l1"] + total_l1_l2_hits["l2"]) / total_req_count) * 100.0,
    "l2_l3": ((total_l2_l3_hits["l2"] + total_l2_l3_hits["l3"]) / total_req_count) * 100.0,
}

cost_stats = {
    "direct": 0,
    "l3": len(servers_l3) * COST_NATIONAL_NODE,
    "l2": len(servers_l2) * COST_REGIONAL_NODE,
    "l1": len(servers_l1) * COST_LOCAL_NODE,
    "depth": (len(servers_l3) * COST_NATIONAL_NODE) + (len(servers_l2) * COST_REGIONAL_NODE) + (len(servers_l1) * COST_LOCAL_NODE),
    "l1_l3": (len(servers_l3) * COST_NATIONAL_NODE) + (len(servers_l1) * COST_LOCAL_NODE),
    "l1_l2": (len(servers_l2) * COST_REGIONAL_NODE) + (len(servers_l1) * COST_LOCAL_NODE),
    "l2_l3": (len(servers_l3) * COST_NATIONAL_NODE) + (len(servers_l2) * COST_REGIONAL_NODE)
}

# --- 4단계: Matplotlib을 활용한 정밀 정적 분석 차트 생성 ---
def generate_charts(lang='ko'):
    is_ko = (lang == 'ko')
    print(f"4단계: Matplotlib 기반 대한민국 지리/통계 그래프 ({lang}) 생성 중...")
    
    # 4-1단계: Matplotlib 기반 대한민국 지리 성능 격차 맵 생성
    fig, axs = plt.subplots(3, 3, figsize=(18, 18))
    
    if is_ko:
        strategies = [
            ("direct", "오리진 직접 연결 (No CDN)", axs[0, 0]),
            ("l3", "L3 에지 CDN (시/도 단위 - Width)", axs[0, 1]),
            ("l2", "L2 에지 CDN (시/군/구 단위 - Width)", axs[0, 2]),
            ("l1", "L1 에지 CDN (읍/면/동 단위 - Width)", axs[1, 0]),
            ("depth", "계층형 멀티티어 CDN (Depth)", axs[1, 1]),
            ("l1_l3", "계층형 CDN (L1 -> L3)", axs[1, 2]),
            ("l1_l2", "계층형 CDN (L1 -> L2)", axs[2, 0]),
            ("l2_l3", "계층형 CDN (L2 -> L3)", axs[2, 1]),
        ]
        pareto_title = "구축 비용 대비 RTT 성능 Pareto Frontier"
        pareto_xlabel = "구축 투자 비용 (억 원)"
        pareto_ylabel = "평균 응답 속도 (ms)"
        pareto_labels = ["Direct", "L3 에지", "L2 에지", "L2->L3 계층", "L1 에지", "L1->L3 계층", "L1->L2 계층", "Depth 계층"]
        main_title = "대한민국 계층형 CDN 6,487개 행정동 지리적 성능 격차 실증 분석"
        colorbar_label = '평균 응답 지연 시간 (Latency RTT ms) | 녹색(우수) <----> 적색(지연)'
    else:
        strategies = [
            ("direct", "Direct Connection (No CDN)", axs[0, 0]),
            ("l3", "L3 Edge CDN (Provincial - Width)", axs[0, 1]),
            ("l2", "L2 Edge CDN (Municipal - Width)", axs[0, 2]),
            ("l1", "L1 Edge CDN (Local Town - Width)", axs[1, 0]),
            ("depth", "Hierarchical CDN (Depth)", axs[1, 1]),
            ("l1_l3", "Hierarchical CDN (L1 -> L3)", axs[1, 2]),
            ("l1_l2", "Hierarchical CDN (L1 -> L2)", axs[2, 0]),
            ("l2_l3", "Hierarchical CDN (L2 -> L3)", axs[2, 1]),
        ]
        pareto_title = "RTT Latency vs Deployment Cost Pareto Frontier"
        pareto_xlabel = "Deployment Investment Cost (100M KRW)"
        pareto_ylabel = "Avg Response Time (ms)"
        pareto_labels = ["Direct", "L3 Edge", "L2 Edge", "L2->L3 Tier", "L1 Edge", "L1->L3 Tier", "L1->L2 Tier", "Depth Tier"]
        main_title = "Geographical CDN Latency Gap Analysis across 6,487 Towns in South Korea"
        colorbar_label = 'Avg Round Trip Time (Latency RTT ms) | Green (Fast) <----> Red (Slow)'

    norm = mcolors.Normalize(vmin=1.0, vmax=12.0)
    try:
        cmap = plt.colormaps['RdYlGn_r']
    except AttributeError:
        cmap = plt.cm.get_cmap('RdYlGn_r')

    client_lons = [n["client_coords"][1] for n in client_nodes]
    client_lats = [n["client_coords"][0] for n in client_nodes]

    for strat_id, title, ax in strategies:
        ax.set_facecolor('#0c1017')
        ax.set_title(title, fontsize=12, fontweight='bold', color='#f0f6fc', pad=10)
        
        lats_list = []
        for node in client_nodes:
            if node["total_requests"] > 0:
                avg_l = np.mean(node[f"latencies_list_{strat_id}"])
            else:
                avg_l = 3.0
            lats_list.append(avg_l)
            
        ax.scatter(client_lons, client_lats, c=lats_list, cmap=cmap, norm=norm, s=1.5, alpha=0.5, zorder=2)
        
        if strat_id == "l3":
            l3_lons = [v["coords"][1] for v in servers_l3.values()]
            l3_lats = [v["coords"][0] for v in servers_l3.values()]
            ax.scatter(l3_lons, l3_lats, color='#3498db', marker='s', s=45, edgecolor='#ffffff', linewidth=0.5, zorder=4)
        elif strat_id == "l2":
            l2_lons = [v["coords"][1] for v in servers_l2.values()]
            l2_lats = [v["coords"][0] for v in servers_l2.values()]
            ax.scatter(l2_lons, l2_lats, color='#2ecc71', marker='^', s=25, edgecolor='#ffffff', linewidth=0.4, zorder=4)
        elif strat_id == "depth":
            l3_lons = [v["coords"][1] for v in servers_l3.values()]
            l3_lats = [v["coords"][0] for v in servers_l3.values()]
            l2_lons = [v["coords"][1] for v in servers_l2.values()]
            l2_lats = [v["coords"][0] for v in servers_l2.values()]
            ax.scatter(l3_lons, l3_lats, color='#3498db', marker='s', s=45, edgecolor='#ffffff', linewidth=0.5, zorder=4)
            ax.scatter(l2_lons, l2_lats, color='#2ecc71', marker='^', s=25, edgecolor='#ffffff', linewidth=0.4, zorder=4)
        elif strat_id == "l1_l3":
            l3_lons = [v["coords"][1] for v in servers_l3.values()]
            l3_lats = [v["coords"][0] for v in servers_l3.values()]
            ax.scatter(l3_lons, l3_lats, color='#3498db', marker='s', s=45, edgecolor='#ffffff', linewidth=0.5, zorder=4)
        elif strat_id == "l1_l2":
            l2_lons = [v["coords"][1] for v in servers_l2.values()]
            l2_lats = [v["coords"][0] for v in servers_l2.values()]
            ax.scatter(l2_lons, l2_lats, color='#2ecc71', marker='^', s=25, edgecolor='#ffffff', linewidth=0.4, zorder=4)
        elif strat_id == "l2_l3":
            l3_lons = [v["coords"][1] for v in servers_l3.values()]
            l3_lats = [v["coords"][0] for v in servers_l3.values()]
            l2_lons = [v["coords"][1] for v in servers_l2.values()]
            l2_lats = [v["coords"][0] for v in servers_l2.values()]
            ax.scatter(l3_lons, l3_lats, color='#3498db', marker='s', s=45, edgecolor='#ffffff', linewidth=0.5, zorder=4)
            ax.scatter(l2_lons, l2_lats, color='#2ecc71', marker='^', s=25, edgecolor='#ffffff', linewidth=0.4, zorder=4)
            
        ax.scatter(origin_coords[1], origin_coords[0], color='#f1c40f', marker='*', s=150, edgecolor='#ffffff', linewidth=1.0, zorder=5)
        
        ax.set_xlim(124.5, 131.0)
        ax.set_ylim(33.0, 39.0)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_color('#2f3640')

    ax_eff = axs[1, 2]
    ax_eff.set_facecolor('#0c1017')
    ax_eff.set_title(pareto_title, fontsize=12, fontweight='bold', color='#f0f6fc', pad=10)

    # Sorted by cost: direct(0), l3(2040), l2(6250), l2_l3(8290), l1(32435), l1_l3(34475), l1_l2(38685), depth(40725)
    pareto_strats = ["direct", "l3", "l2", "l2_l3", "l1", "l1_l3", "l1_l2", "depth"]
    costs = [cost_stats[s] for s in pareto_strats]
    lats = [global_avg_latency[s] for s in pareto_strats]
    colors_eff = ['#e74c3c', '#3498db', '#2ecc71', '#95a5a6', '#9b59b6', '#e67e22', '#1abc9c', '#f1c40f']

    for k in range(len(pareto_strats)):
        ax_eff.scatter(costs[k], lats[k], color=colors_eff[k], s=120, edgecolor='white', linewidth=1.0, zorder=3, label=pareto_labels[k])
        ax_eff.text(costs[k] + 150, lats[k] + 0.1, pareto_labels[k], fontsize=9, color='#c9d1d9', fontweight='semibold')

    ax_eff.plot(costs, lats, color='#444d56', linestyle='--', linewidth=1.5, zorder=2)
    ax_eff.set_xlabel(pareto_xlabel, fontsize=10, color='#8b949e')
    ax_eff.set_ylabel(pareto_ylabel, fontsize=10, color='#8b949e')
    ax_eff.tick_params(colors='#8b949e', labelsize=9)
    ax_eff.grid(True, color='#21262d', linestyle=':', linewidth=0.8)
    for spine in ax_eff.spines.values():
        spine.set_color('#2f3640')

    plt.suptitle(main_title, fontsize=16, fontweight='bold', color='#ffffff', y=0.96)
    plt.tight_layout()
    fig.subplots_adjust(top=0.92, bottom=0.06)

    cbar_ax = fig.add_axes([0.15, 0.02, 0.7, 0.012])
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cbar_ax, orientation='horizontal')
    cb.set_label(colorbar_label, fontsize=11, fontweight='bold', labelpad=5, color='#ffffff')
    cb.ax.tick_params(labelsize=9, colors='#ffffff')

    map_png_path = f'/home/donghwi/cloud_network_project/korea_cdn_map_{lang}.png'
    plt.savefig(map_png_path, dpi=300, facecolor='#0c1017')
    plt.close()
    print(f"-> 지리 성능 맵 이미지({lang}) 저장 완료: {map_png_path}")

    # 4-1-1단계: 개별 지리 성능 맵 분할 생성
    for strat_id, title, _ in strategies:
        fig_single, ax_single = plt.subplots(figsize=(8, 8))
        ax_single.set_facecolor('#0c1017')
        ax_single.set_title(title, fontsize=14, fontweight='bold', color='#f0f6fc', pad=10)
        
        lats_list = []
        for node in client_nodes:
            if node["total_requests"] > 0:
                avg_l = np.mean(node[f"latencies_list_{strat_id}"])
            else:
                avg_l = 3.0
            lats_list.append(avg_l)
            
        sc = ax_single.scatter(client_lons, client_lats, c=lats_list, cmap=cmap, norm=norm, s=3.0, alpha=0.6, zorder=2)
        
        if strat_id == "l3":
            l3_lons = [v["coords"][1] for v in servers_l3.values()]
            l3_lats = [v["coords"][0] for v in servers_l3.values()]
            ax_single.scatter(l3_lons, l3_lats, color='#3498db', marker='s', s=80, edgecolor='#ffffff', linewidth=0.8, zorder=4)
        elif strat_id == "l2":
            l2_lons = [v["coords"][1] for v in servers_l2.values()]
            l2_lats = [v["coords"][0] for v in servers_l2.values()]
            ax_single.scatter(l2_lons, l2_lats, color='#2ecc71', marker='^', s=50, edgecolor='#ffffff', linewidth=0.6, zorder=4)
        elif strat_id == "depth":
            l3_lons = [v["coords"][1] for v in servers_l3.values()]
            l3_lats = [v["coords"][0] for v in servers_l3.values()]
            l2_lons = [v["coords"][1] for v in servers_l2.values()]
            l2_lats = [v["coords"][0] for v in servers_l2.values()]
            ax_single.scatter(l3_lons, l3_lats, color='#3498db', marker='s', s=80, edgecolor='#ffffff', linewidth=0.8, zorder=4)
            ax_single.scatter(l2_lons, l2_lats, color='#2ecc71', marker='^', s=50, edgecolor='#ffffff', linewidth=0.6, zorder=4)
        elif strat_id == "l1_l3":
            l3_lons = [v["coords"][1] for v in servers_l3.values()]
            l3_lats = [v["coords"][0] for v in servers_l3.values()]
            ax_single.scatter(l3_lons, l3_lats, color='#3498db', marker='s', s=80, edgecolor='#ffffff', linewidth=0.8, zorder=4)
        elif strat_id == "l1_l2":
            l2_lons = [v["coords"][1] for v in servers_l2.values()]
            l2_lats = [v["coords"][0] for v in servers_l2.values()]
            ax_single.scatter(l2_lons, l2_lats, color='#2ecc71', marker='^', s=50, edgecolor='#ffffff', linewidth=0.6, zorder=4)
        elif strat_id == "l2_l3":
            l3_lons = [v["coords"][1] for v in servers_l3.values()]
            l3_lats = [v["coords"][0] for v in servers_l3.values()]
            l2_lons = [v["coords"][1] for v in servers_l2.values()]
            l2_lats = [v["coords"][0] for v in servers_l2.values()]
            ax_single.scatter(l3_lons, l3_lats, color='#3498db', marker='s', s=80, edgecolor='#ffffff', linewidth=0.8, zorder=4)
            ax_single.scatter(l2_lons, l2_lats, color='#2ecc71', marker='^', s=50, edgecolor='#ffffff', linewidth=0.6, zorder=4)
            
        ax_single.scatter(origin_coords[1], origin_coords[0], color='#f1c40f', marker='*', s=200, edgecolor='#ffffff', linewidth=1.2, zorder=5)
        
        ax_single.set_xlim(124.5, 131.0)
        ax_single.set_ylim(33.0, 39.0)
        ax_single.set_xticks([])
        ax_single.set_yticks([])
        for spine in ax_single.spines.values():
            spine.set_color('#2f3640')
            
        cb_single = fig_single.colorbar(sc, ax=ax_single, orientation='horizontal', pad=0.05, shrink=0.8)
        cb_single.set_label(colorbar_label, fontsize=10, fontweight='bold', color='#ffffff')
        cb_single.ax.tick_params(labelsize=8, colors='#ffffff')
        fig_single.patch.set_facecolor('#0c1017')
        
        single_map_path = f'/home/donghwi/cloud_network_project/korea_cdn_map_{strat_id}_{lang}.png'
        plt.savefig(single_map_path, dpi=300, facecolor='#0c1017', bbox_inches='tight')
        plt.close(fig_single)
        print(f"-> 개별 지리 맵 이미지({strat_id}_{lang}) 저장 완료: {single_map_path}")

    # Pareto Frontier 단독 저장
    fig_pareto, ax_pareto = plt.subplots(figsize=(8, 6))
    ax_pareto.set_facecolor('#0c1017')
    ax_pareto.set_title(pareto_title, fontsize=14, fontweight='bold', color='#f0f6fc', pad=10)
    for k in range(len(pareto_strats)):
        ax_pareto.scatter(costs[k], lats[k], color=colors_eff[k], s=180, edgecolor='white', linewidth=1.2, zorder=3, label=pareto_labels[k])
        ax_pareto.text(costs[k] + 150, lats[k] + 0.1, pareto_labels[k], fontsize=10, color='#c9d1d9', fontweight='semibold')
    ax_pareto.plot(costs, lats, color='#444d56', linestyle='--', linewidth=2.0, zorder=2)
    ax_pareto.set_xlabel(pareto_xlabel, fontsize=11, color='#8b949e')
    ax_pareto.set_ylabel(pareto_ylabel, fontsize=11, color='#8b949e')
    ax_pareto.tick_params(colors='#8b949e', labelsize=10)
    ax_pareto.grid(True, color='#21262d', linestyle=':', linewidth=0.8)
    for spine in ax_pareto.spines.values():
        spine.set_color('#2f3640')
    fig_pareto.patch.set_facecolor('#0c1017')
    
    pareto_path = f'/home/donghwi/cloud_network_project/korea_cdn_map_pareto_{lang}.png'
    plt.savefig(pareto_path, dpi=300, facecolor='#0c1017', bbox_inches='tight')
    plt.close(fig_pareto)
    print(f"-> 개별 파레토 그래프 이미지(pareto_{lang}) 저장 완료: {pareto_path}")

    # 4-2단계: 통계 비교 및 결과 그래프 생성
    fig, axs = plt.subplots(2, 2, figsize=(14, 10))
    fig.patch.set_facecolor('#0c1017')

    # 차트 1: RTT / TTFF 비교
    ax = axs[0, 0]
    ax.set_facecolor('#0c1017')
    if is_ko:
        ax.set_title("아키텍처별 평균 RTT 및 TTFF 비교", fontsize=12, fontweight='bold', color='#f0f6fc')
        names = ["Direct", "L3 에지", "L2 에지", "L1 에지", "L2->L3", "L1->L3", "L1->L2", "Depth"]
        rtt_label = 'RTT (좌축)'
        ttff_label = 'TTFF (우축)'
        ylabel_rtt = "평균 응답 속도 RTT (ms)"
        ylabel_ttff = "첫 프레임 재생 시간 TTFF (ms)"
    else:
        ax.set_title("Average RTT and TTFF by Architecture", fontsize=12, fontweight='bold', color='#f0f6fc')
        names = ["Direct", "L3 Edge", "L2 Edge", "L1 Edge", "L2->L3", "L1->L3", "L1->L2", "Depth"]
        rtt_label = 'RTT (Left)'
        ttff_label = 'TTFF (Right)'
        ylabel_rtt = "Average Round Trip Time RTT (ms)"
        ylabel_ttff = "Time to First Frame TTFF (ms)"
        
    names_id = ["direct", "l3", "l2", "l1", "l2_l3", "l1_l3", "l1_l2", "depth"]
    avg_lats = [global_avg_latency[s] for s in names_id]
    avg_ttffs = [global_avg_ttff[s] for s in names_id]
    colors = ['#e74c3c', '#3498db', '#2ecc71', '#9b59b6', '#95a5a6', '#e67e22', '#1abc9c', '#f1c40f']

    x_indexes = np.arange(len(names))
    width = 0.35

    rects1 = ax.bar(x_indexes - width/2, avg_lats, width, label=rtt_label, color='#2ecc71', edgecolor='#2f3640', zorder=3)
    ax.set_ylabel(ylabel_rtt, color='#2ecc71')
    ax.tick_params(axis='y', labelcolor='#2ecc71', colors='#8b949e')

    ax2 = ax.twinx()
    rects2 = ax2.bar(x_indexes + width/2, avg_ttffs, width, label=ttff_label, color='#f1c40f', edgecolor='#2f3640', zorder=3)
    ax2.set_ylabel(ylabel_ttff, color='#f1c40f')
    ax2.tick_params(axis='y', labelcolor='#f1c40f', colors='#8b949e')

    ax.set_xticks(x_indexes)
    ax.set_xticklabels(names, color='#8b949e', fontsize=10)
    ax.grid(True, color='#21262d', linestyle=':', zorder=0)

    for rect in rects1:
        h = rect.get_height()
        ax.text(rect.get_x() + rect.get_width()/2., h + 0.15, f"{h:.2f}", ha='center', color='#2ecc71', fontweight='bold', fontsize=8.5)
    for rect in rects2:
        h = rect.get_height()
        ax2.text(rect.get_x() + rect.get_width()/2., h + 0.9, f"{h:.1f}", ha='center', color='#f1c40f', fontweight='bold', fontsize=8.5)
    for spine in ax.spines.values():
        spine.set_color('#2f3640')
    for spine in ax2.spines.values():
        spine.set_color('#2f3640')

    # 차트 2: 캐시 적중률 및 오리진 부하 절감률
    ax = axs[0, 1]
    ax.set_facecolor('#0c1017')
    if is_ko:
        ax.set_title("아키텍처별 캐시 적중률 및 오리진 부하 절감률", fontsize=12, fontweight='bold', color='#f0f6fc')
        hit_label = '적중률'
        offload_label = '오리진 부하 절감률'
        ylabel_ratio = "비율 (%)"
    else:
        ax.set_title("Cache Hit Rate and Origin Offload Rate by Architecture", fontsize=12, fontweight='bold', color='#f0f6fc')
        hit_label = 'Hit Rate'
        offload_label = 'Origin Offload Rate'
        ylabel_ratio = "Ratio (%)"

    names_hit_id = ["l3", "l2", "l1", "l2_l3", "l1_l3", "l1_l2", "depth"]
    hit_rates = [global_hit_rate[s] for s in names_hit_id]
    offload_rates = [global_hit_rate[s] for s in names_hit_id]

    x_indexes_hit = np.arange(len(names[1:]))
    width_hit = 0.35

    rects1_hit = ax.bar(x_indexes_hit - width_hit/2, hit_rates, width_hit, label=hit_label, color='#3498db', edgecolor='#2f3640', zorder=3)
    rects2_hit = ax.bar(x_indexes_hit + width_hit/2, offload_rates, width_hit, label=offload_label, color='#00d2d3', edgecolor='#2f3640', zorder=3)

    ax.set_ylabel(ylabel_ratio, color='#8b949e')
    ax.tick_params(colors='#8b949e', labelsize=10)
    ax.set_xticks(x_indexes_hit)
    ax.set_xticklabels(names[1:])
    ax.set_ylim(0, 105)
    ax.legend(facecolor='#0c1017', edgecolor='#2f3640', labelcolor='#c9d1d9', fontsize=9, loc='upper left')
    ax.grid(True, color='#21262d', linestyle=':', zorder=0)

    for rect in rects1_hit:
        h = rect.get_height()
        ax.text(rect.get_x() + rect.get_width()/2., h + 2.0, f"{h:.2f}%", ha='center', color='#3498db', fontweight='bold', fontsize=8.5)
    for rect in rects2_hit:
        h = rect.get_height()
        ax.text(rect.get_x() + rect.get_width()/2., h + 2.0, f"{h:.2f}%", ha='center', color='#00d2d3', fontweight='bold', fontsize=8.5)
    for spine in ax.spines.values():
        spine.set_color('#2f3640')

    # 차트 3: 재버퍼링 비율 비교
    ax = axs[1, 0]
    ax.set_facecolor('#0c1017')
    if is_ko:
        ax.set_title("아키텍처별 평균 재버퍼링 비율 비교", fontsize=12, fontweight='bold', color='#f0f6fc')
        ylabel_rebuff = "평균 재버퍼링 비율 (%)"
    else:
        ax.set_title("Average Re-buffering Ratio by Architecture", fontsize=12, fontweight='bold', color='#f0f6fc')
        ylabel_rebuff = "Average Re-buffering Ratio (%)"

    avg_rebuffs = [global_avg_rebuff[s] for s in ["direct", "l3", "l2", "l1", "l2_l3", "l1_l3", "l1_l2", "depth"]]
    rects_reb = ax.bar(names, avg_rebuffs, color=colors, edgecolor='#2f3640', width=0.45, zorder=3)
    ax.set_ylabel(ylabel_rebuff, color='#8b949e')
    ax.tick_params(colors='#8b949e', labelsize=10)
    ax.grid(True, color='#21262d', linestyle=':', zorder=0)
    ax.set_ylim(0, max(avg_rebuffs) * 1.25)
    for idx, v in enumerate(avg_rebuffs):
        ax.text(idx, v + 0.1, f"{v:.2f}%", ha='center', color='#f0f6fc', fontweight='bold', fontsize=10)
    for spine in ax.spines.values():
        spine.set_color('#2f3640')

    # 차트 4: 주요 거점 지역별 평균 재버퍼링 비율 비교
    ax = axs[1, 1]
    ax.set_facecolor('#0c1017')
    if is_ko:
        ax.set_title("주요 거점 지역별 평균 재버퍼링 비율 비교", fontsize=12, fontweight='bold', color='#f0f6fc')
        target_cities = ["서울특별시", "경기도", "대구광역시", "부산광역시", "제주특별자치도"]
        city_labels = ["서울", "경기", "대구", "부산", "제주도"]
        ylabel_city = "평균 재버퍼링 비율 (%)"
    else:
        ax.set_title("Average Re-buffering Ratio by Major Regions", fontsize=12, fontweight='bold', color='#f0f6fc')
        target_cities = ["서울특별시", "경기도", "대구광역시", "부산광역시", "제주특별자치도"]
        city_labels = ["Seoul", "Gyeonggi", "Daegu", "Busan", "Jeju"]
        ylabel_city = "Average Re-buffering Ratio (%)"

    x_indexes_city = np.arange(len(target_cities))
    width_city = 0.15

    width_city = 0.09
    for idx, strat in enumerate(["direct", "l3", "l2", "l1", "l2_l3", "l1_l3", "l1_l2", "depth"]):
        avg_vals = [np.mean(regional_rebuffs[c][strat]) if len(regional_rebuffs[c][strat]) > 0 else 0 for c in target_cities]
        ax.bar(x_indexes_city + (idx - 3.5) * width_city, avg_vals, width_city, label=names[idx], color=colors[idx], edgecolor='#2f3640')

    ax.set_xticks(x_indexes_city)
    ax.set_xticklabels(city_labels)
    ax.set_ylabel(ylabel_city, color='#8b949e')
    ax.tick_params(colors='#8b949e', labelsize=10)
    ax.legend(facecolor='#0c1017', edgecolor='#2f3640', labelcolor='#c9d1d9', fontsize=9)
    ax.grid(True, color='#21262d', linestyle=':', zorder=0)
    for spine in ax.spines.values():
        spine.set_color('#2f3640')

    if is_ko:
        plt.suptitle("대한민국 CDN 비디오 QoS 성능 시뮬레이션 결과 통계", fontsize=15, fontweight='bold', color='#ffffff', y=0.97)
    else:
        plt.suptitle("South Korea CDN Video QoS Simulation Statistics", fontsize=15, fontweight='bold', color='#ffffff', y=0.97)
        
    plt.tight_layout()
    fig.subplots_adjust(top=0.91)

    result_png_path = f'/home/donghwi/cloud_network_project/korea_cdn_result_{lang}.png'
    plt.savefig(result_png_path, dpi=300, facecolor='#0c1017')
    plt.close()
    print(f"-> 종합 통계 그래프 이미지({lang}) 저장 완료: {result_png_path}")

    # 4-2-1단계: 개별 통계 차트 분할 생성
    # 개별 차트 1: RTT & TTFF 비교
    fig1, ax1 = plt.subplots(figsize=(8, 6))
    fig1.patch.set_facecolor('#0c1017')
    ax1.set_facecolor('#0c1017')
    if is_ko:
        ax1.set_title("아키텍처별 평균 RTT 및 TTFF 비교", fontsize=14, fontweight='bold', color='#f0f6fc')
        ylabel_rtt = "평균 응답 속도 RTT (ms)"
        ylabel_ttff = "첫 프레임 재생 시간 TTFF (ms)"
    else:
        ax1.set_title("Average RTT and TTFF by Architecture", fontsize=14, fontweight='bold', color='#f0f6fc')
        ylabel_rtt = "Average Round Trip Time RTT (ms)"
        ylabel_ttff = "Time to First Frame TTFF (ms)"
    
    rects1 = ax1.bar(x_indexes - width/2, avg_lats, width, label=rtt_label, color='#2ecc71', edgecolor='#2f3640', zorder=3)
    ax1.set_ylabel(ylabel_rtt, color='#2ecc71')
    ax1.tick_params(axis='y', labelcolor='#2ecc71', colors='#8b949e')
    
    ax1_2 = ax1.twinx()
    rects2 = ax1_2.bar(x_indexes + width/2, avg_ttffs, width, label=ttff_label, color='#f1c40f', edgecolor='#2f3640', zorder=3)
    ax1_2.set_ylabel(ylabel_ttff, color='#f1c40f')
    ax1_2.tick_params(axis='y', labelcolor='#f1c40f', colors='#8b949e')
    
    ax1.set_xticks(x_indexes)
    ax1.set_xticklabels(names, color='#8b949e', fontsize=10)
    ax1.grid(True, color='#21262d', linestyle=':', zorder=0)
    for spine in ax1.spines.values():
        spine.set_color('#2f3640')
    for spine in ax1_2.spines.values():
        spine.set_color('#2f3640')
    for rect in rects1:
        h = rect.get_height()
        ax1.text(rect.get_x() + rect.get_width()/2., h + 0.15, f"{h:.2f}", ha='center', color='#2ecc71', fontweight='bold', fontsize=9)
    for rect in rects2:
        h = rect.get_height()
        ax1_2.text(rect.get_x() + rect.get_width()/2., h + 0.9, f"{h:.1f}", ha='center', color='#f1c40f', fontweight='bold', fontsize=9)
    
    chart1_path = f'/home/donghwi/cloud_network_project/korea_cdn_result_rtt_ttff_{lang}.png'
    plt.savefig(chart1_path, dpi=300, facecolor='#0c1017', bbox_inches='tight')
    plt.close(fig1)

    # 개별 차트 2: 캐시 적중률 & 오리진 부하 절감률
    fig2, ax2 = plt.subplots(figsize=(8, 6))
    fig2.patch.set_facecolor('#0c1017')
    ax2.set_facecolor('#0c1017')
    if is_ko:
        ax2.set_title("아키텍처별 캐시 적중률 및 오리진 부하 절감률", fontsize=14, fontweight='bold', color='#f0f6fc')
        ylabel_ratio = "비율 (%)"
    else:
        ax2.set_title("Cache Hit Rate and Origin Offload Rate by Architecture", fontsize=14, fontweight='bold', color='#f0f6fc')
        ylabel_ratio = "Ratio (%)"

    rects1_hit = ax2.bar(x_indexes_hit - width_hit/2, hit_rates, width_hit, label=hit_label, color='#3498db', edgecolor='#2f3640', zorder=3)
    rects2_hit = ax2.bar(x_indexes_hit + width_hit/2, offload_rates, width_hit, label=offload_label, color='#00d2d3', edgecolor='#2f3640', zorder=3)
    ax2.set_ylabel(ylabel_ratio, color='#8b949e')
    ax2.tick_params(colors='#8b949e', labelsize=10)
    ax2.set_xticks(x_indexes_hit)
    ax2.set_xticklabels(names[1:])
    ax2.set_ylim(0, 105)
    ax2.legend(facecolor='#0c1017', edgecolor='#2f3640', labelcolor='#c9d1d9', fontsize=10)
    ax2.grid(True, color='#21262d', linestyle=':', zorder=0)
    for spine in ax2.spines.values():
        spine.set_color('#2f3640')
    for rect in rects1_hit:
        h = rect.get_height()
        ax2.text(rect.get_x() + rect.get_width()/2., h + 2.0, f"{h:.1f}%", ha='center', color='#3498db', fontweight='bold', fontsize=9)
    for rect in rects2_hit:
        h = rect.get_height()
        ax2.text(rect.get_x() + rect.get_width()/2., h + 2.0, f"{h:.1f}%", ha='center', color='#00d2d3', fontweight='bold', fontsize=9)
    
    chart2_path = f'/home/donghwi/cloud_network_project/korea_cdn_result_hit_offload_{lang}.png'
    plt.savefig(chart2_path, dpi=300, facecolor='#0c1017', bbox_inches='tight')
    plt.close(fig2)

    # 개별 차트 3: 재버퍼링 비율 비교
    fig3, ax3 = plt.subplots(figsize=(8, 6))
    fig3.patch.set_facecolor('#0c1017')
    ax3.set_facecolor('#0c1017')
    if is_ko:
        ax3.set_title("아키텍처별 평균 재버퍼링 비율 비교", fontsize=14, fontweight='bold', color='#f0f6fc')
        ylabel_rebuff = "평균 재버퍼링 비율 (%)"
    else:
        ax3.set_title("Average Re-buffering Ratio by Architecture", fontsize=14, fontweight='bold', color='#f0f6fc')
        ylabel_rebuff = "Average Re-buffering Ratio (%)"

    rects_reb = ax3.bar(names, avg_rebuffs, color=colors, edgecolor='#2f3640', width=0.45, zorder=3)
    ax3.set_ylabel(ylabel_rebuff, color='#8b949e')
    ax3.tick_params(colors='#8b949e', labelsize=10)
    ax3.grid(True, color='#21262d', linestyle=':', zorder=0)
    ax3.set_ylim(0, max(avg_rebuffs) * 1.25)
    for spine in ax3.spines.values():
        spine.set_color('#2f3640')
    for idx, v in enumerate(avg_rebuffs):
        ax3.text(idx, v + 0.1, f"{v:.2f}%", ha='center', color='#f0f6fc', fontweight='bold', fontsize=10)
        
    chart3_path = f'/home/donghwi/cloud_network_project/korea_cdn_result_rebuffering_{lang}.png'
    plt.savefig(chart3_path, dpi=300, facecolor='#0c1017', bbox_inches='tight')
    plt.close(fig3)

    # 개별 차트 4: 주요 거점 지역별 평균 재버퍼링 비율 비교
    fig4, ax4 = plt.subplots(figsize=(8, 6))
    fig4.patch.set_facecolor('#0c1017')
    ax4.set_facecolor('#0c1017')
    if is_ko:
        ax4.set_title("주요 거점 지역별 평균 재버퍼링 비율 비교", fontsize=14, fontweight='bold', color='#f0f6fc')
        ylabel_city = "평균 재버퍼링 비율 (%)"
    else:
        ax4.set_title("Average Re-buffering Ratio by Major Regions", fontsize=14, fontweight='bold', color='#f0f6fc')
        ylabel_city = "Average Re-buffering Ratio (%)"

    width_city = 0.09
    for idx, strat in enumerate(["direct", "l3", "l2", "l1", "l2_l3", "l1_l3", "l1_l2", "depth"]):
        avg_vals = [np.mean(regional_rebuffs[c][strat]) if len(regional_rebuffs[c][strat]) > 0 else 0 for c in target_cities]
        ax4.bar(x_indexes_city + (idx - 3.5) * width_city, avg_vals, width_city, label=names[idx], color=colors[idx], edgecolor='#2f3640')
    ax4.set_xticks(x_indexes_city)
    ax4.set_xticklabels(city_labels)
    ax4.set_ylabel(ylabel_city, color='#8b949e')
    ax4.tick_params(colors='#8b949e', labelsize=10)
    ax4.legend(facecolor='#0c1017', edgecolor='#2f3640', labelcolor='#c9d1d9', fontsize=10)
    ax4.grid(True, color='#21262d', linestyle=':', zorder=0)
    for spine in ax4.spines.values():
        spine.set_color('#2f3640')
        
    chart4_path = f'/home/donghwi/cloud_network_project/korea_cdn_result_regional_rebuff_{lang}.png'
    plt.savefig(chart4_path, dpi=300, facecolor='#0c1017', bbox_inches='tight')
    plt.close(fig4)
    print(f"-> 개별 결과 통계 차트 이미지들({lang}) 생성 완료!")

# 루프를 돌려 ko와 en 모두 생성
generate_charts('ko')
generate_charts('en')

# 하위 호환성을 위해 기본명 파일도 ko 차트에서 복사 생성
import shutil
shutil.copy('/home/donghwi/cloud_network_project/korea_cdn_map_ko.png', '/home/donghwi/cloud_network_project/korea_cdn_map.png')
shutil.copy('/home/donghwi/cloud_network_project/korea_cdn_result_ko.png', '/home/donghwi/cloud_network_project/korea_cdn_result.png')

# 아티팩트 복사 기능 추가
artifact_dir = '/home/donghwi/.gemini/antigravity-cli/brain/21aedd55-43a5-420e-b722-9c5a4be1bd05'
if os.path.exists(artifact_dir):
    shutil.copy('/home/donghwi/cloud_network_project/korea_cdn_map_ko.png', os.path.join(artifact_dir, 'korea_cdn_map_ko.png'))
    shutil.copy('/home/donghwi/cloud_network_project/korea_cdn_map_en.png', os.path.join(artifact_dir, 'korea_cdn_map_en.png'))
    shutil.copy('/home/donghwi/cloud_network_project/korea_cdn_result_ko.png', os.path.join(artifact_dir, 'korea_cdn_result_ko.png'))
    shutil.copy('/home/donghwi/cloud_network_project/korea_cdn_result_en.png', os.path.join(artifact_dir, 'korea_cdn_result_en.png'))
    shutil.copy('/home/donghwi/cloud_network_project/korea_cdn_map.png', os.path.join(artifact_dir, 'korea_cdn_map.png'))
    shutil.copy('/home/donghwi/cloud_network_project/korea_cdn_result.png', os.path.join(artifact_dir, 'korea_cdn_result.png'))

    # 개별 분할 이미지들 복사 (한글/영어 모두)
    for lang in ['ko', 'en']:
        # 개별 지도 복사
        for strat in ['direct', 'l3', 'l2', 'l1', 'depth', 'l1_l3', 'l1_l2', 'l2_l3']:
            map_name = f'korea_cdn_map_{strat}_{lang}.png'
            src_map = os.path.join('/home/donghwi/cloud_network_project', map_name)
            if os.path.exists(src_map):
                shutil.copy(src_map, os.path.join(artifact_dir, map_name))
        
        # 파레토 프런티어 복사
        pareto_name = f'korea_cdn_map_pareto_{lang}.png'
        src_pareto = os.path.join('/home/donghwi/cloud_network_project', pareto_name)
        if os.path.exists(src_pareto):
            shutil.copy(src_pareto, os.path.join(artifact_dir, pareto_name))
            
        # 개별 결과 차트 복사
        for chart in ['rtt_ttff', 'hit_offload', 'rebuffering', 'regional_rebuff']:
            chart_name = f'korea_cdn_result_{chart}_{lang}.png'
            src_chart = os.path.join('/home/donghwi/cloud_network_project', chart_name)
            if os.path.exists(src_chart):
                shutil.copy(src_chart, os.path.join(artifact_dir, chart_name))

    print("-> Artifacts 디렉토리에 모든 개별 및 종합 이미지 복사 완료!")

print("korea_cdn_simulation.py 완료! 이미지들이 성공적으로 생성되었습니다.")
