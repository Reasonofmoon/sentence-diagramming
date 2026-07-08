"""
a4report.py — 분석 결과를 A4 인쇄친화적 벡터 PDF로 출력.
문장 의존구조 다이어그램 + 글 흐름(담화표지) 다이어그램을 한 지면에 전문적으로 배치.

옵션:
    template   : "teacher" (정답 강조 · 색상/라벨 전부) | "student" (빈칸 워크시트)
    flow_style : "linear" (담화표지 흐름 스택) | "rst" (RST 담화 나무)
    layout     : "full" (다중 페이지) | "compact" (1페이지 요약: 흐름 + 문장)

핵심 함수:
    build_a4_pdf(analysis, path="report.pdf", template=, flow_style=, layout=) -> path
    build_a4_png(analysis, path="report.png", ...) -> [png paths]   (미리보기용)
"""
from __future__ import annotations
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.patches import FancyBboxPatch, PathPatch
from matplotlib.path import Path
from matplotlib.backends.backend_pdf import PdfPages

from analyzer import RELATION_STYLE, ROLE_STYLE
from diagram import DEP_KR

# ---- 한글 폰트 자동 등록 (있으면 사용) ----
def _setup_font():
    candidates = [
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for p in candidates:
        try:
            fm.fontManager.addfont(p)
            name = fm.FontProperties(fname=p).get_name()
            plt.rcParams["font.family"] = name
            break
        except Exception:
            continue
    plt.rcParams["axes.unicode_minus"] = False

_setup_font()

# A4 세로 (인치)
A4_W, A4_H = 8.27, 11.69
MARGIN = 0.55            # 인치
CLAIM_C = ROLE_STYLE["claim"]
INK = "#1a1a1a"


# ============================================================
# 문장 의존구조를 하나의 axes에 그리기 (폭에 맞춰 자동 스케일)
# ============================================================
def _draw_sentence(ax, sent, template="teacher"):
    """template='teacher': 관계 라벨 전부. 'student': 라벨을 빈칸(____)으로 두어
    학습자가 직접 채우는 워크시트 형태 (아크·화살표는 유지, 색은 옅게)."""
    student = (template == "student")
    arc_col = "#b0b0b0" if student else "#c0392b"
    toks = sent.tokens
    n = len(toks)
    ax.set_xlim(0, max(n, 1))
    ax.axis("off")
    if n == 0:
        return
    xs = [i + 0.5 for i in range(n)]
    baseline = 0.0
    # 구두점 의존은 시각적 잡음이므로 아크에서 제외 (라벨/단어는 유지)
    def _skip(t):
        return t.dep in ("punct",) or t.dep == "ROOT" or t.head == t.i
    # 최대 아크 높이로 y 범위 결정 (구두점 제외)
    max_span = max([abs(t.head - t.i) for t in toks if not _skip(t)], default=1)
    top_y = 0.5 + 0.62 * max_span
    ax.set_ylim(-0.9, top_y + 0.5)

    # 의존 호
    for t in toks:
        if _skip(t):
            continue
        x1, x2 = xs[t.head], xs[t.i]
        span = abs(t.head - t.i)
        h = 0.45 + 0.62 * span
        verts = [(x1, baseline + 0.12), (x1, baseline + h),
                 (x2, baseline + h), (x2, baseline + 0.12)]
        codes = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4]
        ax.add_patch(PathPatch(Path(verts, codes), fill=False,
                     edgecolor=arc_col, lw=0.9, alpha=0.85))
        # 화살촉
        ax.annotate("", xy=(x2, baseline + 0.14), xytext=(x2, baseline + 0.34),
                    arrowprops=dict(arrowstyle="-|>", color=arc_col, lw=0.9))
        lab = "____" if student else DEP_KR.get(t.dep, t.dep)
        ax.text((x1 + x2) / 2, baseline + h + 0.02, lab, ha="center",
                va="bottom", fontsize=6.2,
                color="#999" if student else "#c0392b", fontweight="bold")

    # root 마커
    rx = xs[sent.root]
    ax.annotate("", xy=(rx, baseline + 0.14), xytext=(rx, baseline + 0.5),
                arrowprops=dict(arrowstyle="-|>", color="#888", lw=0.8))
    ax.text(rx, baseline + 0.55, "root", ha="center", va="bottom",
            fontsize=5.5, color="#888")

    # 단어 + 품사 (student: 품사는 빈칸)
    for i, t in enumerate(toks):
        ax.text(xs[i], baseline - 0.12, t.text, ha="center", va="top",
                fontsize=8, fontweight="bold", color=INK)
        pos = "____" if student else t.pos
        ax.text(xs[i], baseline - 0.42, pos, ha="center", va="top",
                fontsize=5.8, color="#bbb" if student else "#999")


# ============================================================
# 글 흐름 다이어그램을 하나의 axes에 그리기
# ============================================================
def _draw_flow(ax, analysis, max_chars=64, template="teacher", compact=False):
    student = (template == "student")
    sents = analysis.sentences
    n = len(sents)
    ax.set_xlim(0, 10)
    ax.axis("off")
    if n == 0:
        return
    box_h = 1.0
    gap = 0.62
    unit = box_h + gap
    total = n * unit
    ax.set_ylim(0, total + 0.2)
    left, box_w = 1.7, 7.7

    def ytop(i):  # y of box top for sentence i (top-down)
        return total - i * unit

    link_by_dst = {l.dst: l for l in analysis.links}
    for i in range(n):
        yt = ytop(i)
        yb = yt - box_h
        role = analysis.roles.get(i, "neutral")
        kr, fill, stroke = ROLE_STYLE.get(role, ROLE_STYLE["neutral"])
        if student:  # 역할 색 숨기고 중립 처리 (학습자가 판단)
            fill, stroke = "white", "#bbb"
        ax.add_patch(FancyBboxPatch((left, yb), box_w, box_h,
                     boxstyle="round,pad=0.02,rounding_size=0.12",
                     facecolor=fill, edgecolor=stroke, lw=1.2))
        # S번호=박스 상단, 역할 라벨=박스 하단 → 항상 box_h만큼 벌어져 압축돼도 안 겹침
        # compact에선 박스가 얇아 라벨이 겹치므로 S번호만(역할은 색으로 구분)
        ax.text(left - 0.15, yt - 0.06, f"S{i+1}", ha="right",
                va="top", fontsize=8.5 if not compact else 7.5, fontweight="bold",
                color="#555" if student else stroke)
        if not compact:
            rolelbl = "____" if student else kr
            ax.text(left - 0.15, yb + 0.06, rolelbl, ha="right",
                    va="bottom", fontsize=6, color="#999")
        txt = sents[i].text
        if len(txt) > max_chars:
            txt = txt[:max_chars - 1] + "…"
        ax.text(left + 0.18, yb + box_h / 2, txt, ha="left", va="center",
                fontsize=7.5, color=INK)
        # 관계 화살표
        if i in link_by_dst:
            l = link_by_dst[i]
            y_prev_bottom = ytop(i - 1) - box_h
            cx = left + box_w / 2
            ax.annotate("", xy=(cx, yt + 0.01), xytext=(cx, y_prev_bottom - 0.01),
                        arrowprops=dict(arrowstyle="-|>", color="#555", lw=1.2))
            relkr, relcol = RELATION_STYLE.get(l.relation, ("연속", "#999"))
            if student:
                # 담화표지는 힌트로 남기고 관계명은 빈칸
                mlabel = (f"____  ·  {l.marker}" if l.marker else "____")
                ecol = "#bbb"
            else:
                mlabel = relkr + (f"  ·  {l.marker}" if l.marker else "")
                ecol = relcol
            ax.text(cx + 0.15, (yt + y_prev_bottom) / 2, mlabel, ha="left",
                    va="center", fontsize=6.8,
                    color="#999" if student else relcol, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white",
                              ec=ecol, lw=0.7))


# ============================================================
# RST 담화 나무 (핵–위성) — 간이 우편향 스파인 구성
# ============================================================
# nucleus를 이루는(핵 유지) 관계 vs 위성으로 매다는(보조) 관계
_SATELLITE_RELATIONS = {"cause", "example", "concession", "contrast",
                        "condition", "addition"}


def _draw_rst_tree(ax, analysis, max_chars=42, template="teacher"):
    """왼쪽에 담화 스파인(핵 체인)을 세우고, 각 문장을 EDU 잎으로 오른쪽에 배치.
    관계에 따라 핵(굵은 세로선)–위성(가는 사선) 으로 구분한다."""
    student = (template == "student")
    sents = analysis.sentences
    n = len(sents)
    ax.set_xlim(0, 10); ax.axis("off")
    if n == 0:
        return
    row_h = 1.0
    total = n * row_h
    ax.set_ylim(-0.4, total + 0.6)
    spine_x = 1.3
    leaf_x = 3.2
    leaf_w = 6.4

    def yrow(i):
        return total - (i + 0.5) * row_h

    link_by_dst = {l.dst: l for l in analysis.links}

    # 세로 스파인 (담화 중심축)
    ax.plot([spine_x, spine_x], [yrow(n - 1), yrow(0)],
            color="#888", lw=1.4, zorder=1)
    ax.text(spine_x, yrow(0) + 0.5, "담화\n중심축", ha="center", va="bottom",
            fontsize=6, color="#888")

    for i in range(n):
        y = yrow(i)
        rel = link_by_dst[i].relation if i in link_by_dst else "root"
        is_sat = rel in _SATELLITE_RELATIONS
        role = analysis.roles.get(i, "neutral")
        kr, fill, stroke = ROLE_STYLE.get(role, ROLE_STYLE["neutral"])
        if student:
            fill, stroke = "white", "#bbb"

        # 스파인 → 잎 연결선: 핵=굵은 수평, 위성=가는 사선(아래로 매닮)
        if is_sat:
            ax.plot([spine_x, leaf_x], [y + 0.18, y], color="#c0392b",
                    lw=1.0, ls="--", zorder=1)
            tag = "위성(S)"
            tagcol = "#c0392b"
        else:
            ax.plot([spine_x, leaf_x], [y, y], color="#2b7cd3",
                    lw=2.2, zorder=1)
            tag = "핵(N)"
            tagcol = "#2b7cd3"

        # EDU 잎 박스
        ax.add_patch(FancyBboxPatch((leaf_x, y - 0.36), leaf_w, 0.72,
                     boxstyle="round,pad=0.02,rounding_size=0.08",
                     facecolor=fill, edgecolor=stroke, lw=1.1, zorder=2))
        txt = sents[i].text
        if len(txt) > max_chars:
            txt = txt[:max_chars - 1] + "…"
        ax.text(leaf_x + 0.15, y + 0.02, f"S{i+1}  {txt}", ha="left",
                va="center", fontsize=7, color=INK, zorder=3)

        # 관계 라벨 (핵/위성 태그 + 관계명)
        relkr, relcol = RELATION_STYLE.get(rel, ("중심", "#888")) \
            if rel != "root" else ("중심 주장", "#e0a800")
        if student:
            lbl = f"{tag} · ____"
        else:
            lbl = f"{tag} · {relkr}"
        ax.text(leaf_x + leaf_w + 0.15, y, lbl, ha="left", va="center",
                fontsize=6.2, color=tagcol, fontweight="bold")
    ax.set_xlim(0, leaf_x + leaf_w + 2.0)


# ============================================================
# 범례 + 담화표지 요약을 axes에 그리기
# ============================================================
def _draw_legend(ax, analysis, template="teacher"):
    student = (template == "student")
    ax.set_xlim(0, 10); ax.axis("off")
    ax.text(0, 9.6, "범례 · Legend", fontsize=8.5, fontweight="bold", color=INK)
    # 역할 색상
    x = 0
    for key, (kr, fill, stroke) in ROLE_STYLE.items():
        ax.add_patch(FancyBboxPatch((x, 8.6), 0.35, 0.35,
                     boxstyle="round,pad=0.02", fc=fill, ec=stroke, lw=1))
        ax.text(x + 0.45, 8.77, kr, fontsize=6.8, va="center", color=INK)
        x += 1.9
    # 담화표지 관계 (student: 관계명 숨기고 표지만 힌트로)
    heading = "담화 관계 (표지를 보고 관계를 채워보세요)" if student else "탐지된 담화 관계"
    ax.text(0, 7.9, heading, fontsize=8.5, fontweight="bold", color=INK)
    y = 7.3
    if analysis.links:
        for l in analysis.links:
            relkr, relcol = RELATION_STYLE.get(l.relation, ("연속", "#999"))
            mk = f"  (표지: {l.marker})" if l.marker else "  (표지 없음: 암시적)"
            ax.text(0, y, f"S{l.src+1} → S{l.dst+1}", fontsize=6.8,
                    va="center", color="#555")
            relshow = "____________" if student else relkr
            ax.text(1.7, y, relshow, fontsize=6.8, va="center",
                    color="#999" if student else relcol, fontweight="bold")
            ax.text(3.4, y, mk, fontsize=6.5, va="center", color="#999")
            y -= 0.55
            if y < 0.3:
                break
    # 실제 사용한 y범위에 맞춰 axes를 꽉 채움 → 낮은 블록에서도 안 겹침
    ax.set_ylim(min(y + 0.2, 5.0), 10)


# ============================================================
# A4 리포트 조립
# ============================================================
def _tag(template):
    return {"teacher": "교사용", "student": "학생용 워크시트"}.get(template, "")


def _header(axh, title, subtitle, template, right_label):
    axh.axis("off")
    tag = _tag(template)
    full_title = f"{title}" + (f"  [{tag}]" if tag else "")
    axh.text(0, 0.75, full_title, fontsize=15, fontweight="bold", color=INK)
    if subtitle:
        axh.text(0, 0.2, subtitle, fontsize=8.5, color="#666", style="italic",
                 wrap=True)
    axh.text(1.0, 0.75, right_label, fontsize=9, color="#999",
             ha="right", transform=axh.transAxes)


def _draw_flow_or_rst(ax, analysis, flow_style, template, compact=False):
    if flow_style == "rst":
        _draw_rst_tree(ax, analysis, template=template)
    else:
        _draw_flow(ax, analysis, template=template, compact=compact)


def _draw_one_sentence(ax, s, template, sentence_style, title):
    """문장 하나를 지정 스타일로 그린다. dep=의존구조, rk=Reed–Kellogg."""
    ax.set_title(title, loc="left", fontsize=8, fontweight="bold",
                 color=INK, pad=2)
    if sentence_style == "rk":
        import reedkellogg
        reedkellogg.draw_sentence_rk_from_text(ax, s.text, title="")
    else:
        _draw_sentence(ax, s, template=template)


def _rk_rows(s):
    """RK 도해에서 이 문장이 차지하는 절(행) 수 — 페이지 높이 배분용."""
    try:
        import reedkellogg
        return max(1, reedkellogg.n_rows(s.text))
    except Exception:
        return 1


def _rk_sentence_pages(figs, sents, title, template, MARGIN):
    """RK 문장 페이지: 절 수 예산에 맞춰 문장을 페이지에 담고,
    각 문장 axes 높이를 절 수에 비례 배분 → 어떤 문장도 눌리지 않음."""
    ROW_BUDGET = 4          # 페이지당 허용 총 절 수 (패널 높이 확보)
    pages = []
    cur, cur_rows = [], 0
    for s in sents:
        r = _rk_rows(s)
        if cur and cur_rows + r > ROW_BUDGET:
            pages.append(cur); cur, cur_rows = [], 0
        cur.append((s, r)); cur_rows += r
    if cur:
        pages.append(cur)

    npages = len(pages)
    for pg, chunk in enumerate(pages):
        fig = plt.figure(figsize=(A4_W, A4_H))
        fig.subplots_adjust(left=MARGIN / A4_W, right=1 - MARGIN / A4_W,
                            top=1 - MARGIN / A4_H, bottom=MARGIN / A4_H)
        # 각 문장 높이를 절 수에 비례 배분하되 단일 절도 넉넉히(최소 2)
        ratios = [0.4] + [max(2.0, 1.6 * r) for _, r in chunk]
        gs = fig.add_gridspec(len(chunk) + 1, 1, height_ratios=ratios,
                              hspace=0.4)
        axhh = fig.add_subplot(gs[0]); axhh.axis("off")
        pagelbl = f"  (p.{pg+1}/{npages})" if npages > 1 else ""
        tag = _tag(template)
        axhh.text(0, 0.5,
                  f"{title} — 문장 Reed–Kellogg 도해{pagelbl}"
                  + (f"  [{tag}]" if tag else ""),
                  fontsize=12, fontweight="bold", color=INK, va="center")
        for k, (s, _) in enumerate(chunk):
            ax = fig.add_subplot(gs[k + 1])
            _draw_one_sentence(ax, s, template, "rk", f"S{s.idx+1}  ·  {s.text}")
        figs.append(fig)
    return figs


def _build(analysis, title, subtitle, template="teacher",
           flow_style="linear", layout="full", sentence_style="rk"):
    sents = analysis.sentences
    n = len(sents)
    figs = []
    flow_label = ("RST 담화 나무" if flow_style == "rst"
                  else "글 흐름 (담화 구조)")

    # ============ COMPACT: 1페이지 (흐름 + 문장 요약) ============
    if layout == "compact":
        fig = plt.figure(figsize=(A4_W, A4_H))
        fig.subplots_adjust(left=MARGIN / A4_W, right=1 - MARGIN / A4_W,
                            top=1 - MARGIN / A4_H, bottom=MARGIN / A4_H)
        # 헤더 / 흐름 / 문장 스택
        # RK 도해는 세로 공간이 크므로 compact에서 문장 수를 줄이고 흐름은 축소
        if sentence_style == "rk":
            n_sent_slots = min(n, 3)
            flow_ratio = 0.7 + 0.1 * n
            sent_ratios = [max(1.4, 1.2 * _rk_rows(sents[k]))
                           for k in range(n_sent_slots)]
        else:
            n_sent_slots = min(n, 5)
            flow_ratio = 0.9 + 0.15 * n
            sent_ratios = [1] * n_sent_slots
        gs = fig.add_gridspec(2 + n_sent_slots, 1,
                              height_ratios=[0.35, flow_ratio] + sent_ratios,
                              hspace=0.5)
        # compact: 헤더가 짧아 부제목이 겹치므로 생략 (문장 박스가 지문을 대신 표시)
        _header(fig.add_subplot(gs[0]), title, "", template, "1페이지 요약")
        _draw_flow_or_rst(fig.add_subplot(gs[1]), analysis, flow_style, template,
                          compact=True)
        for k in range(n_sent_slots):
            ax = fig.add_subplot(gs[k + 2])
            if k < n:
                s = sents[k]
                role = analysis.roles.get(s.idx, "neutral")
                kr = ROLE_STYLE.get(role, ("",))[0]
                rlbl = "" if template == "student" else f" ({kr})"
                _draw_one_sentence(ax, s, template, sentence_style,
                                   f"S{s.idx+1}{rlbl}  ·  {s.text}")
            else:
                ax.axis("off")
        if n > n_sent_slots:
            fig.text(0.5, 0.015,
                     f"(문장 {n_sent_slots+1}–{n}은 전체(full) 레이아웃에서 확인)",
                     ha="center", fontsize=7, color="#999")
        figs.append(fig)
        return figs

    # ============ FULL: 페이지 1 = 흐름 + 범례 ============
    fig = plt.figure(figsize=(A4_W, A4_H))
    fig.subplots_adjust(left=MARGIN / A4_W, right=1 - MARGIN / A4_W,
                        top=1 - MARGIN / A4_H, bottom=MARGIN / A4_H)
    gs = fig.add_gridspec(3, 1, height_ratios=[0.12, 0.62, 0.26], hspace=0.12)
    _header(fig.add_subplot(gs[0]), title, subtitle, template, flow_label)
    _draw_flow_or_rst(fig.add_subplot(gs[1]), analysis, flow_style, template)
    _draw_legend(fig.add_subplot(gs[2]), analysis, template=template)
    figs.append(fig)

    # ---- 페이지 2+: 문장 다이어그램 ----
    if sentence_style == "rk":
        # RK: 절 수에 따라 문장을 페이지에 배분 (눌림 없음)
        _rk_sentence_pages(figs, sents, title, template, MARGIN)
        return figs

    # dep: 페이지당 4문장 고정 슬롯
    per_page = 4
    npages = (n + per_page - 1) // per_page
    for pg in range(npages):
        chunk = sents[pg * per_page:(pg + 1) * per_page]
        fig = plt.figure(figsize=(A4_W, A4_H))
        fig.subplots_adjust(left=MARGIN / A4_W, right=1 - MARGIN / A4_W,
                            top=1 - MARGIN / A4_H, bottom=MARGIN / A4_H)
        gs = fig.add_gridspec(per_page + 1, 1,
                              height_ratios=[0.5] + [2] * per_page, hspace=0.55)
        axhh = fig.add_subplot(gs[0]); axhh.axis("off")
        pagelbl = f"  (p.{pg+1}/{npages})" if npages > 1 else ""
        tag = _tag(template)
        axhh.text(0, 0.5,
                  f"{title} — 문장 의존구조{pagelbl}" + (f"  [{tag}]" if tag else ""),
                  fontsize=12, fontweight="bold", color=INK, va="center")
        for k in range(per_page):
            ax = fig.add_subplot(gs[k + 1])
            if k < len(chunk):
                s = chunk[k]
                role = analysis.roles.get(s.idx, "neutral")
                kr = ROLE_STYLE.get(role, ("",))[0]
                rlbl = "" if template == "student" else f" ({kr})"
                ax.set_title(f"S{s.idx+1}{rlbl}  ·  {s.text}", loc="left",
                             fontsize=8, fontweight="bold", color=INK, pad=2)
                _draw_sentence(ax, s, template=template)
            else:
                ax.axis("off")
        figs.append(fig)
    return figs


def _subtitle(analysis, subtitle):
    if subtitle is None:
        subtitle = " ".join(s.text for s in analysis.sentences)
        if len(subtitle) > 220:
            subtitle = subtitle[:219] + "…"
    return subtitle


def build_a4_pdf(analysis, path="report.pdf",
                 title="지문 구조 분석 리포트", subtitle=None,
                 template="teacher", flow_style="linear", layout="full",
                 sentence_style="rk"):
    """template: 'teacher'|'student' · flow_style: 'linear'|'rst' ·
    layout: 'full'|'compact'|'bento' · sentence_style: 'rk'(Reed–Kellogg)|'dep'(의존구조)
    layout='bento' → 가장 복잡한 3문장만 벤또 카드 그리드로 (RK 고정)"""
    if layout == "bento":
        import bento
        return bento.build_bento_pdf(analysis, path, k=3, template=template)
    figs = _build(analysis, title, _subtitle(analysis, subtitle),
                  template=template, flow_style=flow_style, layout=layout,
                  sentence_style=sentence_style)
    with PdfPages(path) as pdf:
        for f in figs:
            pdf.savefig(f)
            plt.close(f)
    return path


def build_a4_png(analysis, path="report.png",
                 title="지문 구조 분석 리포트", subtitle=None,
                 template="teacher", flow_style="linear", layout="full",
                 sentence_style="rk", dpi=130):
    if layout == "bento":
        import bento
        return [bento.build_bento_png(analysis, path.replace(".png", "_p1.png"),
                                      k=3, template=template, dpi=dpi)]
    figs = _build(analysis, title, _subtitle(analysis, subtitle),
                  template=template, flow_style=flow_style, layout=layout,
                  sentence_style=sentence_style)
    out = []
    for i, f in enumerate(figs):
        p = path.replace(".png", f"_p{i+1}.png")
        f.savefig(p, dpi=dpi, facecolor="white")
        plt.close(f)
        out.append(p)
    return out


# ============================================================
# Smart layout — 다이어그램을 블록 객체화 → 페이지 안 잘림 + 편집 훅
# ============================================================
def _axes_at(fig, rect):
    """rect=(x0,y0,w,h) figure-fraction → axes 생성."""
    ax = fig.add_axes(list(rect)); ax.axis("off")
    return ax


def _est_sentence_height(s, sentence_style):
    """문장 블록의 필요 높이(인치) 추정 — RK는 절 수, dep는 고정."""
    if sentence_style == "rk":
        try:
            import reedkellogg
            rows = max(1, reedkellogg.n_rows(s.text))
        except Exception:
            rows = 1
        return 1.25 + 1.35 * rows        # 절마다 세로 증가
    return 2.1                            # 의존구조: 고정


def build_blocks(analysis, title, template="teacher", flow_style="linear",
                 sentence_style="rk", include=None, one_per_page=False,
                 with_flow=True, with_legend=True):
    """분석 결과를 Block 리스트로 객체화. Smart editor 훅:
       include: 포함할 문장 idx 집합/리스트 (None=전체)
       one_per_page: 문장마다 단독 페이지
       with_flow/with_legend: 흐름/범례 블록 포함 여부
    """
    import smartlayout as SL
    sents = analysis.sentences
    if include is not None:
        inc = set(include)
        sents = [s for s in sents if s.idx in inc]
    blocks = []

    # 헤더 (다음 블록과 붙임)
    blocks.append(SL.Block(
        kind="header", height_in=0.6, key="header", keep_with_next=True,
        draw=lambda fig, r: _header(_axes_at(fig, r), title,
                                    "", template, "Smart 레이아웃")))

    # 흐름 다이어그램
    if with_flow:
        flow_h = 1.4 + 0.55 * len(sents)
        blocks.append(SL.Block(
            kind="flow", height_in=min(flow_h, 6.5), key="flow",
            draw=lambda fig, r: _draw_flow_or_rst(
                _axes_at(fig, r), analysis, flow_style, template)))
        if with_legend:
            blocks.append(SL.Block(
                kind="legend", height_in=1.1, key="legend",
                page_break_before=False,
                draw=lambda fig, r: _draw_legend(
                    _axes_at(fig, r), analysis, template)))

    # 문장 블록들 (RK 또는 의존구조)
    for s in sents:
        h = _est_sentence_height(s, sentence_style)
        role = analysis.roles.get(s.idx, "neutral")
        kr = ROLE_STYLE.get(role, ("",))[0]
        rlbl = "" if template == "student" else f" ({kr})"
        ttl = f"S{s.idx+1}{rlbl}  ·  {s.text}"

        def _mk(s=s, ttl=ttl):
            def draw(fig, r):
                _draw_one_sentence(_axes_at(fig, r), s, template,
                                   sentence_style, ttl)
            return draw

        blocks.append(SL.Block(
            kind="sentence", height_in=h, key=f"sent-{s.idx}",
            page_break_before=one_per_page,
            draw=_mk()))
    return blocks


def build_smart_pdf(analysis, path="report_smart.pdf",
                    title="지문 구조 분석 리포트", template="teacher",
                    flow_style="linear", sentence_style="rk",
                    include=None, one_per_page=False, justify=True):
    """페이지가 잘리지 않는 스마트 레이아웃 PDF."""
    import smartlayout as SL
    _setup_font()
    blocks = build_blocks(analysis, title, template, flow_style,
                          sentence_style, include=include,
                          one_per_page=one_per_page)
    paths, npages = SL.render_pages(blocks, path, justify=justify, as_pdf=True)
    return paths[0], npages


def build_smart_png(analysis, path="report_smart.png",
                    title="지문 구조 분석 리포트", template="teacher",
                    flow_style="linear", sentence_style="rk",
                    include=None, one_per_page=False, justify=True, dpi=130):
    import smartlayout as SL
    _setup_font()
    blocks = build_blocks(analysis, title, template, flow_style,
                          sentence_style, include=include,
                          one_per_page=one_per_page)
    paths, npages = SL.render_pages(blocks, path, justify=justify,
                                    as_pdf=False, dpi=dpi)
    return paths, npages
