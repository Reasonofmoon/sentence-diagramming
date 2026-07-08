"""벤또 그리드 리포트 — 가장 복잡한 문장 3개를 카드형으로 A4 한 장에.

각 카드: 순위 배지 + 복잡도 점수 + 특징 태그 헤더 바 + RK 도해 본문.
카드 높이는 문장 복잡도(RK 절 수)에 비례 배분 → 빽빽하지만 각 도해가 눌리지 않음.
인쇄 친화적: 벡터 PDF, 옅은 배경 틴트, 명료한 카드 경계.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.backends.backend_pdf import PdfPages

import complexity
import reedkellogg as rk

A4_W, A4_H = 8.27, 11.69
MARGIN = 0.5

try:
    import theme as _t
    INK = _t.INK
    _SUB_COL = _t.LABEL_COL
    _PAGE_BG = _t.PAGE_BG
    # 온도 메터: 복잡도 순위 → 매운맛(오렌지) → 보통(골드) → 순한맛(그린)
    RANK_EDGE = [_t.temp_color(0), _t.temp_color(1), _t.temp_color(2)]
    RANK_BADGE = RANK_EDGE
    RANK_TINT = [_t.with_alpha(c, 0.13) for c in RANK_EDGE]
except Exception:
    INK = "#1a1a1a"
    _SUB_COL = "#5a6b7a"
    _PAGE_BG = "#FAF6EE"
    RANK_TINT = ["#eef4fc", "#f4f8fd", "#f8fafc"]
    RANK_EDGE = ["#2b6cb0", "#5a8fc0", "#9db8d0"]
    RANK_BADGE = ["#2b6cb0", "#4a7fb5", "#6f95bc"]


def _setup_font():
    import matplotlib.font_manager as fm
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "fonts", "NanumGothic.ttf"),
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                fm.fontManager.addfont(p)
                plt.rcParams["font.family"] = \
                    fm.FontProperties(fname=p).get_name()
                break
            except Exception:
                continue
    plt.rcParams["axes.unicode_minus"] = False


def _draw_card(fig, bgax, rect, cscore, rank, template):
    """rect=(x0,y0,w,h) figure 좌표(0-1). 배경은 bgax(전면 배경축)에, 내용은 새 axes에."""
    x0, y0, w, h = rect
    # 카드 배경 + 경계 → 배경 axes에 그려 내용 axes보다 아래층 보장
    bgax.add_patch(FancyBboxPatch(
        (x0, y0), w, h, transform=fig.transFigure,
        boxstyle="round,pad=0.004,rounding_size=0.012",
        facecolor=RANK_TINT[rank], edgecolor=RANK_EDGE[rank],
        lw=1.4, clip_on=False))

    # 헤더 바 axes (카드 상단 얇은 띠)
    bar_h = min(0.048, h * 0.2)
    axb = fig.add_axes([x0 + 0.008, y0 + h - bar_h - 0.004, w - 0.016, bar_h])
    axb.axis("off")
    axb.set_xlim(0, 1); axb.set_ylim(0, 1)
    # 순위 배지
    axb.add_patch(Rectangle((0.0, 0.1), 0.06, 0.8, transform=axb.transAxes,
                            facecolor=RANK_BADGE[rank], edgecolor="none"))
    axb.text(0.03, 0.5, f"{rank+1}", ha="center", va="center",
             fontsize=13, fontweight="bold", color="white")
    try:
        _temp = _t.temp_label(rank)
    except Exception:
        _temp = ""
    axb.text(0.08, 0.66,
             f"원문 S{cscore.idx+1}  ·  복잡도 {cscore.score}  ·  난이도 {_temp}",
             ha="left", va="center", fontsize=8.5, fontweight="bold", color=INK)
    axb.text(0.08, 0.24, cscore.features_kr(), ha="left", va="center",
             fontsize=6.6, color=_SUB_COL)
    # 원문(오른쪽 정렬, 헤더 바 안)
    txt = cscore.text if len(cscore.text) <= 78 else cscore.text[:77] + "…"
    axb.text(1.0, 0.5, txt, ha="right", va="center", fontsize=6.4,
             color=_SUB_COL, fontstyle="italic")

    # 본문 axes (RK 도해)
    body_h = h - bar_h - 0.016
    axd = fig.add_axes([x0 + 0.014, y0 + 0.008, w - 0.028, body_h])
    rk.draw_sentence_rk_from_text(axd, cscore.text, title="")


def _render(fig, analysis, k, title, template):
    """공통 렌더 로직 — PNG/PDF가 공유."""
    tops = complexity.top_complex(analysis, k)
    if not tops:
        raise ValueError("문장이 없습니다.")
    # 전면 배경 axes (카드 배경 전용, 최하층) — 육수 미색으로 주막 톤
    fig.patch.set_facecolor(_PAGE_BG)
    bgax = fig.add_axes([0, 0, 1, 1]); bgax.axis("off")
    bgax.set_xlim(0, 1); bgax.set_ylim(0, 1); bgax.set_zorder(-10)
    bgax.add_patch(Rectangle((0, 0), 1, 1, transform=bgax.transAxes,
                             facecolor=_PAGE_BG, edgecolor="none", zorder=-20))

    # 헤더
    axh = fig.add_axes([MARGIN / A4_W, 1 - (MARGIN + 0.35) / A4_H,
                        1 - 2 * MARGIN / A4_W, 0.35 / A4_H])
    axh.axis("off")
    tag = "[교사용]" if template == "teacher" else "[학생용]"
    axh.text(0, 0.6, f"{title}  {tag}", fontsize=15, fontweight="bold",
             color=INK, va="center")
    axh.text(1, 0.6, f"진국 지문 분석탕 · 상위 {len(tops)}문장 · Reed–Kellogg 도해",
             fontsize=8.5, color=_SUB_COL, ha="right", va="center")

    # 카드 영역
    top_y = 1 - (MARGIN + 0.5) / A4_H
    bot_y = MARGIN / A4_H
    total_h = top_y - bot_y
    left_x = MARGIN / A4_W
    card_w = 1 - 2 * MARGIN / A4_W
    gap = 0.014
    weights = [max(1.4, c.n_clauses) for c in tops]
    wsum = sum(weights)
    avail = total_h - gap * (len(tops) - 1)
    cy = top_y
    for rank, c in enumerate(tops):
        ch = avail * (weights[rank] / wsum)
        cy -= ch
        _draw_card(fig, bgax, (left_x, cy, card_w, ch), c, rank, template)
        cy -= gap
    return tops


def build_bento_pdf(analysis, path="bento.pdf", k=3,
                    title="복잡한 문장 집중 분석", template="teacher"):
    _setup_font()
    fig = plt.figure(figsize=(A4_W, A4_H))
    _render(fig, analysis, k, title, template)
    fig.savefig(path, format="pdf", facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def build_bento_png(analysis, path="bento.png", k=3,
                    title="복잡한 문장 집중 분석", template="teacher", dpi=130):
    _setup_font()
    fig = plt.figure(figsize=(A4_W, A4_H))
    _render(fig, analysis, k, title, template)
    fig.savefig(path, dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path
