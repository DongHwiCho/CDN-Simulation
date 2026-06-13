import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.font_manager as fm
import os
import shutil

# --- 한글 폰트 설정 ---
try:
    font_path = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
    fm.fontManager.addfont(font_path)
    plt.rcParams['font.family'] = 'Noto Sans CJK JP'
    plt.rcParams['axes.unicode_minus'] = False
    print("한글 폰트 설정 완료: Noto Sans CJK JP")
except Exception as e:
    print(f"한글 폰트 설정 중 오류 발생: {e}")

def draw_diagram(lang='ko'):
    is_ko = (lang == 'ko')
    
    # 폰트 색상 및 스타일
    bg_color = '#0c1017'
    text_color = '#f0f6fc'
    
    # 노드 색상 정의
    client_color = '#00d2d3'  # 클라이언트 (청록)
    l1_color = '#9b59b6'      # L1 에지 (보라)
    l2_color = '#2ecc71'      # L2 에지 (초록)
    l3_color = '#3498db'      # L3 에지 (파랑)
    origin_color = '#f1c40f'  # 오리진 (노랑)
    
    # 텍스트 레이블 정의
    if is_ko:
        title_width = "Width (단층형 CDN 아키텍처)"
        title_depth = "Depth (계층형 CDN 아키텍처)"
        label_client = "클라이언트\n(Client)"
        label_l1 = "L1 에지\n(읍/면/동)"
        label_l2 = "L2 에지\n(시/군/구)"
        label_l3 = "L3 에지\n(시/도)"
        label_origin = "오리진\n(Origin)"
        desc_width = "• 각 에지 레벨이 단독으로 오리진과 통신\n• L1 미스 시 즉시 오리진으로 트래픽 집중"
        desc_depth = "• Client → L1 → L2 → L3 → Origin 연쇄 통신\n• 단계별 캐싱 필터링으로 오리진 부하 극대화 절감"
        main_suptitle = "CDN 토폴로지 비교: Width(단층형) vs Depth(계층형)"
    else:
        title_width = "Width (Single-Tier CDN Architecture)"
        title_depth = "Depth (Multi-Tier Hierarchical CDN)"
        label_client = "Client"
        label_l1 = "L1 Edge\n(Town)"
        label_l2 = "L2 Edge\n(Municipal)"
        label_l3 = "L3 Edge\n(Provincial)"
        label_origin = "Origin\n(Central)"
        desc_width = "• Each tier communicates directly with the Origin\n• Misses at L1/L2 go straight to Origin, increasing load"
        desc_depth = "• Client → L1 → L2 → L3 → Origin hop sequence\n• Cascaded filtering reduces Origin load significantly"
        main_suptitle = "CDN Topology Comparison: Width vs Depth"

    fig, axs = plt.subplots(1, 2, figsize=(15, 8.5))
    fig.patch.set_facecolor(bg_color)
    
    # ------------------ 1. Width (단층형) 그리기 ------------------
    ax_w = axs[0]
    ax_w.set_facecolor(bg_color)
    ax_w.set_title(title_width, fontsize=15, fontweight='bold', color=text_color, pad=15)
    
    # 노드 그리기 (클라이언트, 에지, 오리진)
    # L3 Width
    ax_w.add_patch(patches.Circle((1, 3), 0.25, color=client_color, zorder=3))
    ax_w.text(1, 3, label_client, ha='center', va='center', color='#000000', fontsize=9, fontweight='bold', zorder=4)
    ax_w.add_patch(patches.Circle((3, 3), 0.28, color=l3_color, zorder=3))
    ax_w.text(3, 3, label_l3, ha='center', va='center', color='#ffffff', fontsize=9, fontweight='bold', zorder=4)
    
    # L2 Width
    ax_w.add_patch(patches.Circle((1, 2), 0.25, color=client_color, zorder=3))
    ax_w.text(1, 2, label_client, ha='center', va='center', color='#000000', fontsize=9, fontweight='bold', zorder=4)
    ax_w.add_patch(patches.Circle((3, 2), 0.28, color=l2_color, zorder=3))
    ax_w.text(3, 2, label_l2, ha='center', va='center', color='#ffffff', fontsize=9, fontweight='bold', zorder=4)
    
    # L1 Width
    ax_w.add_patch(patches.Circle((1, 1), 0.25, color=client_color, zorder=3))
    ax_w.text(1, 1, label_client, ha='center', va='center', color='#000000', fontsize=9, fontweight='bold', zorder=4)
    ax_w.add_patch(patches.Circle((3, 1), 0.28, color=l1_color, zorder=3))
    ax_w.text(3, 1, label_l1, ha='center', va='center', color='#ffffff', fontsize=9, fontweight='bold', zorder=4)
    
    # 오리진 (우측 중앙)
    ax_w.add_patch(patches.RegularPolygon(xy=(5.2, 2), numVertices=5, radius=0.35, color=origin_color, zorder=3))
    ax_w.text(5.2, 2, label_origin, ha='center', va='center', color='#000000', fontsize=9, fontweight='bold', zorder=4)
    
    # 연결 화살표 그리기
    # Client -> Edges
    ax_w.annotate('', xy=(2.72, 3), xytext=(1.25, 3), arrowprops=dict(arrowstyle="->", color='#8b949e', lw=2))
    ax_w.annotate('', xy=(2.72, 2), xytext=(1.25, 2), arrowprops=dict(arrowstyle="->", color='#8b949e', lw=2))
    ax_w.annotate('', xy=(2.72, 1), xytext=(1.25, 1), arrowprops=dict(arrowstyle="->", color='#8b949e', lw=2))
    
    # Edges -> Origin
    ax_w.annotate('', xy=(4.9, 2.1), xytext=(3.28, 3), arrowprops=dict(arrowstyle="->", color='#ff7675', lw=2, linestyle='--'))
    ax_w.annotate('', xy=(4.9, 2.0), xytext=(3.28, 2), arrowprops=dict(arrowstyle="->", color='#ff7675', lw=2, linestyle='--'))
    ax_w.annotate('', xy=(4.9, 1.9), xytext=(3.28, 1), arrowprops=dict(arrowstyle="->", color='#ff7675', lw=2, linestyle='--'))
    
    # 흐름 설명 라벨 추가
    if is_ko:
        ax_w.text(2, 3.15, "로컬 요청", color='#8b949e', fontsize=8, ha='center', va='center',
                  bbox=dict(boxstyle='round,pad=0.2', facecolor='#0c1017', edgecolor='none', alpha=0.9))
        ax_w.text(4.1, 2.85, "캐시 미스 시\n오리진 직접 요청", color='#ff7675', fontsize=8, ha='center', va='center',
                  bbox=dict(boxstyle='round,pad=0.2', facecolor='#0c1017', edgecolor='none', alpha=0.9))
    else:
        ax_w.text(2, 3.15, "Local Req", color='#8b949e', fontsize=8, ha='center', va='center',
                  bbox=dict(boxstyle='round,pad=0.2', facecolor='#0c1017', edgecolor='none', alpha=0.9))
        ax_w.text(4.1, 2.85, "Direct Request\non Miss", color='#ff7675', fontsize=8, ha='center', va='center',
                  bbox=dict(boxstyle='round,pad=0.2', facecolor='#0c1017', edgecolor='none', alpha=0.9))

    # 설명 박스
    ax_w.text(1, 0.2, desc_width, fontsize=10, color='#c9d1d9', va='top', ha='left',
              bbox=dict(boxstyle='round,pad=0.5', facecolor='#161b22', edgecolor='#30363d', alpha=0.8))
              
    ax_w.set_xlim(0.3, 5.9)
    ax_w.set_ylim(-0.2, 3.6)
    ax_w.axis('off')
    
    # ------------------ 2. Depth (계층형) 그리기 ------------------
    ax_d = axs[1]
    ax_d.set_facecolor(bg_color)
    ax_d.set_title(title_depth, fontsize=15, fontweight='bold', color=text_color, pad=15)
    
    # Depth 노드 그리기 (일렬 구조)
    ax_d.add_patch(patches.Circle((1.0, 2), 0.28, color=client_color, zorder=3))
    ax_d.text(1.0, 2, label_client, ha='center', va='center', color='#000000', fontsize=9, fontweight='bold', zorder=4)
    
    ax_d.add_patch(patches.Circle((2.2, 2), 0.28, color=l1_color, zorder=3))
    ax_d.text(2.2, 2, label_l1, ha='center', va='center', color='#ffffff', fontsize=9, fontweight='bold', zorder=4)
    
    ax_d.add_patch(patches.Circle((3.4, 2), 0.28, color=l2_color, zorder=3))
    ax_d.text(3.4, 2, label_l2, ha='center', va='center', color='#ffffff', fontsize=9, fontweight='bold', zorder=4)
    
    ax_d.add_patch(patches.Circle((4.6, 2), 0.28, color=l3_color, zorder=3))
    ax_d.text(4.6, 2, label_l3, ha='center', va='center', color='#ffffff', fontsize=9, fontweight='bold', zorder=4)
    
    ax_d.add_patch(patches.RegularPolygon(xy=(5.8, 2), numVertices=5, radius=0.35, color=origin_color, zorder=3))
    ax_d.text(5.8, 2, label_origin, ha='center', va='center', color='#000000', fontsize=9, fontweight='bold', zorder=4)
    
    # 연결 화살표 그리기
    # Client -> L1
    ax_d.annotate('', xy=(1.92, 2), xytext=(1.28, 2), arrowprops=dict(arrowstyle="->", color='#8b949e', lw=2))
    # L1 -> L2
    ax_d.annotate('', xy=(3.12, 2), xytext=(2.48, 2), arrowprops=dict(arrowstyle="->", color='#a29bfe', lw=2, linestyle='-'))
    # L2 -> L3
    ax_d.annotate('', xy=(4.32, 2), xytext=(3.68, 2), arrowprops=dict(arrowstyle="->", color='#74b9ff', lw=2, linestyle='-'))
    # L3 -> Origin
    ax_d.annotate('', xy=(5.5, 2), xytext=(4.88, 2), arrowprops=dict(arrowstyle="->", color='#ff7675', lw=2, linestyle='-'))
    
    # 흐름 설명 라벨 추가
    if is_ko:
        ax_d.text(1.6, 2.15, "1. 로컬 요청", color='#8b949e', fontsize=7.5, ha='center')
        ax_d.text(2.8, 2.15, "2. L1 미스 시\nL2 전달", color='#a29bfe', fontsize=7.5, ha='center')
        ax_d.text(4.0, 2.15, "3. L2 미스 시\nL3 전달", color='#74b9ff', fontsize=7.5, ha='center')
        ax_d.text(5.2, 2.15, "4. L3 미스 시\n최종 오리진", color='#ff7675', fontsize=7.5, ha='center')
    else:
        ax_d.text(1.6, 2.15, "1. Local Req", color='#8b949e', fontsize=7.5, ha='center')
        ax_d.text(2.8, 2.15, "2. L1 Miss\nForward to L2", color='#a29bfe', fontsize=7.5, ha='center')
        ax_d.text(4.0, 2.15, "3. L2 Miss\nForward to L3", color='#74b9ff', fontsize=7.5, ha='center')
        ax_d.text(5.2, 2.15, "4. L3 Miss\nFetch Origin", color='#ff7675', fontsize=7.5, ha='center')

    # 설명 박스
    ax_d.text(0.7, 0.2, desc_depth, fontsize=10, color='#c9d1d9', va='top', ha='left',
              bbox=dict(boxstyle='round,pad=0.5', facecolor='#161b22', edgecolor='#30363d', alpha=0.8))
              
    ax_d.set_xlim(0.3, 6.5)
    ax_d.set_ylim(-0.2, 3.6)
    ax_d.axis('off')
    
    plt.suptitle(main_suptitle, fontsize=18, fontweight='bold', color='#ffffff', y=0.96)
    plt.tight_layout()
    fig.subplots_adjust(top=0.88, bottom=0.05)
    
    output_path = f'/home/donghwi/cloud_network_project/korea_cdn_topology_{lang}.png'
    plt.savefig(output_path, dpi=300, facecolor=bg_color)
    plt.close()
    print(f"-> 토폴로지 연결 다이어그램({lang}) 저장 완료: {output_path}")

    # --- 1-1. Width 단독 저장 ---
    fig_w, ax_w = plt.subplots(figsize=(8, 8))
    fig_w.patch.set_facecolor(bg_color)
    ax_w.set_facecolor(bg_color)
    ax_w.set_title(title_width, fontsize=14, fontweight='bold', color=text_color, pad=15)
    
    ax_w.add_patch(patches.Circle((1, 3), 0.25, color=client_color, zorder=3))
    ax_w.text(1, 3, label_client, ha='center', va='center', color='#000000', fontsize=9, fontweight='bold', zorder=4)
    ax_w.add_patch(patches.Circle((3, 3), 0.28, color=l3_color, zorder=3))
    ax_w.text(3, 3, label_l3, ha='center', va='center', color='#ffffff', fontsize=9, fontweight='bold', zorder=4)
    
    ax_w.add_patch(patches.Circle((1, 2), 0.25, color=client_color, zorder=3))
    ax_w.text(1, 2, label_client, ha='center', va='center', color='#000000', fontsize=9, fontweight='bold', zorder=4)
    ax_w.add_patch(patches.Circle((3, 2), 0.28, color=l2_color, zorder=3))
    ax_w.text(3, 2, label_l2, ha='center', va='center', color='#ffffff', fontsize=9, fontweight='bold', zorder=4)
    
    ax_w.add_patch(patches.Circle((1, 1), 0.25, color=client_color, zorder=3))
    ax_w.text(1, 1, label_client, ha='center', va='center', color='#000000', fontsize=9, fontweight='bold', zorder=4)
    ax_w.add_patch(patches.Circle((3, 1), 0.28, color=l1_color, zorder=3))
    ax_w.text(3, 1, label_l1, ha='center', va='center', color='#ffffff', fontsize=9, fontweight='bold', zorder=4)
    
    ax_w.add_patch(patches.RegularPolygon(xy=(5.2, 2), numVertices=5, radius=0.35, color=origin_color, zorder=3))
    ax_w.text(5.2, 2, label_origin, ha='center', va='center', color='#000000', fontsize=9, fontweight='bold', zorder=4)
    
    ax_w.annotate('', xy=(2.72, 3), xytext=(1.25, 3), arrowprops=dict(arrowstyle="->", color='#8b949e', lw=2))
    ax_w.annotate('', xy=(2.72, 2), xytext=(1.25, 2), arrowprops=dict(arrowstyle="->", color='#8b949e', lw=2))
    ax_w.annotate('', xy=(2.72, 1), xytext=(1.25, 1), arrowprops=dict(arrowstyle="->", color='#8b949e', lw=2))
    
    ax_w.annotate('', xy=(4.9, 2.1), xytext=(3.28, 3), arrowprops=dict(arrowstyle="->", color='#ff7675', lw=2, linestyle='--'))
    ax_w.annotate('', xy=(4.9, 2.0), xytext=(3.28, 2), arrowprops=dict(arrowstyle="->", color='#ff7675', lw=2, linestyle='--'))
    ax_w.annotate('', xy=(4.9, 1.9), xytext=(3.28, 1), arrowprops=dict(arrowstyle="->", color='#ff7675', lw=2, linestyle='--'))
    
    if is_ko:
        ax_w.text(2, 3.15, "로컬 요청", color='#8b949e', fontsize=8, ha='center', va='center',
                  bbox=dict(boxstyle='round,pad=0.2', facecolor='#0c1017', edgecolor='none', alpha=0.9))
        ax_w.text(4.1, 2.85, "캐시 미스 시\n오리진 직접 요청", color='#ff7675', fontsize=8, ha='center', va='center',
                  bbox=dict(boxstyle='round,pad=0.2', facecolor='#0c1017', edgecolor='none', alpha=0.9))
    else:
        ax_w.text(2, 3.15, "Local Req", color='#8b949e', fontsize=8, ha='center', va='center',
                  bbox=dict(boxstyle='round,pad=0.2', facecolor='#0c1017', edgecolor='none', alpha=0.9))
        ax_w.text(4.1, 2.85, "Direct Request\non Miss", color='#ff7675', fontsize=8, ha='center', va='center',
                  bbox=dict(boxstyle='round,pad=0.2', facecolor='#0c1017', edgecolor='none', alpha=0.9))

    ax_w.text(1, 0.2, desc_width, fontsize=10, color='#c9d1d9', va='top', ha='left',
              bbox=dict(boxstyle='round,pad=0.5', facecolor='#161b22', edgecolor='#30363d', alpha=0.8))
              
    ax_w.set_xlim(0.3, 5.9)
    ax_w.set_ylim(-0.2, 3.6)
    ax_w.axis('off')
    
    width_path = f'/home/donghwi/cloud_network_project/korea_cdn_topology_width_{lang}.png'
    plt.savefig(width_path, dpi=300, facecolor=bg_color, bbox_inches='tight')
    plt.close(fig_w)
    print(f"-> 개별 Width개념도({lang}) 저장 완료: {width_path}")

    # --- 1-2. Depth 단독 저장 ---
    fig_d, ax_d = plt.subplots(figsize=(8, 6))
    fig_d.patch.set_facecolor(bg_color)
    ax_d.set_facecolor(bg_color)
    ax_d.set_title(title_depth, fontsize=14, fontweight='bold', color=text_color, pad=15)
    
    ax_d.add_patch(patches.Circle((1.0, 2), 0.28, color=client_color, zorder=3))
    ax_d.text(1.0, 2, label_client, ha='center', va='center', color='#000000', fontsize=9, fontweight='bold', zorder=4)
    
    ax_d.add_patch(patches.Circle((2.2, 2), 0.28, color=l1_color, zorder=3))
    ax_d.text(2.2, 2, label_l1, ha='center', va='center', color='#ffffff', fontsize=9, fontweight='bold', zorder=4)
    
    ax_d.add_patch(patches.Circle((3.4, 2), 0.28, color=l2_color, zorder=3))
    ax_d.text(3.4, 2, label_l2, ha='center', va='center', color='#ffffff', fontsize=9, fontweight='bold', zorder=4)
    
    ax_d.add_patch(patches.Circle((4.6, 2), 0.28, color=l3_color, zorder=3))
    ax_d.text(4.6, 2, label_l3, ha='center', va='center', color='#ffffff', fontsize=9, fontweight='bold', zorder=4)
    
    ax_d.add_patch(patches.RegularPolygon(xy=(5.8, 2), numVertices=5, radius=0.35, color=origin_color, zorder=3))
    ax_d.text(5.8, 2, label_origin, ha='center', va='center', color='#000000', fontsize=9, fontweight='bold', zorder=4)
    
    ax_d.annotate('', xy=(1.92, 2), xytext=(1.28, 2), arrowprops=dict(arrowstyle="->", color='#8b949e', lw=2))
    ax_d.annotate('', xy=(3.12, 2), xytext=(2.48, 2), arrowprops=dict(arrowstyle="->", color='#a29bfe', lw=2, linestyle='-'))
    ax_d.annotate('', xy=(4.32, 2), xytext=(3.68, 2), arrowprops=dict(arrowstyle="->", color='#74b9ff', lw=2, linestyle='-'))
    ax_d.annotate('', xy=(5.5, 2), xytext=(4.88, 2), arrowprops=dict(arrowstyle="->", color='#ff7675', lw=2, linestyle='-'))
    
    if is_ko:
        ax_d.text(1.6, 2.15, "1. 로컬 요청", color='#8b949e', fontsize=7.5, ha='center')
        ax_d.text(2.8, 2.15, "2. L1 미스 시\nL2 전달", color='#a29bfe', fontsize=7.5, ha='center')
        ax_d.text(4.0, 2.15, "3. L2 미스 시\nL3 전달", color='#74b9ff', fontsize=7.5, ha='center')
        ax_d.text(5.2, 2.15, "4. L3 미스 시\n최종 오리진", color='#ff7675', fontsize=7.5, ha='center')
    else:
        ax_d.text(1.6, 2.15, "1. Local Req", color='#8b949e', fontsize=7.5, ha='center')
        ax_d.text(2.8, 2.15, "2. L1 Miss\nForward to L2", color='#a29bfe', fontsize=7.5, ha='center')
        ax_d.text(4.0, 2.15, "3. L2 Miss\nForward to L3", color='#74b9ff', fontsize=7.5, ha='center')
        ax_d.text(5.2, 2.15, "4. L3 Miss\nFetch Origin", color='#ff7675', fontsize=7.5, ha='center')

    ax_d.text(0.7, 0.2, desc_depth, fontsize=10, color='#c9d1d9', va='top', ha='left',
              bbox=dict(boxstyle='round,pad=0.5', facecolor='#161b22', edgecolor='#30363d', alpha=0.8))
              
    ax_d.set_xlim(0.3, 6.5)
    ax_d.set_ylim(-0.2, 3.6)
    ax_d.axis('off')
    
    depth_path = f'/home/donghwi/cloud_network_project/korea_cdn_topology_depth_{lang}.png'
    plt.savefig(depth_path, dpi=300, facecolor=bg_color, bbox_inches='tight')
    plt.close(fig_d)
    print(f"-> 개별 Depth개념도({lang}) 저장 완료: {depth_path}")

# 다이어그램 생성
draw_diagram('ko')
draw_diagram('en')

# 복사
artifact_dir = '/home/donghwi/.gemini/antigravity-cli/brain/21aedd55-43a5-420e-b722-9c5a4be1bd05'
if os.path.exists(artifact_dir):
    shutil.copy('/home/donghwi/cloud_network_project/korea_cdn_topology_ko.png', os.path.join(artifact_dir, 'korea_cdn_topology_ko.png'))
    shutil.copy('/home/donghwi/cloud_network_project/korea_cdn_topology_en.png', os.path.join(artifact_dir, 'korea_cdn_topology_en.png'))
    
    # 개별 분할 개념도 복사
    for lang in ['ko', 'en']:
        shutil.copy(f'/home/donghwi/cloud_network_project/korea_cdn_topology_width_{lang}.png', os.path.join(artifact_dir, f'korea_cdn_topology_width_{lang}.png'))
        shutil.copy(f'/home/donghwi/cloud_network_project/korea_cdn_topology_depth_{lang}.png', os.path.join(artifact_dir, f'korea_cdn_topology_depth_{lang}.png'))
        
    print("-> Artifacts 디렉토리에 모든 개념 다이어그램 복사 완료!")
