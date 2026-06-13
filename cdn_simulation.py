import simpy
import numpy as np
import matplotlib.pyplot as plt
import random

# --- 시뮬레이션 설정 ---
RANDOM_SEED = 42
SIM_TIME = 10000  # 시뮬레이션 총 시간
NUM_REQUESTS = 50000 # 총 요청 수
ZIPF_ALPHA = 1.0 # Zipf 분포 지수 (콘텐츠 인기도)
CONTENT_COUNT = 2000 # 전체 콘텐츠 수

# 비용 설정
COST_PER_NODE = 10  # 노드 하나당 유지 비용
LATENCY_ORIGIN = 100 # 오리진 서버까지의 지연 시간 (ms)
LATENCY_EDGE = 10    # 엣지 노드까지의 지연 시간 (ms)
LATENCY_TIER = 20    # 계층 간 이동 지연 시간 (ms)

def get_zipf_request():
    """Zipf 분포를 따르는 콘텐츠 ID 반환"""
    # 단순화된 Zipf 샘플링
    weights = [1.0 / (i + 1)**ZIPF_ALPHA for i in range(CONTENT_COUNT)]
    weights /= np.sum(weights)
    return np.random.choice(range(CONTENT_COUNT), p=weights)

class CDNNode:
    def __init__(self, env, node_id, level=1, parent=None):
        self.env = env
        self.node_id = node_id
        self.level = level
        self.parent = parent
        self.cache = set()
        self.cache_capacity = 100 # 각 노드의 캐시 용량

    def request(self, content_id):
        # 1. 로컬 캐시 확인
        if content_id in self.cache:
            return LATENCY_EDGE if self.level == 1 else LATENCY_TIER
        
        # 2. 상위 계층 또는 오리진 확인
        if self.parent:
            latency = self.parent.request(content_id)
        else:
            latency = LATENCY_ORIGIN
        
        # 캐싱 (단순화를 위해 요청된 콘텐츠를 캐시에 추가)
        if len(self.cache) < self.cache_capacity:
            self.cache.add(content_id)
        else:
            # LRU 대신 랜덤 교체 (간략화)
            self.cache.remove(random.choice(list(self.cache)))
            self.cache.add(content_id)
            
        return latency + (LATENCY_TIER if self.level > 1 else 0)

def simulate_cdn(strategy, n_nodes):
    env = simpy.Environment()
    
    if strategy == 'width':
        # Strategy A (Width): Flat 1-tier topology
        # n_nodes개의 엣지 노드가 오리진에 직접 연결됨
        nodes = [CDNNode(env, i, level=1) for i in range(n_nodes)]
    else:
        # Strategy B (Depth): 4-tier tree topology
        # Origin -> L3 -> L2 -> L1 (Client)
        # 단순화를 위해 n_nodes를 전체 계층에 분배하거나 
        # 트리 구조로 배치 (여기서는 n_nodes를 L1의 수로 가정하고 계층 구성)
        l3 = CDNNode(env, 'l3', level=3)
        l2 = CDNNode(env, 'l2', level=2, parent=l3)
        l1 = [CDNNode(env, f'l1_{i}', level=1, parent=l2) for i in range(n_nodes)]
        nodes = l1

    total_latency = 0
    
    for _ in range(NUM_REQUESTS):
        content_id = get_zipf_request()
        node = random.choice(nodes)
        total_latency += node.request(content_id)
        
    avg_latency = total_latency / NUM_REQUESTS
    total_cost = n_nodes * COST_PER_NODE
    
    return avg_latency, total_cost

def run_experiment():
    n_range = range(1, 101, 5) # N from 1 to 100
    width_results = []
    depth_results = []

    print("Running Simulation for Width Strategy...")
    for n in n_range:
        lat, cost = simulate_cdn('width', n)
        width_results.append((n, lat, cost))

    print("Running Simulation for Depth Strategy...")
    for n in n_range:
        lat, cost = simulate_cdn('depth', n)
        depth_results.append((n, lat, cost))

    # 결과 시각화 및 Elbow Point 분석
    plt.figure(figsize=(12, 5))

    plt.subplot(1, 2, 1)
    plt.plot([r[0] for r in width_results], [r[1] for r in width_results], label='Width (Flat)', marker='o')
    plt.plot([r[0] for r in depth_results], [r[1] for r in depth_results], label='Depth (4-Tier)', marker='s')
    plt.xlabel('Number of Nodes (N)')
    plt.ylabel('Avg Response Time (ms)')
    plt.title('Performance: Width vs Depth')
    plt.legend()
    plt.grid(True)

    plt.subplot(1, 2, 2)
    # Cost-Efficiency Metric: Latency * Cost (낮을수록 좋음)
    plt.plot([r[0] for r in width_results], [r[1]*r[2] for r in width_results], label='Width Efficiency', marker='o')
    plt.plot([r[0] for r in depth_results], [r[1]*r[2] for r in depth_results], label='Depth Efficiency', marker='s')
    plt.xlabel('Number of Nodes (N)')
    plt.ylabel('Cost x Latency (Metric)')
    plt.title('Finding Elbow Point (Cost-Efficiency)')
    plt.legend()
    plt.grid(True)

    plt.tight_layout()
    plt.savefig('/home/donghwi/cloud_network_project/experiment1_result.png')
    print("Results saved to /home/donghwi/cloud_network_project/experiment1_result.png")
    plt.show()

if __name__ == "__main__":
    np.random.seed(RANDOM_SEED)
    run_experiment()
