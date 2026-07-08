"""
diagram.py — SVG 다이어그램 렌더러
- render_sentence_svg: 문장 의존구조 다이어그램 (핵어→의존어 호 + 라벨)
- render_flow_svg: 글 흐름 다이어그램 (문장 노드 + 담화관계 화살표)
"""
from __future__ import annotations
import html
from analyzer import RELATION_STYLE, ROLE_STYLE

# 주요 의존관계 라벨 한글 병기
DEP_KR = {
    "nsubj": "주어", "nsubjpass": "주어(수동)", "dobj": "목적어", "obj": "목적어",
    "iobj": "간접목적어", "amod": "형용사수식", "advmod": "부사수식",
    "det": "한정사", "prep": "전치사", "pobj": "전치사목적어", "aux": "조동사",
    "auxpass": "조동사(수동)", "cc": "등위접속", "conj": "접속어",
    "compound": "복합어", "poss": "소유격", "attr": "보어", "acomp": "형용사보어",
    "ccomp": "절보어", "xcomp": "절보어", "relcl": "관계절", "advcl": "부사절",
    "mark": "종속표지", "prt": "불변화사", "neg": "부정", "npadvmod": "명사부사",
    "case": "격표지", "nmod": "명사수식", "ROOT": "핵(root)",
}


def _esc(s: str) -> str:
    return html.escape(str(s), quote=True)


# ============================================================
# 문장 의존구조 다이어그램
# ============================================================
def render_sentence_svg(sent, width_per_token: int = 110,
                        height: int = 220, font: str = "sans-serif") -> str:
    toks = sent.tokens
    n = len(toks)
    if n == 0:
        return "<svg xmlns='http://www.w3.org/2000/svg' width='100' height='40'></svg>"
    pad = 60
    W = max(pad * 2 + width_per_token * (n - 1) + 40, 320)
    H = height
    baseline = H - 55
    xs = [pad + i * width_per_token for i in range(n)]

    parts = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' "
             f"font-family='{font}' font-size='14'>"]
    parts.append(f"<defs><marker id='arrow' markerWidth='9' markerHeight='9' "
                 f"refX='7' refY='3' orient='auto' markerUnits='strokeWidth'>"
                 f"<path d='M0,0 L7,3 L0,6 z' fill='#c0392b'/></marker></defs>")

    # 의존 호
    for t in toks:
        if t.dep == "ROOT" or t.head == t.i:
            continue
        x1, x2 = xs[t.head], xs[t.i]
        span = abs(t.head - t.i)
        arc_h = 30 + 26 * span
        top = baseline - arc_h
        mx = (x1 + x2) / 2
        # 라벨
        lab = DEP_KR.get(t.dep, t.dep)
        parts.append(
            f"<path d='M{x1},{baseline-14} C{x1},{top} {x2},{top} {x2},{baseline-14}' "
            f"fill='none' stroke='#c0392b' stroke-width='1.4' marker-end='url(#arrow)' "
            f"opacity='0.85'/>")
        parts.append(
            f"<text x='{mx}' y='{top+2}' text-anchor='middle' fill='#c0392b' "
            f"font-size='11' font-weight='bold'>{_esc(lab)}</text>")

    # root 표시
    rx = xs[sent.root]
    parts.append(f"<line x1='{rx}' y1='{baseline-14}' x2='{rx}' y2='{baseline-40}' "
                 f"stroke='#777' stroke-width='1.3' marker-end='url(#arrow)'/>")
    parts.append(f"<text x='{rx}' y='{baseline-44}' text-anchor='middle' "
                 f"fill='#777' font-size='10'>root</text>")

    # 단어 + 품사
    for i, t in enumerate(toks):
        parts.append(f"<text x='{xs[i]}' y='{baseline}' text-anchor='middle' "
                     f"font-weight='bold' fill='#1a1a1a'>{_esc(t.text)}</text>")
        parts.append(f"<text x='{xs[i]}' y='{baseline+18}' text-anchor='middle' "
                     f"fill='#999' font-size='10'>{_esc(t.pos)}</text>")
    parts.append("</svg>")
    return "".join(parts)


# ============================================================
# 글 흐름 다이어그램 (세로 스택 + 관계 화살표)
# ============================================================
def render_flow_svg(analysis, font: str = "sans-serif", max_chars: int = 70) -> str:
    sents = analysis.sentences
    n = len(sents)
    if n == 0:
        return "<svg xmlns='http://www.w3.org/2000/svg' width='100' height='40'></svg>"

    box_w, box_h, gap = 560, 60, 46
    left = 210
    W = left + box_w + 60
    H = 40 + n * (box_h + gap)

    parts = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' "
             f"font-family='{font}' font-size='13'>"]
    parts.append("<defs>"
                 "<marker id='fa' markerWidth='10' markerHeight='10' refX='7' refY='3' "
                 "orient='auto'><path d='M0,0 L7,3 L0,6 z' fill='#555'/></marker>"
                 "</defs>")

    ys = [30 + i * (box_h + gap) for i in range(n)]

    # 관계 화살표 (문장 i-1 -> i)
    link_by_dst = {l.dst: l for l in analysis.links}
    for i in range(n):
        y = ys[i]
        role = analysis.roles.get(i, "neutral")
        kr, fill, stroke = ROLE_STYLE.get(role, ROLE_STYLE["neutral"])
        # 박스
        parts.append(f"<rect x='{left}' y='{y}' width='{box_w}' height='{box_h}' rx='10' "
                     f"fill='{fill}' stroke='{stroke}' stroke-width='1.6'/>")
        # 문장 번호 + 역할
        parts.append(f"<text x='{left-14}' y='{y+box_h/2+5}' text-anchor='end' "
                     f"font-weight='bold' fill='{stroke}'>S{i+1}</text>")
        parts.append(f"<text x='{left-14}' y='{y+box_h/2+22}' text-anchor='end' "
                     f"fill='#999' font-size='10'>{_esc(kr)}</text>")
        # 문장 텍스트 (자르기)
        txt = sents[i].text
        if len(txt) > max_chars:
            txt = txt[:max_chars - 1] + "…"
        parts.append(f"<text x='{left+16}' y='{y+box_h/2+5}' fill='#1a1a1a'>"
                     f"{_esc(txt)}</text>")
        # 화살표 + 관계 라벨
        if i in link_by_dst:
            l = link_by_dst[i]
            y0 = ys[i - 1] + box_h
            relkr, relcol = RELATION_STYLE.get(l.relation, ("연속", "#999"))
            parts.append(f"<line x1='{left+box_w/2}' y1='{y0}' "
                         f"x2='{left+box_w/2}' y2='{y-2}' stroke='#555' "
                         f"stroke-width='1.6' marker-end='url(#fa)'/>")
            mlabel = relkr + (f" · {l.marker}" if l.marker else "")
            parts.append(f"<rect x='{left+box_w/2+8}' y='{y0+gap/2-11}' "
                         f"width='{max(60, len(mlabel)*8)}' height='20' rx='6' "
                         f"fill='white' stroke='{relcol}' stroke-width='1'/>")
            parts.append(f"<text x='{left+box_w/2+14}' y='{y0+gap/2+3}' "
                         f"fill='{relcol}' font-size='11' font-weight='bold'>"
                         f"{_esc(mlabel)}</text>")
    parts.append("</svg>")
    return "".join(parts)


# ============================================================
# 범례
# ============================================================
def role_legend_html() -> str:
    items = []
    for key, (kr, fill, stroke) in ROLE_STYLE.items():
        items.append(
            f"<span style='display:inline-block;margin:2px 8px;'>"
            f"<span style='display:inline-block;width:14px;height:14px;"
            f"background:{fill};border:1.5px solid {stroke};border-radius:3px;"
            f"vertical-align:middle;'></span> {kr}</span>")
    return "<div style='font-size:13px;'>" + "".join(items) + "</div>"
