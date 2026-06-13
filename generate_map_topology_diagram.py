import numpy as np
import random
import os
import shutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.colors as mcolors
from korean_geocoding.geocoding import KoreanGeocoding
import korean_geocoding.geocoding as kg_module

# --- 한글 폰트 설정 ---
try:
    font_path = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
    fm.fontManager.addfont(font_path)
    plt.rcParams['font.family'] = 'Noto Sans CJK JP'
    plt.rcParams['axes.unicode_minus'] = False
    print("한글 폰트 설정 완료: Noto Sans CJK JP")
except Exception as e:
    print(f"한글 폰트 설정 중 오류 발생: {e}")

# --- 1단계: 토폴로지 데이터 빌드 ---
RANDOM_SEED = 42
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

kg = KoreanGeocoding()
sido_keys = list(kg_module.SIDO_DICT.keys())

POPULATIONS = {
    "서울특별시": 9400000, "부산광역시": 3300000, "대구광역시": 2400000, "인천광역시": 3000000,
    "광주광역시": 1400000, "대전광역시": 1400000, "울산광역시": 1100000, "세종특별자치시": 390000,
    "경기도": 13600000, "강원도": 1530000, "충청북도": 1600000, "충청남도": 2120000,
    "전라북도": 1770000, "전라남도": 1810000, "경상북도": 2580000, "경상남도": 3270000,
    "제주특별자치도": 670000
}

origin_coords = [37.5665, 126.9780] # 서울특별시청 기준

# Helper functions for coordinates
def get_l2_coordinates(kg, query, parent_coords):
    try:
        coords = kg.get_coordinates(query)
        if coords is not None: return coords
    except: pass
    return parent_coords

def get_l1_coordinates(kg, query, parent_coords):
    try:
        coords = kg.get_coordinates(query)
        if coords is not None: return coords
    except: pass
    if parent_coords:
        angle = random.uniform(0, 2 * np.pi)
        dist_km = random.uniform(2.0, 3.5)
        lat_offset = (dist_km / 111.0) * np.sin(angle)
        lon_offset = (dist_km / (111.0 * np.cos(np.radians(parent_coords[0])))) * np.cos(angle)
        return (parent_coords[0] + lat_offset, parent_coords[1] + lon_offset)
    return None

client_nodes = []
servers_l3 = {}
servers_l2 = {}
servers_l1 = {}

print("지리적 데이터를 가동 중...")
for sido in sido_keys:
    coords_l3 = kg.get_coordinates(sido)
    if coords_l3 is None: continue
    
    sido_pop = POPULATIONS.get(sido, 1000000)
    servers_l3[sido] = {"name": sido, "coords": coords_l3, "level": "L3"}
    
    if sido == "세종특별자치시":
        dongs = kg.get_under_districts(sido)
        l2_id = "Sejong_0"
        servers_l2[l2_id] = {"name": "세종특별자치시청", "coords": coords_l3, "l3_id": sido, "level": "L2"}
        for idx, dong_name in enumerate(dongs):
            coords_l1 = get_l1_coordinates(kg, f"{sido} {dong_name}", coords_l3)
            if coords_l1 is None: continue
            l1_id = f"{l2_id}_{idx}"
            client_angle = random.uniform(0, 2 * np.pi)
            client_dist_km = random.uniform(1.2, 2.2)
            client_lat = (client_dist_km / 111.0) * np.sin(client_angle)
            client_lon = (client_dist_km / (111.0 * np.cos(np.radians(coords_l1[0])))) * np.cos(client_angle)
            client_coords = (coords_l1[0] + client_lat, coords_l1[1] + client_lon)
            servers_l1[l1_id] = {"name": f"{sido} {dong_name} 에지", "coords": coords_l1, "l2_id": l2_id, "l3_id": sido, "level": "L1"}
            client_nodes.append({"id": l1_id, "name": f"{sido} {dong_name}", "coords": coords_l1, "client_coords": client_coords, "l2_id": l2_id, "l3_id": sido})
    else:
        sigungus = kg.get_under_districts(sido)
        for sgg in sigungus:
            coords_l2 = get_l2_coordinates(kg, f"{sido} {sgg}", coords_l3)
            l2_id = f"{sido}_{sgg}"
            servers_l2[l2_id] = {"name": f"{sido} {sgg} 에지", "coords": coords_l2, "l3_id": sido, "level": "L2"}
            try:
                dongs = kg.get_under_districts(f"{sido} {sgg}")
            except:
                dongs = [sgg]
            for idx, dong in enumerate(dongs):
                coords_l1 = get_l1_coordinates(kg, f"{sido} {sgg} {dong}", coords_l2)
                if coords_l1 is None: continue
                l1_id = f"{l2_id}_{idx}"
                client_angle = random.uniform(0, 2 * np.pi)
                client_dist_km = random.uniform(1.2, 2.2)
                client_lat = (client_dist_km / 111.0) * np.sin(client_angle)
                client_lon = (client_dist_km / (111.0 * np.cos(np.radians(coords_l1[0])))) * np.cos(client_angle)
                client_coords = (coords_l1[0] + client_lat, coords_l1[1] + client_lon)
                servers_l1[l1_id] = {"name": f"{sido} {sgg} {dong} 에지", "coords": coords_l1, "l2_id": l2_id, "l3_id": sido, "level": "L1"}
                client_nodes.append({"id": l1_id, "name": f"{sido} {sgg} {dong}", "coords": coords_l1, "client_coords": client_coords, "l2_id": l2_id, "l3_id": sido})

print(f"로드 완료: L3={len(servers_l3)}, L2={len(servers_l2)}, L1={len(servers_l1)}, Clients={len(client_nodes)}")

# --- 2단계: 대표 노드 및 경로 매핑 ---
# 대표 지역 설정: 제주도, 부산, 대구, 강원도 강릉
selected_targets = [
    {"name_ko": "제주 서귀포", "name_en": "Jeju Seogwipo", "sido": "제주특별자치도", "sgg": "서귀포시"},
    {"name_ko": "부산 해운대", "name_en": "Busan Haeundae", "sido": "부산광역시", "sgg": "해운대구"},
    {"name_ko": "대구 수성", "name_en": "Daegu Suseong", "sido": "대구광역시", "sgg": "수성구"},
    {"name_ko": "강원 강릉", "name_en": "Gangwon Gangneung", "sido": "강원도", "sgg": "강릉시"}
]

target_paths = []
for target in selected_targets:
    # 해당 sido/sgg에 속하는 클라이언트 찾기
    candidates = [n for n in client_nodes if n["l3_id"] == target["sido"] and target["sgg"] in n["name"]]
    if not candidates:
        candidates = [n for n in client_nodes if n["l3_id"] == target["sido"]]
    if candidates:
        client = candidates[len(candidates)//2] # 중간에 있는 것 선택
        l1_id = client["id"]
        l1 = servers_l1[l1_id]
        l2_id = client["l2_id"]
        l2 = servers_l2[l2_id]
        l3_id = client["l3_id"]
        l3 = servers_l3[l3_id]
        
        target_paths.append({
            "label_ko": target["name_ko"],
            "label_en": target["name_en"],
            "client": client["client_coords"],
            "l1": l1["coords"],
            "l2": l2["coords"],
            "l3": l3["coords"]
        })

# --- 3단계: 지도 시각화 드로잉 ---
def draw_map_topology(lang='ko'):
    is_ko = (lang == 'ko')
    
    bg_color = '#0c1017'
    text_color = '#f0f6fc'
    map_dot_color = '#1f242d' # 매우 어두운 점으로 한국의 실루엣 표현
    
    client_color = '#00d2d3'  # 클라이언트 (청록)
    l1_color = '#9b59b6'      # L1 에지 (보라)
    l2_color = '#2ecc71'      # L2 에지 (초록)
    l3_color = '#3498db'      # L3 에지 (파랑)
    origin_color = '#f1c40f'  # 오리진 (노랑)
    
    fig, axs = plt.subplots(1, 2, figsize=(16, 9.5))
    fig.patch.set_facecolor(bg_color)
    
    titles = {
        "width": "Width (단층형 CDN 지리적 연결도)" if is_ko else "Width (Geographical Single-Tier CDN Flow)",
        "depth": "Depth (계층형 CDN 지리적 연결도)" if is_ko else "Depth (Geographical Multi-Tier CDN Flow)",
        "origin": "오리진\n(Origin)" if is_ko else "Origin",
        "client": "클라이언트" if is_ko else "Client"
    }

    # 전체 클라이언트 좌표 추출 (배경 대한민국 실루엣용)
    all_lons = [n["client_coords"][1] for n in client_nodes]
    all_lats = [n["client_coords"][0] for n in client_nodes]
    
    # ------------------ Subplot 1: Width 그리기 ------------------
    ax_w = axs[0]
    ax_w.set_facecolor(bg_color)
    ax_w.set_title(titles["width"], fontsize=14, fontweight='bold', color=text_color, pad=10)
    
    # 배경 대한민국 점도
    ax_w.scatter(all_lons, all_lats, color=map_dot_color, s=1.0, alpha=0.3, zorder=1)
    
    # 오리진 표시 (서울)
    ax_w.scatter(origin_coords[1], origin_coords[0], color=origin_color, marker='*', s=150, edgecolor='#ffffff', linewidth=1.0, zorder=5)
    ax_w.text(origin_coords[1] - 0.1, origin_coords[0] + 0.15, titles["origin"], color=origin_color, fontsize=9, fontweight='bold', ha='right', zorder=6)
    
    # 각 지점별 Width 경로 그리기
    # 4개 지점에 각각 다른 Width 아키텍처를 보여주어 개념을 설명
    # 1. 제주도: L3 에지와 연결되는 구조
    # 2. 부산: L2 에지와 연결되는 구조
    # 3. 강릉: L1 에지와 연결되는 구조
    # 4. 대구: L1 에지와 연결되는 구조
    
    width_types = [
        {"name": "L3 Width", "level": "L3", "color": l3_color},
        {"name": "L2 Width", "level": "L2", "color": l2_color},
        {"name": "L1 Width", "level": "L1", "color": l1_color},
        {"name": "L1 Width", "level": "L1", "color": l1_color}
    ]
    
    for idx, path in enumerate(target_paths):
        w_type = width_types[idx]
        c_coords = path["client"]
        target_coords = path[w_type["level"].lower()]
        
        # 1. 클라이언트 플롯
        ax_w.scatter(c_coords[1], c_coords[0], color=client_color, s=40, edgecolor='white', linewidth=0.5, zorder=4)
        ax_w.text(c_coords[1] + 0.08, c_coords[0] - 0.08, path["label_ko" if is_ko else "label_en"], color=text_color, fontsize=8, fontweight='bold', zorder=5)
        
        # 2. 통신 에지 서버 플롯
        ax_w.scatter(target_coords[1], target_coords[0], color=w_type["color"], s=60, marker='s' if w_type["level"]=="L3" else '^' if w_type["level"]=="L2" else 'o', edgecolor='white', linewidth=0.5, zorder=4)
        
        # 3. 선 연결 (Client -> Edge -> Origin)
        # Client -> Edge
        ax_w.plot([c_coords[1], target_coords[1]], [c_coords[0], target_coords[0]], color='#8b949e', lw=1.5, zorder=2)
        # Edge -> Origin (미스 시 오리진 연결선 - 빨간 점선)
        ax_w.plot([target_coords[1], origin_coords[1]], [target_coords[0], origin_coords[0]], color='#ff7675', lw=1.5, linestyle='--', zorder=2)
        
        # 설명 텍스트
        mid_x = (c_coords[1] + target_coords[1]) / 2
        mid_y = (c_coords[0] + target_coords[0]) / 2
        label_text = f"{w_type['name']}"
        ax_w.text(mid_x, mid_y + 0.05, label_text, color=w_type["color"], fontsize=7.5, fontweight='bold', ha='center', zorder=5)

    ax_w.set_xlim(124.2, 131.2)
    ax_w.set_ylim(32.8, 38.8)
    ax_w.axis('off')
    
    # ------------------ Subplot 2: Depth 그리기 ------------------
    ax_d = axs[1]
    ax_d.set_facecolor(bg_color)
    ax_d.set_title(titles["depth"], fontsize=14, fontweight='bold', color=text_color, pad=10)
    
    # 배경 대한민국 점도
    ax_d.scatter(all_lons, all_lats, color=map_dot_color, s=1.0, alpha=0.3, zorder=1)
    
    # 오리진 표시 (서울)
    ax_d.scatter(origin_coords[1], origin_coords[0], color=origin_color, marker='*', s=150, edgecolor='#ffffff', linewidth=1.0, zorder=5)
    ax_d.text(origin_coords[1] - 0.1, origin_coords[0] + 0.15, titles["origin"], color=origin_color, fontsize=9, fontweight='bold', ha='right', zorder=6)
    
    # Depth 경로 그리기: Client -> L1 -> L2 -> L3 -> Origin
    for path in target_paths:
        c_coords = path["client"]
        l1_coords = path["l1"]
        l2_coords = path["l2"]
        l3_coords = path["l3"]
        
        # 노드들 플롯
        # Client
        ax_d.scatter(c_coords[1], c_coords[0], color=client_color, s=40, edgecolor='white', linewidth=0.5, zorder=4)
        ax_d.text(c_coords[1] + 0.08, c_coords[0] - 0.08, path["label_ko" if is_ko else "label_en"], color=text_color, fontsize=8, fontweight='bold', zorder=5)
        # L1 (보라)
        ax_d.scatter(l1_coords[1], l1_coords[0], color=l1_color, s=45, marker='o', edgecolor='white', linewidth=0.5, zorder=4)
        # L2 (초록)
        ax_d.scatter(l2_coords[1], l2_coords[0], color=l2_color, s=50, marker='^', edgecolor='white', linewidth=0.5, zorder=4)
        # L3 (파랑)
        ax_d.scatter(l3_coords[1], l3_coords[0], color=l3_color, s=60, marker='s', edgecolor='white', linewidth=0.5, zorder=4)
        
        # 단계별 홉 연결선 그리기 (Client -> L1 -> L2 -> L3 -> Origin)
        # Client -> L1
        ax_d.plot([c_coords[1], l1_coords[1]], [c_coords[0], l1_coords[0]], color=client_color, lw=1.2, zorder=2)
        # L1 -> L2
        ax_d.plot([l1_coords[1], l2_coords[1]], [l1_coords[0], l2_coords[0]], color='#a29bfe', lw=1.5, zorder=2)
        # L2 -> L3
        ax_d.plot([l2_coords[1], l3_coords[1]], [l2_coords[0], l3_coords[0]], color='#74b9ff', lw=1.8, zorder=2)
        # L3 -> Origin
        ax_d.plot([l3_coords[1], origin_coords[1]], [l3_coords[0], origin_coords[0]], color='#ff7675', lw=2.0, zorder=2)

    # 범례 박스 그리기
    legend_elements = [
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=client_color, markersize=8, label=titles["client"]),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=l1_color, markersize=8, label="L1 에지 (읍면동)" if is_ko else "L1 Edge (Town)"),
        plt.Line2D([0], [0], marker='^', color='w', markerfacecolor=l2_color, markersize=8, label="L2 에지 (시군구)" if is_ko else "L2 Edge (Municipal)"),
        plt.Line2D([0], [0], marker='s', color='w', markerfacecolor=l3_color, markersize=8, label="L3 에지 (시도)" if is_ko else "L3 Edge (Provincial)"),
        plt.Line2D([0], [0], marker='*', color='w', markerfacecolor=origin_color, markersize=12, label="서울 오리진" if is_ko else "Seoul Origin"),
        plt.Line2D([0], [0], color='#ff7675', lw=2, linestyle='--', label="오리진 백홀 연결" if is_ko else "Origin Backhaul Path")
    ]
    ax_d.legend(handles=legend_elements, facecolor='#161b22', edgecolor='#30363d', labelcolor='#c9d1d9', fontsize=8.5, loc='lower right')

    ax_d.set_xlim(124.2, 131.2)
    ax_d.set_ylim(32.8, 38.8)
    ax_d.axis('off')
    
    # 전체 메인 타이틀
    main_title = "대한민국 CDN 토폴로지 지리적 연결 흐름 비교 (Width vs Depth)" if is_ko else "Geographical CDN Topology Flow: Width vs Depth in South Korea"
    plt.suptitle(main_title, fontsize=16, fontweight='bold', color='#ffffff', y=0.96)
    
    plt.tight_layout()
    fig.subplots_adjust(top=0.90, bottom=0.03)
    
    output_path = f'/home/donghwi/cloud_network_project/korea_cdn_map_topology_{lang}.png'
    plt.savefig(output_path, dpi=300, facecolor=bg_color)
    plt.close()
    print(f"-> 지리 토폴로지 연결도({lang}) 저장 완료: {output_path}")

# 실행
draw_map_topology('ko')
draw_map_topology('en')

# 아티팩트 복사
artifact_dir = '/home/donghwi/.gemini/antigravity-cli/brain/21aedd55-43a5-420e-b722-9c5a4be1bd05'
if os.path.exists(artifact_dir):
    shutil.copy('/home/donghwi/cloud_network_project/korea_cdn_map_topology_ko.png', os.path.join(artifact_dir, 'korea_cdn_map_topology_ko.png'))
    shutil.copy('/home/donghwi/cloud_network_project/korea_cdn_map_topology_en.png', os.path.join(artifact_dir, 'korea_cdn_map_topology_en.png'))
    print("-> Artifacts 디렉토리에 지리 다이어그램 복사 완료!")
