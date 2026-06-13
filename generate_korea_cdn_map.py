import numpy as np
import json
import random
import os
import time
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
        # Hit
        lat_l3 = 3.0 + 0.04 * l3_dist
        ttff_l3 = 3.5 * lat_l3 + 15.0
        rebuff_l3 = max(0.1, 0.3 + 0.08 * lat_l3 + random.uniform(-0.05, 0.05))
        node["hits"]["l3"] += 1
    else:
        # Miss
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
        # Hit
        lat_l2 = 2.0 + 0.04 * l2_dist
        ttff_l2 = 3.5 * lat_l2 + 10.0
        rebuff_l2 = max(0.1, 0.2 + 0.08 * lat_l2 + random.uniform(-0.05, 0.05))
        node["hits"]["l2"] += 1
    else:
        # Miss
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
        # Hit
        lat_l1 = 1.0 + 0.04 * l1_dist
        ttff_l1 = 3.5 * lat_l1 + 5.0
        rebuff_l1 = max(0.1, 0.1 + 0.08 * lat_l1 + random.uniform(-0.02, 0.02))
        node["hits"]["l1"] += 1
    else:
        # Miss
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
        # L1 Hit
        lat_depth = lat_hop_l1
        ttff_depth = 3.5 * lat_depth + 5.0
        rebuff_depth = max(0.1, 0.1 + 0.08 * lat_depth + random.uniform(-0.02, 0.02))
        node["depth_hits"]["l1"] += 1
    elif cache_depth_l2[l2_id].get(content_id):
        # L1 Miss, L2 Hit
        lat_depth = lat_hop_l1 + lat_hop_l2
        ttff_depth = 3.5 * lat_depth + 5.0 + 10.0
        rebuff_depth = max(0.1, 0.2 + 0.08 * lat_depth + random.uniform(-0.05, 0.05))
        cache_depth_l1[l1_id].put(content_id)
        node["depth_hits"]["l2"] += 1
    elif cache_depth_l3[l3_id].get(content_id):
        # L1 Miss, L2 Miss, L3 Hit
        lat_depth = lat_hop_l1 + lat_hop_l2 + lat_hop_l3
        ttff_depth = 3.5 * lat_depth + 5.0 + 10.0 + 15.0
        rebuff_depth = max(0.1, 0.3 + 0.08 * lat_depth + random.uniform(-0.05, 0.05))
        cache_depth_l2[l2_id].put(content_id)
        cache_depth_l1[l1_id].put(content_id)
        node["depth_hits"]["l3"] += 1
    else:
        # All Miss
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
client_json_list = []
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
    if req_count == 0:
        node_lat_dir = 3.0 + 0.04 * haversine_distance(node["client_coords"], origin_coords)
        latencies = {"direct": node_lat_dir, "l3": 5.0, "l2": 4.0, "l1": 3.0, "depth": 2.0, "l1_l3": 2.5, "l1_l2": 2.3, "l2_l3": 3.5}
        ttffs = {"direct": 45.0, "l3": 35.0, "l2": 30.0, "l1": 25.0, "depth": 20.0, "l1_l3": 22.0, "l1_l2": 21.0, "l2_l3": 28.0}
        rebuffs = {"direct": 2.0, "l3": 1.2, "l2": 1.0, "l1": 2.0, "depth": 0.5, "l1_l3": 0.8, "l1_l2": 0.7, "l2_l3": 1.1}
        hit_rates = {"l3": 85.0, "l2": 70.0, "l1": 30.0, "depth": 85.0, "l1_l3": 85.0, "l1_l2": 75.0, "l2_l3": 80.0}
        depth_hits_detail = {"l1": 0, "l2": 0, "l3": 0}
        l1_l3_hits_detail = {"l1": 0, "l3": 0}
        l1_l2_hits_detail = {"l1": 0, "l2": 0}
        l2_l3_hits_detail = {"l2": 0, "l3": 0}
    else:
        latencies = {
            "direct": np.mean(node["latencies_list_direct"]),
            "l3": np.mean(node["latencies_list_l3"]),
            "l2": np.mean(node["latencies_list_l2"]),
            "l1": np.mean(node["latencies_list_l1"]),
            "depth": np.mean(node["latencies_list_depth"]),
            "l1_l3": np.mean(node["latencies_list_l1_l3"]),
            "l1_l2": np.mean(node["latencies_list_l1_l2"]),
            "l2_l3": np.mean(node["latencies_list_l2_l3"])
        }
        ttffs = {
            "direct": np.mean(node["ttff_list_direct"]),
            "l3": np.mean(node["ttff_list_l3"]),
            "l2": np.mean(node["ttff_list_l2"]),
            "l1": np.mean(node["ttff_list_l1"]),
            "depth": np.mean(node["ttff_list_depth"]),
            "l1_l3": np.mean(node["ttff_list_l1_l3"]),
            "l1_l2": np.mean(node["ttff_list_l1_l2"]),
            "l2_l3": np.mean(node["ttff_list_l2_l3"])
        }
        rebuffs = {
            "direct": np.mean(node["rebuff_list_direct"]),
            "l3": np.mean(node["rebuff_list_l3"]),
            "l2": np.mean(node["rebuff_list_l2"]),
            "l1": np.mean(node["rebuff_list_l1"]),
            "depth": np.mean(node["rebuff_list_depth"]),
            "l1_l3": np.mean(node["rebuff_list_l1_l3"]),
            "l1_l2": np.mean(node["rebuff_list_l1_l2"]),
            "l2_l3": np.mean(node["rebuff_list_l2_l3"])
        }
        hit_rates = {
            "l3": (node["hits"]["l3"] / req_count) * 100.0,
            "l2": (node["hits"]["l2"] / req_count) * 100.0,
            "l1": (node["hits"]["l1"] / req_count) * 100.0,
            "depth": ((node["depth_hits"]["l1"] + node["depth_hits"]["l2"] + node["depth_hits"]["l3"]) / req_count) * 100.0,
            "l1_l3": ((node["l1_l3_hits"]["l1"] + node["l1_l3_hits"]["l3"]) / req_count) * 100.0,
            "l1_l2": ((node["l1_l2_hits"]["l1"] + node["l1_l2_hits"]["l2"]) / req_count) * 100.0,
            "l2_l3": ((node["l2_l3_hits"]["l2"] + node["l2_l3_hits"]["l3"]) / req_count) * 100.0
        }
        depth_hits_detail = {
            "l1": (node["depth_hits"]["l1"] / req_count * 100.0),
            "l2": (node["depth_hits"]["l2"] / req_count * 100.0),
            "l3": (node["depth_hits"]["l3"] / req_count * 100.0)
        }
        l1_l3_hits_detail = {
            "l1": (node["l1_l3_hits"]["l1"] / req_count * 100.0),
            "l3": (node["l1_l3_hits"]["l3"] / req_count * 100.0)
        }
        l1_l2_hits_detail = {
            "l1": (node["l1_l2_hits"]["l1"] / req_count * 100.0),
            "l2": (node["l1_l2_hits"]["l2"] / req_count * 100.0)
        }
        l2_l3_hits_detail = {
            "l2": (node["l2_l3_hits"]["l2"] / req_count * 100.0),
            "l3": (node["l2_l3_hits"]["l3"] / req_count * 100.0)
        }
        
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
        
    client_json_list.append({
        "id": node["id"],
        "name": node["name"],
        "lat": node["client_coords"][0], # Client 실 위도
        "lon": node["client_coords"][1], # Client 실 경도
        "server_lat": node["coords"][0], # L1 Server 실 위도
        "server_lon": node["coords"][1], # L1 Server 실 경도
        "pop": node["pop"],
        "l2_id": node["l2_id"],
        "l3_id": node["l3_id"],
        "latencies": latencies,
        "ttffs": ttffs,
        "rebuffs": rebuffs,
        "hit_rates": hit_rates,
        "requests": req_count,
        "depth_hits_detail": depth_hits_detail,
        "l1_l3_hits_detail": l1_l3_hits_detail,
        "l1_l2_hits_detail": l1_l2_hits_detail,
        "l2_l3_hits_detail": l2_l3_hits_detail
    })

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

# 비용 및 노드 수
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

node_count_stats = {
    "direct": 0,
    "l3": len(servers_l3),
    "l2": len(servers_l2),
    "l1": len(servers_l1),
    "depth": len(servers_l3) + len(servers_l2) + len(servers_l1),
    "l1_l3": len(servers_l3) + len(servers_l1),
    "l1_l2": len(servers_l2) + len(servers_l1),
    "l2_l3": len(servers_l3) + len(servers_l2)
}

strategy_metadata = {
    "direct": {
        "ko": {
            "title": "오리진 직접 연결",
            "latency": f"{global_avg_latency['direct']:.2f} ms",
            "hit": "0.00 %",
            "cost": "0억 원",
            "nodes": "0개",
            "ttff": f"{global_avg_ttff['direct']:.1f} ms",
            "rebuff": f"{global_avg_rebuff['direct']:.2f} %",
            "offload": "0.00 %",
            "desc": "CDN 에지 노드를 구축하지 않고 모든 트래픽이 서울 오리진 서버로 직접 다이렉트 전달됩니다. 지리적 거리가 먼 제주, 전남, 경상도 등 도서/외곽 지역의 지연 시간이 극심해 지역간 정보격차가 심화됩니다."
        },
        "en": {
            "title": "Direct Connection",
            "latency": f"{global_avg_latency['direct']:.2f} ms",
            "hit": "0.00 %",
            "cost": "0 Billion KRW",
            "nodes": "0 Nodes",
            "ttff": f"{global_avg_ttff['direct']:.1f} ms",
            "rebuff": f"{global_avg_rebuff['direct']:.2f} %",
            "offload": "0.00 %",
            "desc": "No CDN edge nodes are built, and all traffic is routed directly to the Seoul Origin server. Network latency is severe in remote and coastal areas like Jeju, Jeonnam, and Gyeongsang provinces due to geographic distance, widening the regional digital divide."
        }
    },
    "l3": {
        "ko": {
            "title": "L3 에지 (시/도 단위 CDN - Width)",
            "latency": f"{global_avg_latency['l3']:.2f} ms",
            "hit": f"{global_hit_rate['l3']:.2f} %",
            "cost": f"{cost_stats['l3']:,d}억 원",
            "nodes": f"{node_count_stats['l3']}개 (전국 광역시/도)",
            "ttff": f"{global_avg_ttff['l3']:.1f} ms",
            "rebuff": f"{global_avg_rebuff['l3']:.2f} %",
            "offload": f"{global_hit_rate['l3']:.2f} %",
            "desc": "전국 17개 주요 광역지자체(서울, 경기, 제주 등) 단위 거점에 대형 시/도 에지 캐시 노드를 배치합니다. 트래픽 밀집도가 높아 캐시 효율이 우수하나 에지로부터 개별 거실(Client)까지 물리적 거리가 멀어 RTT 단축 효과가 중간에 머무릅니다."
        },
        "en": {
            "title": "L3 Edge (Provincial CDN - Width)",
            "latency": f"{global_avg_latency['l3']:.2f} ms",
            "hit": f"{global_hit_rate['l3']:.2f} %",
            "cost": f"{cost_stats['l3']:,d} Billion KRW",
            "nodes": f"{node_count_stats['l3']} Nodes (Provincial HQ)",
            "ttff": f"{global_avg_ttff['l3']:.1f} ms",
            "rebuff": f"{global_avg_rebuff['l3']:.2f} %",
            "offload": f"{global_hit_rate['l3']:.2f} %",
            "desc": "Deploys large provincial edge caches at 17 major regional centers (Seoul, Gyeonggi, Jeju, etc.). The cache efficiency is outstanding due to high traffic density, but because the physical distance from edges to individual clients remains large, the RTT reduction is moderate."
        }
    },
    "l2": {
        "ko": {
            "title": "L2 에지 (시/군/구 단위 CDN - Width)",
            "latency": f"{global_avg_latency['l2']:.2f} ms",
            "hit": f"{global_hit_rate['l2']:.2f} %",
            "cost": f"{cost_stats['l2']:,d}억 원",
            "nodes": f"{node_count_stats['l2']}개 (전국 시/군/구)",
            "ttff": f"{global_avg_ttff['l2']:.1f} ms",
            "rebuff": f"{global_avg_rebuff['l2']:.2f} %",
            "offload": f"{global_hit_rate['l2']:.2f} %",
            "desc": "전국 250개 기초지자체(시/군/구) 단위로 에지 노드를 완전 분배합니다. 읍면동 단위보다 캐시 적중률이 우수하면서 물리적 거리를 상시 좁힙니다. 미스 시에는 각 군/구 서버에서 서울 오리진으로 다이렉트 통신하는 수평 구조(Width)입니다."
        },
        "en": {
            "title": "L2 Edge (Municipal CDN - Width)",
            "latency": f"{global_avg_latency['l2']:.2f} ms",
            "hit": f"{global_hit_rate['l2']:.2f} %",
            "cost": f"{cost_stats['l2']:,d} Billion KRW",
            "nodes": f"{node_count_stats['l2']} Nodes (Si/Gun/Gu HQ)",
            "ttff": f"{global_avg_ttff['l2']:.1f} ms",
            "rebuff": f"{global_avg_rebuff['l2']:.2f} %",
            "offload": f"{global_hit_rate['l2']:.2f} %",
            "desc": "Deploys edge caches at 250 municipal centers (Si/Gun/Gu). It offers better cache hit rates than Dong-level caches while constantly reducing physical distance to clients. In case of cache miss, it communicates directly with Seoul Origin in a horizontal layout."
        }
    },
    "l1": {
        "ko": {
            "title": "L1 에지 (읍/면/동 단위 CDN - Width)",
            "latency": f"{global_avg_latency['l1']:.2f} ms",
            "hit": f"{global_hit_rate['l1']:.2f} %",
            "cost": f"{cost_stats['l1']:,d}억 원",
            "nodes": f"{node_count_stats['l1']}개 (전국 읍/면/동)",
            "ttff": f"{global_avg_ttff['l1']:.1f} ms",
            "rebuff": f"{global_avg_rebuff['l1']:.2f} %",
            "offload": f"{global_hit_rate['l1']:.2f} %",
            "desc": "전국 약 6,487개 동/읍/면에 초정밀 밀착 에지를 구성합니다. 히트 시 초저지연 통신(1.5ms 미만)을 보장하나 캐시 풀링 상실로 적중률이 낮아 미스 시 바로 서울 오리진으로 직행하는 Width 특성상 RTT 패널티가 큽니다."
        },
        "en": {
            "title": "L1 Edge (Local Town CDN - Width)",
            "latency": f"{global_avg_latency['l1']:.2f} ms",
            "hit": f"{global_hit_rate['l1']:.2f} %",
            "cost": f"{cost_stats['l1']:,d} Billion KRW",
            "nodes": f"{node_count_stats['l1']} Nodes (Eup/Myeon/Dong)",
            "ttff": f"{global_avg_ttff['l1']:.1f} ms",
            "rebuff": f"{global_avg_rebuff['l1']:.2f} %",
            "offload": f"{global_hit_rate['l1']:.2f} %",
            "desc": "Deploys hyper-local edge nodes across 6,487 towns. It guarantees ultra-low latency (under 1.5ms) on cache hit. However, due to cache pooling loss, hit rate is very low, and cache miss forces direct routing to Seoul, creating a high latency penalty."
        }
    },
    "depth": {
        "ko": {
            "title": "계층형 멀티티어 CDN (Depth)",
            "latency": f"{global_avg_latency['depth']:.2f} ms",
            "hit": f"{global_hit_rate['depth']:.2f} %",
            "cost": f"{cost_stats['depth']:,d}억 원",
            "nodes": f"{node_count_stats['depth']}개 (L3+L2+L1 전체)",
            "ttff": f"{global_avg_ttff['depth']:.1f} ms",
            "rebuff": f"{global_avg_rebuff['depth']:.2f} %",
            "offload": f"{global_hit_rate['depth']:.2f} %",
            "desc": "L1(읍면동), L2(시군구), L3(시도) 노드를 수직적 계층으로 전부 가동하는 Depth 아키텍처입니다. Client -> L1(동네) -> L2(구청) -> L3(도청) -> Origin(서울)의 폭포수형 탐색 경로를 타게 됩니다. L1 미스 시 오리진으로 가지 않고 상위 캐시(L2, L3)를 순차 탐색하므로, 오리진 백홀 부하를 제거하고 전반적인 응답 시간을 4ms 대로 급감시킵니다."
        },
        "en": {
            "title": "Multi-tier Hierarchical CDN (Depth)",
            "latency": f"{global_avg_latency['depth']:.2f} ms",
            "hit": f"{global_hit_rate['depth']:.2f} %",
            "cost": f"{cost_stats['depth']:,d} Billion KRW",
            "nodes": f"{node_count_stats['depth']} Nodes (L1+L2+L3 Total)",
            "ttff": f"{global_avg_ttff['depth']:.1f} ms",
            "rebuff": f"{global_avg_rebuff['depth']:.2f} %",
            "offload": f"{global_hit_rate['depth']:.2f} %",
            "desc": "A depth architecture activating L1, L2, L3 nodes as a vertical hierarchy. It triggers a waterfall-like resolution path: Client -> L1 -> L2 -> L3 -> Origin. Cache miss at L1 checks L2 and L3 instead of going straight to origin, removing origin backhaul load and dropping average RTT to ~4ms."
        }
    },
    "l1_l3": {
        "ko": {
            "title": "계층형 CDN (L1 → L3)",
            "latency": f"{global_avg_latency['l1_l3']:.2f} ms",
            "hit": f"{global_hit_rate['l1_l3']:.2f} %",
            "cost": f"{cost_stats['l1_l3']:,d}억 원",
            "nodes": f"{node_count_stats['l1_l3']}개 (L1+L3 거점)",
            "ttff": f"{global_avg_ttff['l1_l3']:.1f} ms",
            "rebuff": f"{global_avg_rebuff['l1_l3']:.2f} %",
            "offload": f"{global_hit_rate['l1_l3']:.2f} %",
            "desc": "L1(읍면동)과 L3(시도) 노드만 수직 계층으로 연결하고 L2를 생략한 구조입니다. L2 노드를 제외해 구축 비용을 아끼면서도, L1 캐시 미스 시 서울 오리진이 아닌 광역 L3 캐시를 탐색하므로 지연 시간과 오리진 부하를 분배합니다."
        },
        "en": {
            "title": "Hierarchical CDN (L1 → L3)",
            "latency": f"{global_avg_latency['l1_l3']:.2f} ms",
            "hit": f"{global_hit_rate['l1_l3']:.2f} %",
            "cost": f"{cost_stats['l1_l3']:,d} Billion KRW",
            "nodes": f"{node_count_stats['l1_l3']} Nodes (L1+L3)",
            "ttff": f"{global_avg_ttff['l1_l3']:.1f} ms",
            "rebuff": f"{global_avg_rebuff['l1_l3']:.2f} %",
            "offload": f"{global_hit_rate['l1_l3']:.2f} %",
            "desc": "A tiered network using L1 (Local Town) and L3 (Provincial) caches while skipping L2. It reduces municipal deployment costs while allowing L1 cache misses to check L3 provincial nodes instead of going straight to origin."
        }
    },
    "l1_l2": {
        "ko": {
            "title": "계층형 CDN (L1 → L2)",
            "latency": f"{global_avg_latency['l1_l2']:.2f} ms",
            "hit": f"{global_hit_rate['l1_l2']:.2f} %",
            "cost": f"{cost_stats['l1_l2']:,d}억 원",
            "nodes": f"{node_count_stats['l1_l2']}개 (L1+L2 거점)",
            "ttff": f"{global_avg_ttff['l1_l2']:.1f} ms",
            "rebuff": f"{global_avg_rebuff['l1_l2']:.2f} %",
            "offload": f"{global_hit_rate['l1_l2']:.2f} %",
            "desc": "L1(읍면동)과 L2(시군구) 에지노드만을 가동하는 계층 구조입니다. 대용량 광역 L3 노드를 배제하고 L1 미스 시 상위 L2 노드에서 캐시를 탐색함으로써, 광역 거점 서버 비용을 절감하는 대안적 아키텍처입니다."
        },
        "en": {
            "title": "Hierarchical CDN (L1 → L2)",
            "latency": f"{global_avg_latency['l1_l2']:.2f} ms",
            "hit": f"{global_hit_rate['l1_l2']:.2f} %",
            "cost": f"{cost_stats['l1_l2']:,d} Billion KRW",
            "nodes": f"{node_count_stats['l1_l2']} Nodes (L1+L2)",
            "ttff": f"{global_avg_ttff['l1_l2']:.1f} ms",
            "rebuff": f"{global_avg_rebuff['l1_l2']:.2f} %",
            "offload": f"{global_hit_rate['l1_l2']:.2f} %",
            "desc": "A tiered network using L1 (Local Town) and L2 (Municipal) caches while skipping L3. It avoids large provincial node deployment costs, allowing L1 cache misses to check nearby L2 municipal servers."
        }
    },
    "l2_l3": {
        "ko": {
            "title": "계층형 CDN (L2 → L3)",
            "latency": f"{global_avg_latency['l2_l3']:.2f} ms",
            "hit": f"{global_hit_rate['l2_l3']:.2f} %",
            "cost": f"{cost_stats['l2_l3']:,d}억 원",
            "nodes": f"{node_count_stats['l2_l3']}개 (L2+L3 거점)",
            "ttff": f"{global_avg_ttff['l2_l3']:.1f} ms",
            "rebuff": f"{global_avg_rebuff['l2_l3']:.2f} %",
            "offload": f"{global_hit_rate['l2_l3']:.2f} %",
            "desc": "L2(시군구)와 L3(시도) 에지노드만 가동하고 L1을 배제한 구조입니다. 읍면동 단위 밀착 에지의 노드 수가 6,487개에 달해 발생하는 거대한 설치 비용과 캐시 풀링 상실 문제를 방지하면서 지리적 지연 속도를 대폭 줄입니다."
        },
        "en": {
            "title": "Hierarchical CDN (L2 → L3)",
            "latency": f"{global_avg_latency['l2_l3']:.2f} ms",
            "hit": f"{global_hit_rate['l2_l3']:.2f} %",
            "cost": f"{cost_stats['l2_l3']:,d} Billion KRW",
            "nodes": f"{node_count_stats['l2_l3']} Nodes (L2+L3)",
            "ttff": f"{global_avg_ttff['l2_l3']:.1f} ms",
            "rebuff": f"{global_avg_rebuff['l2_l3']:.2f} %",
            "offload": f"{global_hit_rate['l2_l3']:.2f} %",
            "desc": "A tiered network using L2 (Municipal) and L3 (Provincial) caches while omitting L1. It avoids the massive deployment scale of 6,487 town nodes and the cache pooling loss, while maintaining reasonable latency RTT."
        }
    }
}

# 결과 콘솔 출력
print("=========================================================================")
print(f"{'설치 레벨 (전략)':<20} | {'평균 RTT':<10} | {'평균 TTFF':<10} | {'재버퍼링 비율':<10} | {'부하 절감률':<10}")
print("-------------------------------------------------------------------------")
for strat, name in [("direct", "오리진 직접 연결"), ("l3", "L3 에지 (시/도)"), ("l2", "L2 에지 (시/군/구)"), ("l1", "L1 에지 (읍/면/동)"), ("depth", "계층형 CDN (Depth)"), ("l1_l3", "계층형 CDN (L1->L3)"), ("l1_l2", "계층형 CDN (L1->L2)"), ("l2_l3", "계층형 CDN (L2->L3)")]:
    print(f"{name:<18} | {global_avg_latency[strat]:8.2f} ms | {global_avg_ttff[strat]:8.1f} ms | {global_avg_rebuff[strat]:10.2f} % | {global_hit_rate[strat]:10.2f} %")
print("=========================================================================")

# --- 4단계: Matplotlib을 활용한 정밀 정적 분석 차트 생성 ---
def generate_charts(lang='ko'):
    is_ko = (lang == 'ko')
    print(f"4단계: Matplotlib 기반 대한민국 지리/통계 그래프 ({lang}) 생성 중...")
    
    # ---------------- 4-1단계: 종합 지리 맵 생성 ----------------
    fig, axs = plt.subplots(3, 3, figsize=(18, 18))
    
    # 다국어 타이틀 및 라벨 매핑
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

    # 지연 시간 시각화용 컬러맵 설정 (1.0ms에서 12.0ms 구간)
    norm = mcolors.Normalize(vmin=1.0, vmax=12.0)
    try:
        cmap = plt.colormaps['RdYlGn_r']
    except AttributeError:
        cmap = plt.cm.get_cmap('RdYlGn_r')

    # 클라이언트 노드들의 실제 위경도 리스트
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
    print(f"-> 종합 지리 성능 맵 이미지({lang}) 저장 완료: {map_png_path}")

    # ---------------- 4-1-1단계: 개별 지리 성능 맵 분할 생성 ----------------
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

    # ---------------- 4-2단계: 종합 통계 비교 그래프 생성 ----------------
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

    # ---------------- 4-2-1단계: 개별 통계 차트 분할 생성 ----------------
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


# --- 5단계: Leaflet.js 기반의 HTML 대시보드 맵 파일 렌더링 ---
print("5단계: Leaflet.js 기반의 HTML 대시보드 맵 파일 렌더링 중...")

client_data_str = json.dumps(client_json_list, ensure_ascii=False)
servers_l3_str = json.dumps([{"id": k, "name": v["name"], "lat": v["coords"][0], "lon": v["coords"][1]} for k, v in servers_l3.items()], ensure_ascii=False)
servers_l2_str = json.dumps([{"id": k, "name": v["name"], "lat": v["coords"][0], "lon": v["coords"][1]} for k, v in servers_l2.items()], ensure_ascii=False)
servers_l1_str = json.dumps([{"id": k, "name": v["name"], "lat": v["coords"][0], "lon": v["coords"][1]} for k, v in servers_l1.items()], ensure_ascii=False)
strategy_meta_str = json.dumps(strategy_metadata, ensure_ascii=False)

html_template = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>대한민국 계층형(L3/L2/L1) CDN 성능 분석 실증 지도</title>
    
    <!-- Google Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=Outfit:wght@400;600;800&display=swap" rel="stylesheet">
    
    <!-- Leaflet.js CSS -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
    
    <!-- FontAwesome (Icons) -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    
    <!-- Vanilla CSS Custom Style -->
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Inter', sans-serif;
            background-color: #0c1017;
            color: #f0f6fc;
            height: 100vh;
            display: flex;
            overflow: hidden;
        }}
        
        /* Layout */
        #app-container {{
            display: flex;
            width: 100%;
            height: 100%;
            position: relative;
        }}
        
        #sidebar {{
            width: 420px;
            background: rgba(18, 26, 38, 0.95);
            border-right: 1px solid rgba(255, 255, 255, 0.08);
            display: flex;
            flex-direction: column;
            padding: 24px;
            z-index: 1000;
            box-shadow: 10px 0 30px rgba(0,0,0,0.5);
            backdrop-filter: blur(15px);
            overflow-y: auto;
        }}
        
        #map-container {{
            flex: 1;
            height: 100%;
            position: relative;
        }}
        
        #map {{
            width: 100%;
            height: 100%;
        }}
        
        /* Typography */
        h1 {{
            font-family: 'Outfit', sans-serif;
            font-size: 20px;
            font-weight: 800;
            line-height: 1.3;
            background: linear-gradient(135deg, #00d2d3, #a55eea);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 4px;
        }}
        
        .subtitle {{
            font-size: 12px;
            color: #8b949e;
            margin-bottom: 15px;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            font-weight: 600;
        }}
        
        /* Language Toggle Button Style */
        .lang-container {{
            display: flex;
            justify-content: flex-end;
            gap: 6px;
            margin-bottom: 12px;
        }}
        .lang-btn {{
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: #8b949e;
            padding: 4px 10px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 11px;
            font-weight: 700;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }}
        .lang-btn:hover {{
            background: rgba(255, 255, 255, 0.1);
            color: #f0f6fc;
            border-color: rgba(255, 255, 255, 0.2);
        }}
        .lang-btn.active {{
            background: #a55eea;
            border-color: #a55eea;
            color: #ffffff;
            box-shadow: 0 0 10px rgba(165, 94, 234, 0.4);
        }}
        
        /* Strategy Selector Cards */
        .strategy-title {{
            font-size: 14px;
            font-weight: 600;
            color: #8b949e;
            margin-bottom: 12px;
        }}
        
        .strategy-grid {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 10px;
            margin-bottom: 24px;
        }}
        
        .strategy-card {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 12px;
            padding: 12px 14px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            align-items: center;
            position: relative;
            overflow: hidden;
        }}
        
        .strategy-card:hover {{
            background: rgba(255, 255, 255, 0.06);
            border-color: rgba(255, 255, 255, 0.15);
            transform: translateY(-2px);
        }}
        
        .strategy-card.active {{
            background: rgba(165, 94, 234, 0.15);
            border-color: #a55eea;
            box-shadow: 0 0 15px rgba(165, 94, 234, 0.3);
        }}
        
        .strategy-card input[type="radio"] {{
            display: none;
        }}
        
        .card-icon {{
            width: 34px;
            height: 34px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.05);
            display: flex;
            align-items: center;
            justify-content: center;
            margin-right: 14px;
            font-size: 15px;
            transition: all 0.3s;
        }}
        
        .strategy-card.active .card-icon {{
            background: #a55eea;
            color: #fff;
        }}
        
        .card-details {{
            display: flex;
            flex-direction: column;
        }}
        
        .card-name {{
            font-size: 13px;
            font-weight: 700;
            color: #f0f6fc;
        }}
        
        .card-desc {{
            font-size: 10.5px;
            color: #8b949e;
            margin-top: 2px;
        }}
        
        /* Stats Dashboard Panels */
        .panel-title {{
            font-size: 14px;
            font-weight: 600;
            color: #8b949e;
            margin-bottom: 12px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            padding-bottom: 6px;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 24px;
        }}
        
        .stat-box {{
            background: rgba(0, 0, 0, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.04);
            border-radius: 10px;
            padding: 14px;
            display: flex;
            flex-direction: column;
        }}
        
        .stat-label {{
            font-size: 11px;
            color: #8b949e;
            margin-bottom: 6px;
            text-transform: uppercase;
        }}
        
        .stat-value {{
            font-family: 'Outfit', sans-serif;
            font-size: 20px;
            font-weight: 700;
            color: #00d2d3;
        }}
        
        .stat-value.latency {{
            color: #2ecc71;
        }}
        
        .stat-value.cost {{
            color: #ff7675;
        }}
        
        .desc-box {{
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.04);
            border-radius: 10px;
            padding: 14px;
            font-size: 12px;
            line-height: 1.6;
            color: #c9d1d9;
            margin-bottom: 24px;
        }}
        
        /* Map Legend Overlay */
        .legend-box {{
            background: rgba(18, 26, 38, 0.90);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            padding: 12px;
            font-size: 11px;
            line-height: 1.6;
            position: absolute;
            bottom: 20px;
            right: 20px;
            z-index: 1000;
            box-shadow: 0 4px 20px rgba(0,0,0,0.5);
            backdrop-filter: blur(5px);
            width: 230px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            margin-bottom: 6px;
        }}
        .legend-color {{
            width: 14px;
            height: 14px;
            border-radius: 3px;
            margin-right: 8px;
        }}
        
        /* Custom Leaflet Styling */
        .leaflet-container {{
            background-color: #0c1017 !important;
        }}
        
        /* Tooltip and Popups Custom Dark Theme */
        .leaflet-popup-content-wrapper, .leaflet-popup-tip {{
            background: rgba(18, 26, 38, 0.95) !important;
            color: #f0f6fc !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            box-shadow: 0 4px 20px rgba(0,0,0,0.6) !important;
            border-radius: 10px !important;
        }}
        .leaflet-popup-content {{
            margin: 14px 16px !important;
            font-family: 'Inter', sans-serif !important;
            font-size: 12px !important;
            line-height: 1.5 !important;
        }}
        .popup-title {{
            font-size: 13px;
            font-weight: 700;
            margin-bottom: 8px;
            color: #00d2d3;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            padding-bottom: 4px;
        }}
        .popup-row {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 4px;
        }}
        .popup-label {{
            color: #8b949e;
        }}
        .popup-val {{
            font-weight: 600;
        }}
    </style>
</head>
<body>

    <div id="app-container">
        <!-- Sidebar Dashboard -->
        <div id="sidebar">
            <div class="lang-container">
                <button id="btn-lang-ko" class="lang-btn active" onclick="changeLanguage('ko')">KO</button>
                <button id="btn-lang-en" class="lang-btn" onclick="changeLanguage('en')">EN</button>
            </div>
            
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 5px;">
                <i class="fa-solid fa-network-wired" style="color: #00d2d3; font-size: 24px;"></i>
                <h1 id="ui-title">CDN 에지 망 실증 대시보드</h1>
            </div>
            <div class="subtitle">Korea Tiered CDN Simulation</div>
            
            <!-- Strategy Selector -->
            <div class="panel-title" id="ui-step1">1단계: 에지 구축 레벨 선택</div>
            <div class="strategy-grid">
                <div class="strategy-card active" onclick="selectStrategy('direct')">
                    <input type="radio" name="strategy" id="r-direct" checked>
                    <div class="card-icon" style="color: #ff7675;"><i class="fa-solid fa-server"></i></div>
                    <div class="card-details">
                        <span class="card-name" id="card-name-direct">오리진 직접 연결 (No CDN)</span>
                        <span class="card-desc" id="card-desc-direct">서울 본사 오리진 직접 라우팅</span>
                    </div>
                </div>
                <div class="strategy-card" onclick="selectStrategy('l3')">
                    <input type="radio" name="strategy" id="r-l3">
                    <div class="card-icon" style="color: #3498db;"><i class="fa-solid fa-building-columns"></i></div>
                    <div class="card-details">
                        <span class="card-name" id="card-name-l3">L3 에지 (시/도 단위 - Width)</span>
                        <span class="card-desc" id="card-desc-l3">전국 {len(servers_l3)}개 광역 시/도 거점</span>
                    </div>
                </div>
                <div class="strategy-card" onclick="selectStrategy('l2')">
                    <input type="radio" name="strategy" id="r-l2">
                    <div class="card-icon" style="color: #2ecc71;"><i class="fa-solid fa-building-user"></i></div>
                    <div class="card-details">
                        <span class="card-name" id="card-name-l2">L2 에지 (시/군/구 단위 - Width)</span>
                        <span class="card-desc" id="card-desc-l2">전국 {len(servers_l2)}개 시/군/구 거점</span>
                    </div>
                </div>
                <div class="strategy-card" onclick="selectStrategy('l1')">
                    <input type="radio" name="strategy" id="r-l1">
                    <div class="card-icon" style="color: #9b59b6;"><i class="fa-solid fa-house-laptop"></i></div>
                    <div class="card-details">
                        <span class="card-name" id="card-name-l1">L1 에지 (읍/면/동 단위 - Width)</span>
                        <span class="card-desc" id="card-desc-l1">전국 {len(servers_l1)}개 동네 밀착형 에지</span>
                    </div>
                </div>
                <div class="strategy-card" onclick="selectStrategy('depth')">
                    <input type="radio" name="strategy" id="r-depth">
                    <div class="card-icon" style="color: #f1c40f;"><i class="fa-solid fa-network-wired"></i></div>
                    <div class="card-details">
                        <span class="card-name" id="card-name-depth" style="color: #f1c40f;">계층형 멀티티어 CDN (Depth)</span>
                        <span class="card-desc" id="card-desc-depth">Client → L1 → L2 → L3 → Origin</span>
                    </div>
                </div>
                <div class="strategy-card" onclick="selectStrategy('l2_l3')">
                    <input type="radio" name="strategy" id="r-l2_l3">
                    <div class="card-icon" style="color: #95a5a6;"><i class="fa-solid fa-network-wired"></i></div>
                    <div class="card-details">
                        <span class="card-name" id="card-name-l2_l3">계층형 CDN (L2 → L3)</span>
                        <span class="card-desc" id="card-desc-l2_l3">Client → L2 → L3 → Origin</span>
                    </div>
                </div>
                <div class="strategy-card" onclick="selectStrategy('l1_l3')">
                    <input type="radio" name="strategy" id="r-l1_l3">
                    <div class="card-icon" style="color: #e67e22;"><i class="fa-solid fa-network-wired"></i></div>
                    <div class="card-details">
                        <span class="card-name" id="card-name-l1_l3">계층형 CDN (L1 → L3)</span>
                        <span class="card-desc" id="card-desc-l1_l3">Client → L1 → L3 → Origin</span>
                    </div>
                </div>
                <div class="strategy-card" onclick="selectStrategy('l1_l2')">
                    <input type="radio" name="strategy" id="r-l1_l2">
                    <div class="card-icon" style="color: #1abc9c;"><i class="fa-solid fa-network-wired"></i></div>
                    <div class="card-details">
                        <span class="card-name" id="card-name-l1_l2">계층형 CDN (L1 → L2)</span>
                        <span class="card-desc" id="card-desc-l1_l2">Client → L1 → L2 → Origin</span>
                    </div>
                </div>
            </div>
            
            <!-- Stats Dashboard -->
            <div class="panel-title" id="ui-step2">2단계: 전체 네트워크 지표 요약</div>
            <div class="stats-grid">
                <div class="stat-box">
                    <span class="stat-label" id="lbl-latency">평균 응답 속도</span>
                    <span class="stat-value latency" id="stat-latency">-- ms</span>
                </div>
                <div class="stat-box">
                    <span class="stat-label" id="lbl-hit">캐시 적중률</span>
                    <span class="stat-value" id="stat-hit">-- %</span>
                </div>
                <div class="stat-box">
                    <span class="stat-label" id="lbl-nodes">망 노드 구축 수</span>
                    <span class="stat-value" id="stat-nodes">-- 개</span>
                </div>
                <div class="stat-box">
                    <span class="stat-label" id="lbl-cost">총 구축 투자 비용</span>
                    <span class="stat-value cost" id="stat-cost">-- 억 원</span>
                </div>
            </div>

            <!-- Video QoS Metrics Dashboard -->
            <div class="panel-title" id="ui-video">동영상 스트리밍 QoS 지표</div>
            <div class="stats-grid" style="grid-template-columns: 1fr; gap: 8px; margin-bottom: 24px;">
                <div class="stat-box" style="flex-direction: row; justify-content: space-between; align-items: center; padding: 10px 14px;">
                    <span class="stat-label" id="lbl-ttff" style="margin-bottom: 0;">첫 프레임 재생 시간 (TTFF)</span>
                    <span class="stat-value" id="stat-ttff" style="color: #f1c40f; font-size: 16px;">-- ms</span>
                </div>
                <div class="stat-box" style="flex-direction: row; justify-content: space-between; align-items: center; padding: 10px 14px;">
                    <span class="stat-label" id="lbl-rebuff" style="margin-bottom: 0;">평균 재버퍼링 비율 (Re-buffering)</span>
                    <span class="stat-value" id="stat-rebuff" style="color: #ff7675; font-size: 16px;">-- %</span>
                </div>
                <div class="stat-box" style="flex-direction: row; justify-content: space-between; align-items: center; padding: 10px 14px;">
                    <span class="stat-label" id="lbl-offload" style="margin-bottom: 0;">오리진 부하 절감률 (Offload Rate)</span>
                    <span class="stat-value" id="stat-offload" style="color: #00d2d3; font-size: 16px;">-- %</span>
                </div>
            </div>
            
            <!-- Strategy Description -->
            <div class="panel-title" id="ui-desc">구축 아키텍처 상세 설명</div>
            <div class="desc-box" id="stat-desc">
                여기에 선택된 아키텍처의 설계 특징과 기술적 장단점이 기술됩니다.
            </div>
            
            <!-- Usage Guide -->
            <div class="panel-title" id="ui-guide">지도 사용 및 가이드</div>
            <div id="guide-content" style="font-size: 11px; color: #8b949e; line-height: 1.6;">
                <p style="margin-bottom: 6px;"><i class="fa-solid fa-circle-info" style="color: #00d2d3; margin-right: 4px;"></i> 지도 상의 <b>작은 원 마커</b>들은 전국 {len(servers_l1)}개 실존 행정동의 가상 사용자(Client) 포인트입니다.</p>
                <p style="margin-bottom: 6px;"><i class="fa-solid fa-circle-info" style="color: #00d2d3; margin-right: 4px;"></i> 사용자 포인트를 <b>클릭</b>하면 해당 지역에서 에지 노드 및 오리진 서버까지 도달하는 <b>네트워크 물리 홉 경로선</b>이 활성화됩니다.</p>
                <p><i class="fa-solid fa-circle-info" style="color: #00d2d3; margin-right: 4px;"></i> 에지 구축 레벨이 달라짐에 따라 지역간 격차가 해소되는 색상 분포를 확인하세요.</p>
            </div>
        </div>
        
        <!-- Interactive Map -->
        <div id="map-container">
            <div id="map"></div>
            
            <!-- Legend Overlay -->
            <div class="legend-box" id="legend-box-overlay">
                <div style="font-weight: 600; margin-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 4px;">지연 속도 범례 (RTT)</div>
                <div class="legend-item">
                    <div class="legend-color" style="background: #2ecc71;"></div>
                    <span>초고속 ( &lt; 3 ms )</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: #a8e05f;"></div>
                    <span>보통 ( 3 - 6 ms )</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: #f1c40f;"></div>
                    <span>경미한 지연 ( 6 - 10 ms )</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: #fd9644;"></div>
                    <span>지연 발생 ( 10 - 16 ms )</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: #ff7675;"></div>
                    <span>극심한 지연 ( &gt; 16 ms )</span>
                </div>
                
                <div style="font-weight: 600; margin-top: 10px; margin-bottom: 6px; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 4px;">서버 노드 아이콘</div>
                <div class="legend-item">
                    <i class="fa-solid fa-star" style="color: #f1c40f; margin-right: 8px; font-size: 12px;"></i>
                    <span>서울 중앙 오리진 서버</span>
                </div>
                <div class="legend-item">
                    <i class="fa-solid fa-server" style="color: #3498db; margin-right: 8px; font-size: 10px;"></i>
                    <span>L3 시/도 에지 캐시 노드</span>
                </div>
                <div class="legend-item">
                    <i class="fa-solid fa-server" style="color: #2ecc71; margin-right: 8px; font-size: 10px;"></i>
                    <span>L2 시/군/구 에지 캐시 노드</span>
                </div>
                <div class="legend-item">
                    <span class="legend-color" style="background: #9b59b6; width: 10px; height: 10px; display: inline-block; margin-right: 8px;"></span>
                    <span>L1 읍/면/동 에지 캐시 노드</span>
                </div>
            </div>
        </div>
    </div>

    <!-- Leaflet.js script -->
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
    
    <!-- Simulation Embedded Data -->
    <script>
        const clients = {client_data_str};
        const serversL3 = {servers_l3_str};
        const serversL2 = {servers_l2_str};
        const serversL1 = {servers_l1_str};
        const strategyMeta = {strategy_meta_str};
        const originCoords = [{origin_coords[0]}, {origin_coords[1]}];
    </script>
    
    <!-- Application Translation and Logic -->
    <script>
        let map;
        let clientMarkers = [];
        let serverMarkers = [];
        let pathLines = [];
        let currentStrategy = 'direct';
        let canvasRenderer;
        let currentLanguage = 'ko';
        
        const translations = {{
            ko: {{
                title: "CDN 에지 망 실증 대시보드",
                subtitle: "Korea Tiered CDN Simulation",
                step1: "1단계: 에지 구축 레벨 선택",
                step2: "2단계: 전체 네트워크 지표 요약",
                video_title: "동영상 스트리밍 QoS 지표",
                desc_title: "구축 아키텍처 상세 설명",
                guide_title: "지도 사용 및 가이드",
                
                stat_latency_lbl: "평균 응답 속도",
                stat_hit_lbl: "캐시 적중률",
                stat_nodes_lbl: "망 노드 구축 수",
                stat_cost_lbl: "총 구축 투자 비용",
                stat_ttff_lbl: "첫 프레임 재생 시간 (TTFF)",
                stat_rebuff_lbl: "평균 재버퍼링 비율 (Re-buffering)",
                stat_offload_lbl: "오리진 부하 절감률 (Offload Rate)",
                
                guide_1: "지도 상의 <b>작은 원 마커</b>들은 전국 {len(servers_l1)}개 실존 행정동의 가상 사용자(Client) 포인트입니다.",
                guide_2: "사용자 포인트를 <b>클릭</b>하면 해당 지역에서 에지 노드 및 오리진 서버까지 도달하는 <b>네트워크 물리 홉 경로선</b>이 활성화됩니다.",
                guide_3: "에지 구축 레벨이 달라짐에 따라 지역간 격차가 해소되는 색상 분포를 확인하세요.",
                
                legend_title: "지연 속도 범례 (RTT)",
                legend_fast: "초고속 ( &lt; 3 ms )",
                legend_normal: "보통 ( 3 - 6 ms )",
                legend_mild: "경미한 지연 ( 6 - 10 ms )",
                legend_warn: "지연 발생 ( 10 - 16 ms )",
                legend_severe: "극심한 지연 ( &gt; 16 ms )",
                
                legend_server_title: "서버 노드 아이콘",
                legend_origin: "서울 중앙 오리진 서버",
                legend_l3: "L3 시/도 에지 캐시 노드",
                legend_l2: "L2 시/군/구 에지 캐시 노드",
                legend_l1: "L1 읍/면/동 에지 캐시 노드",
                
                popup_client_title: "가상 사용자",
                popup_pop: "인구 수",
                popup_req: "요청 건수",
                popup_avg_rtt: "평균 RTT",
                popup_ttff: "첫 프레임 속도 (TTFF)",
                popup_rebuff: "재버퍼링 비율",
                popup_total_hit: "CDN 총 적중률",
                popup_l1_hit: "ㄴ L1 (동네) 히트",
                popup_l2_hit: "ㄴ L2 (구군) 히트",
                popup_l3_hit: "ㄴ L3 (시도) 히트",
                popup_click_guide: "(마커 클릭 시 네트워크 홉 경로선 활성화)",
                
                popup_origin_title: "중앙 오리진 서버 (서울)",
                popup_origin_loc: "위치: 서울특별시 본사 IDC",
                
                popup_l3_title: "CDN 캐시 노드 (L3 시/도)",
                popup_l2_title: "CDN 캐시 노드 (L2 시/군/구)",
                popup_l1_title: "CDN 캐시 노드 (L1 읍/면/동)",
                popup_node_name: "노드 명칭",
                popup_name: "명칭",
                
                direct_card_name: "오리진 직접 연결 (No CDN)",
                direct_card_desc: "서울 본사 오리진 직접 라우팅",
                l3_card_name: "L3 에지 (시/도 단위 - Width)",
                l3_card_desc: "전국 {len(servers_l3)}개 광역 시/도 거점",
                l2_card_name: "L2 에지 (시/군/구 단위 - Width)",
                l2_card_desc: "전국 {len(servers_l2)}개 시/군/구 거점",
                l1_card_name: "L1 에지 (읍/면/동 단위 - Width)",
                l1_card_desc: "전국 {len(servers_l1)}개 동네 밀착형 에지",
                depth_card_name: "계층형 멀티티어 CDN (Depth)",
                depth_card_desc: "Client → L1 → L2 → L3 → Origin",
                l2_l3_card_name: "계층형 CDN (L2 → L3)",
                l2_l3_card_desc: "전국 {len(servers_l2)}개 L2 → {len(servers_l3)}개 L3 거점",
                l1_l3_card_name: "계층형 CDN (L1 → L3)",
                l1_l3_card_desc: "전국 {len(servers_l1)}개 L1 → {len(servers_l3)}개 L3 거점",
                l1_l2_card_name: "계층형 CDN (L1 → L2)",
                l1_l2_card_desc: "전국 {len(servers_l1)}개 L1 → {len(servers_l2)}개 L2 거점"
            }},
            en: {{
                title: "CDN Edge Network Dashboard",
                subtitle: "Korea Tiered CDN Simulation",
                step1: "Step 1: Choose Edge Level",
                step2: "Step 2: Network Metrics Summary",
                video_title: "Video Streaming QoS Metrics",
                desc_title: "Architecture Description",
                guide_title: "Map Interactive Guide",
                
                stat_latency_lbl: "Avg Response Time",
                stat_hit_lbl: "Cache Hit Rate",
                stat_nodes_lbl: "Edge Node Count",
                stat_cost_lbl: "Investment Cost",
                stat_ttff_lbl: "Time to First Frame (TTFF)",
                stat_rebuff_lbl: "Avg Re-buffering Ratio",
                stat_offload_lbl: "Origin Offload Rate",
                
                guide_1: "The <b>small circles</b> on the map represent virtual client positions across {len(servers_l1)} towns in Korea.",
                guide_2: "<b>Click</b> on any client circle to draw the <b>physical network hop path</b> reaching edge nodes and origin server.",
                guide_3: "Observe the color changes showing how regional digital disparity is resolved as you select deeper edge levels.",
                
                legend_title: "Latency Legend (RTT)",
                legend_fast: "Excellent ( &lt; 3 ms )",
                legend_normal: "Normal ( 3 - 6 ms )",
                legend_mild: "Mild Latency ( 6 - 10 ms )",
                legend_warn: "High Latency ( 10 - 16 ms )",
                legend_severe: "Critical Latency ( &gt; 16 ms )",
                
                legend_server_title: "Server Icons",
                legend_origin: "Seoul Origin Server",
                legend_l3: "L3 Provincial Edge Cache",
                legend_l2: "L2 Municipal Edge Cache",
                legend_l1: "L1 Local Town Edge Cache",
                
                popup_client_title: "Virtual Client",
                popup_pop: "Population",
                popup_req: "Requests",
                popup_avg_rtt: "Avg RTT",
                popup_ttff: "Avg TTFF",
                popup_rebuff: "Re-buffering Ratio",
                popup_total_hit: "CDN Total Hit Rate",
                popup_l1_hit: "L1 (Local) Hit",
                popup_l2_hit: "L2 (Municipal) Hit",
                popup_l3_hit: "L3 (Provincial) Hit",
                popup_click_guide: "(Click marker to draw network hop path)",
                
                popup_origin_title: "Central Origin Server (Seoul)",
                popup_origin_loc: "Location: Seoul HQ IDC",
                
                popup_l3_title: "CDN Cache Node (L3 Provincial)",
                popup_l2_title: "CDN Cache Node (L2 Municipal)",
                popup_l1_title: "CDN Cache Node (L1 Local)",
                popup_node_name: "Node Name",
                popup_name: "Name",
                
                direct_card_name: "Direct Connection (No CDN)",
                direct_card_desc: "Direct routing to Seoul Origin",
                l3_card_name: "L3 Edge (Provincial - Width)",
                l3_card_desc: "{len(servers_l3)} Provincial HQ centers",
                l2_card_name: "L2 Edge (Municipal - Width)",
                l2_card_desc: "{len(servers_l2)} Municipal centers",
                l1_card_name: "L1 Edge (Local Town - Width)",
                l1_card_desc: "{len(servers_l1)} Local town centers",
                depth_card_name: "Multi-tier Hierarchical CDN (Depth)",
                depth_card_desc: "Client → L1 → L2 → L3 → Origin",
                l2_l3_card_name: "Hierarchical CDN (L2 → L3)",
                l2_l3_card_desc: "{len(servers_l2)} L2 → {len(servers_l3)} L3 nodes",
                l1_l3_card_name: "Hierarchical CDN (L1 → L3)",
                l1_l3_card_desc: "{len(servers_l1)} L1 → {len(servers_l3)} L3 nodes",
                l1_l2_card_name: "Hierarchical CDN (L1 → L2)",
                l1_l2_card_desc: "{len(servers_l1)} L1 → {len(servers_l2)} L2 nodes"
            }}
        }};

        function changeLanguage(lang) {{
            currentLanguage = lang;
            document.getElementById('btn-lang-ko').classList.toggle('active', lang === 'ko');
            document.getElementById('btn-lang-en').classList.toggle('active', lang === 'en');
            
            // Translate Text elements
            const t = translations[lang];
            document.getElementById('ui-title').innerText = t.title;
            document.getElementById('ui-step1').innerText = t.step1;
            document.getElementById('ui-step2').innerText = t.step2;
            document.getElementById('ui-video').innerText = t.video_title;
            document.getElementById('ui-desc').innerText = t.desc_title;
            document.getElementById('ui-guide').innerText = t.guide_title;
            
            // Labels
            document.getElementById('lbl-latency').innerText = t.stat_latency_lbl;
            document.getElementById('lbl-hit').innerText = t.stat_hit_lbl;
            document.getElementById('lbl-nodes').innerText = t.stat_nodes_lbl;
            document.getElementById('lbl-cost').innerText = t.stat_cost_lbl;
            document.getElementById('lbl-ttff').innerText = t.stat_ttff_lbl;
            document.getElementById('lbl-rebuff').innerText = t.stat_rebuff_lbl;
            document.getElementById('lbl-offload').innerText = t.stat_offload_lbl;
            
            // Guide text
            document.getElementById('guide-content').innerHTML = `
                <p style="margin-bottom: 6px;"><i class="fa-solid fa-circle-info" style="color: #00d2d3; margin-right: 4px;"></i> ${{t.guide_1}}</p>
                <p style="margin-bottom: 6px;"><i class="fa-solid fa-circle-info" style="color: #00d2d3; margin-right: 4px;"></i> ${{t.guide_2}}</p>
                <p><i class="fa-solid fa-circle-info" style="color: #00d2d3; margin-right: 4px;"></i> ${{t.guide_3}}</p>
            `;
            
            // Legend
            const legendBox = document.getElementById('legend-box-overlay');
            legendBox.innerHTML = `
                <div style="font-weight: 600; margin-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 4px;">${{t.legend_title}}</div>
                <div class="legend-item"><div class="legend-color" style="background: #2ecc71;"></div><span>${{t.legend_fast}}</span></div>
                <div class="legend-item"><div class="legend-color" style="background: #a8e05f;"></div><span>${{t.legend_normal}}</span></div>
                <div class="legend-item"><div class="legend-color" style="background: #f1c40f;"></div><span>${{t.legend_mild}}</span></div>
                <div class="legend-item"><div class="legend-color" style="background: #fd9644;"></div><span>${{t.legend_warn}}</span></div>
                <div class="legend-item"><div class="legend-color" style="background: #ff7675;"></div><span>${{t.legend_severe}}</span></div>
                
                <div style="font-weight: 600; margin-top: 10px; margin-bottom: 6px; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 4px;">${{t.legend_server_title}}</div>
                <div class="legend-item"><i class="fa-solid fa-star" style="color: #f1c40f; margin-right: 8px; font-size: 12px;"></i><span>${{t.legend_origin}}</span></div>
                <div class="legend-item"><i class="fa-solid fa-server" style="color: #3498db; margin-right: 8px; font-size: 10px;"></i><span>${{t.legend_l3}}</span></div>
                <div class="legend-item"><i class="fa-solid fa-server" style="color: #2ecc71; margin-right: 8px; font-size: 10px;"></i><span>${{t.legend_l2}}</span></div>
                <div class="legend-item"><span class="legend-color" style="background: #9b59b6; width: 10px; height: 10px; display: inline-block; margin-right: 8px;"></span><span>${{t.legend_l1}}</span></div>
            `;
            
            // Cards text
            document.getElementById('card-name-direct').innerText = t.direct_card_name;
            document.getElementById('card-desc-direct').innerText = t.direct_card_desc;
            
            document.getElementById('card-name-l3').innerText = t.l3_card_name;
            document.getElementById('card-desc-l3').innerText = t.l3_card_desc;
            
            document.getElementById('card-name-l2').innerText = t.l2_card_name;
            document.getElementById('card-desc-l2').innerText = t.l2_card_desc;
            
            document.getElementById('card-name-l1').innerText = t.l1_card_name;
            document.getElementById('card-desc-l1').innerText = t.l1_card_desc;
            
            document.getElementById('card-name-depth').innerText = t.depth_card_name;
            document.getElementById('card-desc-depth').innerText = t.depth_card_desc;
            
            document.getElementById('card-name-l2_l3').innerText = t.l2_l3_card_name;
            document.getElementById('card-desc-l2_l3').innerText = t.l2_l3_card_desc;
            
            document.getElementById('card-name-l1_l3').innerText = t.l1_l3_card_name;
            document.getElementById('card-desc-l1_l3').innerText = t.l1_l3_card_desc;
            
            document.getElementById('card-name-l1_l2').innerText = t.l1_l2_card_name;
            document.getElementById('card-desc-l1_l2').innerText = t.l1_l2_card_desc;
            
            updateUI();
            drawMapLayers();
        }}
        
        function getLatencyColor(lat) {{
            if (lat < 3.0) return '#2ecc71';
            if (lat < 6.0) return '#a8e05f';
            if (lat < 10.0) return '#f1c40f';
            if (lat < 16.0) return '#fd9644';
            return '#ff7675';
        }}
        
        function initMap() {{
            map = L.map('map', {{
                zoomControl: false
            }}).setView([35.9, 127.8], 7.2);
            
            canvasRenderer = L.canvas({{ padding: 0.5 }});
            
            L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
                attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://openstreetmap.org">OpenStreetMap</a>',
                subdomains: 'abcd',
                maxZoom: 20
            }}).addTo(map);
            
            L.control.zoom({{
                position: 'topright'
            }}).addTo(map);
            
            const originIcon = L.divIcon({{
                html: '<i class="fa-solid fa-star" style="color: #f1c40f; font-size: 24px; text-shadow: 0 0 10px rgba(241,196,15,0.8);"></i>',
                className: 'custom-div-icon',
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            }});
            
            // Origin server marker binding with dynamic translations
            L.marker(originCoords, {{icon: originIcon}}).addTo(map)
                .on('click', function(e) {{
                    const t = translations[currentLanguage];
                    L.popup()
                        .setLatLng(originCoords)
                        .setContent(`<div class="popup-title"><i class="fa-solid fa-database"></i> ${{t.popup_origin_title}}</div><div>${{t.popup_origin_loc}}</div>`)
                        .openOn(map);
                }});
                
            updateUI();
            drawMapLayers();
            
            map.on('click', function() {{
                clearActivePaths();
            }});
        }}
        
        function clearActivePaths() {{
            pathLines.forEach(line => map.removeLayer(line));
            pathLines = [];
        }}
        
        function drawMapLayers() {{
            clearActivePaths();
            
            clientMarkers.forEach(m => map.removeLayer(m));
            serverMarkers.forEach(m => map.removeLayer(m));
            clientMarkers = [];
            serverMarkers = [];
            
            const t = translations[currentLanguage];
            
            // 1. Draw Servers based on strategy
            if (currentStrategy === 'l3') {{
                serversL3.forEach(server => {{
                    const serverIcon = L.divIcon({{
                        html: `<i class="fa-solid fa-server" style="color: #3498db; font-size: 14px; text-shadow: 0 0 6px #3498db;"></i>`,
                        className: 'custom-div-icon',
                        iconSize: [16, 16],
                        iconAnchor: [8, 8]
                    }});
                    const m = L.marker([server.lat, server.lon], {{icon: serverIcon}}).addTo(map)
                        .bindPopup(`<div class="popup-title"><i class="fa-solid fa-network-wired"></i> ${{t.popup_l3_title}}</div><div><b>${{t.popup_node_name}}:</b> ${{server.name}}</div>`);
                    serverMarkers.push(m);
                }});
            }} else if (currentStrategy === 'l2') {{
                serversL2.forEach(server => {{
                    const serverIcon = L.divIcon({{
                        html: `<i class="fa-solid fa-server" style="color: #2ecc71; font-size: 11px; text-shadow: 0 0 4px #2ecc71;"></i>`,
                        className: 'custom-div-icon',
                        iconSize: [12, 12],
                        iconAnchor: [6, 6]
                    }});
                    const m = L.marker([server.lat, server.lon], {{icon: serverIcon}}).addTo(map)
                        .bindPopup(`<div class="popup-title"><i class="fa-solid fa-network-wired"></i> ${{t.popup_l2_title}}</div><div><b>${{t.popup_node_name}}:</b> ${{server.name}}</div>`);
                    serverMarkers.push(m);
                }});
            }} else if (currentStrategy === 'l1') {{
                serversL1.forEach(server => {{
                    const sMarker = L.circleMarker([server.lat, server.lon], {{
                        renderer: canvasRenderer,
                        radius: 3,
                        fillColor: '#9b59b6',
                        color: '#ffffff',
                        weight: 0.4,
                        opacity: 0.8,
                        fillOpacity: 0.9
                    }}).addTo(map);
                    sMarker.bindPopup(`<div class="popup-title"><i class="fa-solid fa-network-wired"></i> ${{t.popup_l1_title}}</div><div><b>${{t.popup_name}}:</b> ${{server.name}}</div>`);
                    serverMarkers.push(sMarker);
                }});
            }} else if (currentStrategy === 'depth') {{
                serversL3.forEach(server => {{
                    const serverIcon = L.divIcon({{
                        html: `<i class="fa-solid fa-server" style="color: #3498db; font-size: 14px; text-shadow: 0 0 6px #3498db;"></i>`,
                        className: 'custom-div-icon',
                        iconSize: [16, 16],
                        iconAnchor: [8, 8]
                    }});
                    const m = L.marker([server.lat, server.lon], {{icon: serverIcon}}).addTo(map)
                        .bindPopup(`<div class="popup-title"><i class="fa-solid fa-network-wired"></i> ${{t.popup_l3_title}}</div><div><b>${{t.popup_name}}:</b> ${{server.name}}</div>`);
                    serverMarkers.push(m);
                }});
                serversL2.forEach(server => {{
                    const serverIcon = L.divIcon({{
                        html: `<i class="fa-solid fa-server" style="color: #2ecc71; font-size: 11px; text-shadow: 0 0 4px #2ecc71;"></i>`,
                        className: 'custom-div-icon',
                        iconSize: [12, 12],
                        iconAnchor: [6, 6]
                    }});
                    const m = L.marker([server.lat, server.lon], {{icon: serverIcon}}).addTo(map)
                        .bindPopup(`<div class="popup-title"><i class="fa-solid fa-network-wired"></i> ${{t.popup_l2_title}}</div><div><b>${{t.popup_name}}:</b> ${{server.name}}</div>`);
                    serverMarkers.push(m);
                }});
                serversL1.forEach(server => {{
                    const sMarker = L.circleMarker([server.lat, server.lon], {{
                        renderer: canvasRenderer,
                        radius: 3,
                        fillColor: '#9b59b6',
                        color: '#ffffff',
                        weight: 0.4,
                        opacity: 0.8,
                        fillOpacity: 0.9
                    }}).addTo(map);
                    sMarker.bindPopup(`<div class="popup-title"><i class="fa-solid fa-network-wired"></i> ${{t.popup_l1_title}}</div><div><b>${{t.popup_name}}:</b> ${{server.name}}</div>`);
                    serverMarkers.push(sMarker);
                }});
            }}
            
            // 2. Draw Clients (Circle Markers)
            clients.forEach(client => {{
                const latVal = client.latencies[currentStrategy];
                const ttffVal = client.ttffs[currentStrategy];
                const rebuffVal = client.rebuffs[currentStrategy];
                const color = getLatencyColor(latVal);
                const hitVal = client.hit_rates[currentStrategy] || 0.0;
                
                const radius = Math.max(3.0, Math.log10(client.pop) * 1.2);
                
                const cMarker = L.circleMarker([client.lat, client.lon], {{
                    renderer: canvasRenderer,
                    radius: radius,
                    fillColor: color,
                    color: '#ffffff',
                    weight: 0.4,
                    opacity: 0.6,
                    fillOpacity: 0.8
                }}).addTo(map);
                
                let popupContent = `
                    <div class="popup-title"><i class="fa-solid fa-house"></i> ${{t.popup_client_title}}: ${{client.name}}</div>
                    <div class="popup-row"><span class="popup-label">${{t.popup_pop}}:</span><span class="popup-val">${{client.pop.toLocaleString()}}</span></div>
                    <div class="popup-row"><span class="popup-label">${{t.popup_req}}:</span><span class="popup-val">${{client.requests.toLocaleString()}}</span></div>
                    
                    <div style="margin-top: 8px; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 6px;"></div>
                    <div class="popup-row">
                        <span class="popup-label">${{t.popup_avg_rtt}}:</span>
                        <span class="popup-val" style="color: ${{color}}; font-weight: 700;">${{latVal.toFixed(2)}} ms</span>
                    </div>
                    <div class="popup-row">
                        <span class="popup-label">${{t.popup_ttff}}:</span>
                        <span class="popup-val" style="color: #f1c40f;">${{ttffVal.toFixed(1)}} ms</span>
                    </div>
                    <div class="popup-row">
                        <span class="popup-label">${{t.popup_rebuff}}:</span>
                        <span class="popup-val" style="color: #ff7675;">${{rebuffVal.toFixed(2)}} %</span>
                    </div>
                `;
                
                if (currentStrategy === 'depth') {{
                    popupContent += `
                        <div class="popup-row">
                            <span class="popup-label">${{t.popup_total_hit}}:</span>
                            <span class="popup-val" style="color: #00d2d3;">${{hitVal.toFixed(1)}} %</span>
                        </div>
                        <div style="margin-top: 6px; padding-top: 4px; border-top: 1px dashed rgba(255,255,255,0.05); font-size: 11px;">
                            <div class="popup-row"><span class="popup-label">${{t.popup_l1_hit}}:</span><span class="popup-val" style="color: #9b59b6;">${{client.depth_hits_detail.l1.toFixed(1)}}%</span></div>
                            <div class="popup-row"><span class="popup-label">${{t.popup_l2_hit}}:</span><span class="popup-val" style="color: #2ecc71;">${{client.depth_hits_detail.l2.toFixed(1)}}%</span></div>
                            <div class="popup-row"><span class="popup-label">${{t.popup_l3_hit}}:</span><span class="popup-val" style="color: #3498db;">${{client.depth_hits_detail.l3.toFixed(1)}}%</span></div>
                        </div>
                    `;
                }} else if (currentStrategy === 'l1_l3') {{
                    popupContent += `
                        <div class="popup-row">
                            <span class="popup-label">${{t.popup_total_hit}}:</span>
                            <span class="popup-val" style="color: #00d2d3;">${{hitVal.toFixed(1)}} %</span>
                        </div>
                        <div style="margin-top: 6px; padding-top: 4px; border-top: 1px dashed rgba(255,255,255,0.05); font-size: 11px;">
                            <div class="popup-row"><span class="popup-label">${{t.popup_l1_hit}}:</span><span class="popup-val" style="color: #9b59b6;">${{client.l1_l3_hits_detail.l1.toFixed(1)}}%</span></div>
                            <div class="popup-row"><span class="popup-label">${{t.popup_l3_hit}}:</span><span class="popup-val" style="color: #3498db;">${{client.l1_l3_hits_detail.l3.toFixed(1)}}%</span></div>
                        </div>
                    `;
                }} else if (currentStrategy === 'l1_l2') {{
                    popupContent += `
                        <div class="popup-row">
                            <span class="popup-label">${{t.popup_total_hit}}:</span>
                            <span class="popup-val" style="color: #00d2d3;">${{hitVal.toFixed(1)}} %</span>
                        </div>
                        <div style="margin-top: 6px; padding-top: 4px; border-top: 1px dashed rgba(255,255,255,0.05); font-size: 11px;">
                            <div class="popup-row"><span class="popup-label">${{t.popup_l1_hit}}:</span><span class="popup-val" style="color: #9b59b6;">${{client.l1_l2_hits_detail.l1.toFixed(1)}}%</span></div>
                            <div class="popup-row"><span class="popup-label">${{t.popup_l2_hit}}:</span><span class="popup-val" style="color: #2ecc71;">${{client.l1_l2_hits_detail.l2.toFixed(1)}}%</span></div>
                        </div>
                    `;
                }} else if (currentStrategy === 'l2_l3') {{
                    popupContent += `
                        <div class="popup-row">
                            <span class="popup-label">${{t.popup_total_hit}}:</span>
                            <span class="popup-val" style="color: #00d2d3;">${{hitVal.toFixed(1)}} %</span>
                        </div>
                        <div style="margin-top: 6px; padding-top: 4px; border-top: 1px dashed rgba(255,255,255,0.05); font-size: 11px;">
                            <div class="popup-row"><span class="popup-label">${{t.popup_l2_hit}}:</span><span class="popup-val" style="color: #2ecc71;">${{client.l2_l3_hits_detail.l2.toFixed(1)}}%</span></div>
                            <div class="popup-row"><span class="popup-label">${{t.popup_l3_hit}}:</span><span class="popup-val" style="color: #3498db;">${{client.l2_l3_hits_detail.l3.toFixed(1)}}%</span></div>
                        </div>
                    `;
                }} else if (currentStrategy !== 'direct') {{
                    popupContent += `
                        <div class="popup-row">
                            <span class="popup-label">${{t.popup_total_hit}}:</span>
                            <span class="popup-val" style="color: #00d2d3;">${{hitVal.toFixed(1)}} %</span>
                        </div>
                    `;
                }}
                
                popupContent += `<div style="font-size: 10px; color: #8b949e; margin-top: 8px; text-align: center;">${{t.popup_click_guide}}</div>`;
                cMarker.bindPopup(popupContent);
                
                cMarker.on('click', function(e) {{
                    L.DomEvent.stopPropagation(e);
                    clearActivePaths();
                    
                    if (currentStrategy === 'depth') {{
                        const s2 = serversL2.find(s => s.id === client.l2_id);
                        const s3 = serversL3.find(s => s.id === client.l3_id);
                        
                        if (s2 && s3) {{
                            const lineToL1 = L.polyline([[client.lat, client.lon], [client.server_lat, client.server_lon]], {{
                                color: '#9b59b6',
                                weight: 2.5,
                                opacity: 0.95
                            }}).addTo(map);
                            pathLines.push(lineToL1);
                            
                            const lineToL2 = L.polyline([[client.server_lat, client.server_lon], [s2.lat, s2.lon]], {{
                                color: '#2ecc71',
                                weight: 2.5,
                                opacity: 0.85
                            }}).addTo(map);
                            pathLines.push(lineToL2);
                            
                            const lineToL3 = L.polyline([[s2.lat, s2.lon], [s3.lat, s3.lon]], {{
                                color: '#3498db',
                                weight: 2.0,
                                opacity: 0.8
                            }}).addTo(map);
                            pathLines.push(lineToL3);
                            
                            const lineToOrigin = L.polyline([[s3.lat, s3.lon], originCoords], {{
                                color: '#ff7675',
                                weight: 1.5,
                                opacity: 0.6,
                                dashArray: '5, 5'
                            }}).addTo(map);
                            pathLines.push(lineToOrigin);
                        }}
                    }} else if (currentStrategy === 'l1_l3') {{
                        const s3 = serversL3.find(s => s.id === client.l3_id);
                        if (s3) {{
                            const lineToL1 = L.polyline([[client.lat, client.lon], [client.server_lat, client.server_lon]], {{
                                color: '#9b59b6',
                                weight: 2.5,
                                opacity: 0.95
                            }}).addTo(map);
                            pathLines.push(lineToL1);
                            
                            const lineToL3 = L.polyline([[client.server_lat, client.server_lon], [s3.lat, s3.lon]], {{
                                color: '#3498db',
                                weight: 2.5,
                                opacity: 0.85
                            }}).addTo(map);
                            pathLines.push(lineToL3);
                            
                            const lineToOrigin = L.polyline([[s3.lat, s3.lon], originCoords], {{
                                color: '#ff7675',
                                weight: 1.5,
                                opacity: 0.6,
                                dashArray: '5, 5'
                            }}).addTo(map);
                            pathLines.push(lineToOrigin);
                        }}
                    }} else if (currentStrategy === 'l1_l2') {{
                        const s2 = serversL2.find(s => s.id === client.l2_id);
                        if (s2) {{
                            const lineToL1 = L.polyline([[client.lat, client.lon], [client.server_lat, client.server_lon]], {{
                                color: '#9b59b6',
                                weight: 2.5,
                                opacity: 0.95
                            }}).addTo(map);
                            pathLines.push(lineToL1);
                            
                            const lineToL2 = L.polyline([[client.server_lat, client.server_lon], [s2.lat, s2.lon]], {{
                                color: '#2ecc71',
                                weight: 2.5,
                                opacity: 0.85
                            }}).addTo(map);
                            pathLines.push(lineToL2);
                            
                            const lineToOrigin = L.polyline([[s2.lat, s2.lon], originCoords], {{
                                color: '#ff7675',
                                weight: 1.5,
                                opacity: 0.6,
                                dashArray: '5, 5'
                            }}).addTo(map);
                            pathLines.push(lineToOrigin);
                        }}
                    }} else if (currentStrategy === 'l2_l3') {{
                        const s2 = serversL2.find(s => s.id === client.l2_id);
                        const s3 = serversL3.find(s => s.id === client.l3_id);
                        if (s2 && s3) {{
                            const lineToL2 = L.polyline([[client.lat, client.lon], [s2.lat, s2.lon]], {{
                                color: '#2ecc71',
                                weight: 2.5,
                                opacity: 0.95
                            }}).addTo(map);
                            pathLines.push(lineToL2);
                            
                            const lineToL3 = L.polyline([[s2.lat, s2.lon], [s3.lat, s3.lon]], {{
                                color: '#3498db',
                                weight: 2.5,
                                opacity: 0.85
                            }}).addTo(map);
                            pathLines.push(lineToL3);
                            
                            const lineToOrigin = L.polyline([[s3.lat, s3.lon], originCoords], {{
                                color: '#ff7675',
                                weight: 1.5,
                                opacity: 0.6,
                                dashArray: '5, 5'
                            }}).addTo(map);
                            pathLines.push(lineToOrigin);
                        }}
                    }} else {{
                        let serverCoords = null;
                        let hopColor = '#00b894';
                        let lineWeight = 2.5;
                        
                        if (currentStrategy === 'l3') {{
                            const s = serversL3.find(s => s.id === client.l3_id);
                            if (s) serverCoords = [s.lat, s.lon];
                            hopColor = '#3498db';
                        }} else if (currentStrategy === 'l2') {{
                            const s = serversL2.find(s => s.id === client.l2_id);
                            if (s) serverCoords = [s.lat, s.lon];
                            hopColor = '#2ecc71';
                        }} else if (currentStrategy === 'l1') {{
                            serverCoords = [client.server_lat, client.server_lon];
                            hopColor = '#9b59b6';
                            lineWeight = 3.0;
                        }}
                        
                        if (serverCoords) {{
                            const lineToCDN = L.polyline([[client.lat, client.lon], serverCoords], {{
                                color: hopColor,
                                weight: lineWeight,
                                opacity: 0.95
                            }}).addTo(map);
                            pathLines.push(lineToCDN);
                            
                            const lineToOrigin = L.polyline([serverCoords, originCoords], {{
                                color: '#ff7675',
                                weight: 1.5,
                                opacity: 0.6,
                                dashArray: '5, 5'
                            }}).addTo(map);
                            pathLines.push(lineToOrigin);
                        }} else {{
                            const lineToOrigin = L.polyline([[client.lat, client.lon], originCoords], {{
                                color: '#ff7675',
                                weight: 2.0,
                                opacity: 0.8
                            }}).addTo(map);
                            pathLines.push(lineToOrigin);
                        }}
                    }}
                }});
                
                clientMarkers.push(cMarker);
            }});
        }}
        
        function selectStrategy(strategyId) {{
            currentStrategy = strategyId;
            
            const cards = document.querySelectorAll('.strategy-card');
            cards.forEach(card => card.classList.remove('active'));
            
            document.getElementById('r-' + strategyId).checked = true;
            document.getElementById('r-' + strategyId).closest('.strategy-card').classList.add('active');
            
            updateUI();
            drawMapLayers();
        }}
        
        function updateUI() {{
            const meta = strategyMeta[currentStrategy][currentLanguage];
            document.getElementById('stat-latency').innerText = meta.latency;
            document.getElementById('stat-hit').innerText = meta.hit;
            document.getElementById('stat-nodes').innerText = meta.nodes;
            document.getElementById('stat-cost').innerText = meta.cost;
            document.getElementById('stat-desc').innerText = meta.desc;
            
            // Video QoS Dashboard update
            document.getElementById('stat-ttff').innerText = meta.ttff;
            document.getElementById('stat-rebuff').innerText = meta.rebuff;
            document.getElementById('stat-offload').innerText = meta.offload;
        }}
        
        window.onload = initMap;
    </script>
</body>
</html>
"""

# Write HTML file
html_filepath = '/home/donghwi/cloud_network_project/korea_cdn_interactive_map.html'
with open(html_filepath, 'w', encoding='utf-8') as f:
    f.write(html_template)

print(f"5단계: HTML 파일 저장 완료 -> {html_filepath}")

# 또한 Artifacts 디렉토리로 동일하게 내보내기
artifact_dir = '/home/donghwi/.gemini/antigravity-cli/brain/21aedd55-43a5-420e-b722-9c5a4be1bd05'
if os.path.exists(artifact_dir):
    with open(os.path.join(artifact_dir, 'korea_cdn_interactive_map.html'), 'w', encoding='utf-8') as f:
        f.write(html_template)
    
    # 영어/한글 버전 복사
    shutil.copy('/home/donghwi/cloud_network_project/korea_cdn_map_ko.png', os.path.join(artifact_dir, 'korea_cdn_map_ko.png'))
    shutil.copy('/home/donghwi/cloud_network_project/korea_cdn_map_en.png', os.path.join(artifact_dir, 'korea_cdn_map_en.png'))
    shutil.copy('/home/donghwi/cloud_network_project/korea_cdn_result_ko.png', os.path.join(artifact_dir, 'korea_cdn_result_ko.png'))
    shutil.copy('/home/donghwi/cloud_network_project/korea_cdn_result_en.png', os.path.join(artifact_dir, 'korea_cdn_result_en.png'))
    
    # 하위 호환성 유지용 파일 복사
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

print("=========================================================================")
print(" 시뮬레이션 및 인터랙티브 웹 맵 생성 성공!")
print(" 브라우저에서 아래 파일을 열어서 탐색해 보세요:")
print(f" file://{html_filepath}")
print("=========================================================================")
