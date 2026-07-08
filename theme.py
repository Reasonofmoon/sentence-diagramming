"""K-Jumak(현대적 국밥 주막) 프리미엄 웜톤 테마 — 국밥맨 AI 컨셉을 도해 출력에 이식.

단일 색 소스. 모든 렌더러(reedkellogg / bento / a4report / analyzer)가 여기서
색을 가져온다. "진국 지문 분석탕" 컨셉:
- 복잡도 = 온도(매운맛). 다대기 오렌지(100°) → 수저 골드(70°) → 청양 그린(40°).
- 웜 잉크(뚝배기 브라운) + 육수 미색 배경 + 형광펜 하이라이트.
"""

# ---- K-Jumak 팔레트 (designer style guide) ----
TTUKBAEGI_BROWN = "#4A2312"   # 주조색: 잉크/baseline/테두리
DADAEGI_ORANGE  = "#FF5722"   # 강조/고온/대조
CHEONGYANG_GREEN = "#6D8C7C"  # 양념 키워드/근거/전치사구(직독직해)
YUKSU_IVORY     = "#FAF6EE"   # 메인 배경
RICE_WHITE      = "#FFFFFF"   # 카드 표면
GGADUGI_RED     = "#D32F2F"   # 에러/오답/반론
SUJEO_GOLD      = "#D4AF37"   # 프리미엄/주장·결론

# ---- 도해 의미 매핑 ----
INK        = TTUKBAEGI_BROWN     # 본문 글자·baseline
LABEL_COL  = "#8A6E5D"           # 성분 라벨(브라운 그레이)
BASELINE   = "#5A3A26"           # baseline 선(약간 옅은 브라운)
PREP_COL   = CHEONGYANG_GREEN    # 전치사구(양념)
CONNECT_COL = DADAEGI_ORANGE     # 절 연결자(관계대명사/접속사) — 뜨거운 연결
PAGE_BG    = YUKSU_IVORY
CARD_BG    = RICE_WHITE

# ---- 온도(복잡도) 메터: 순위/난이도 → 색 ----
# rank 0(가장 복잡=매운맛 100°) → 2(순한맛 40°)
TEMP_COLORS = [DADAEGI_ORANGE, SUJEO_GOLD, CHEONGYANG_GREEN]
TEMP_LABELS = ["100°", "70°", "40°"]


def temp_color(rank):
    """복잡도 순위(0=최상위) → 온도 색. 범위를 넘으면 마지막(순한맛)."""
    return TEMP_COLORS[min(rank, len(TEMP_COLORS) - 1)]


def temp_label(rank):
    return TEMP_LABELS[min(rank, len(TEMP_LABELS) - 1)]


def with_alpha(hex_color, alpha):
    """#RRGGBB + alpha(0~1) → matplotlib RGBA 튜플 (형광펜/글라스 틴트용)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return (r, g, b, alpha)
