"""스마트 레이아웃 엔진 — 콘텐츠를 '블록 객체'로 만들고 페이지가 잘리지 않게 배치.

핵심: 각 다이어그램은 측정된 높이를 가진 Block. 페이지네이터는 CSS의
`break-inside: avoid`처럼 블록이 페이지 경계를 넘지 않도록 페이지를 나눈다.
한 블록이 페이지보다 크면(초장문) 그 블록만 축소해 담는다(그래도 안 잘림).

Smart editor 훅:
- include        : 포함할 문장 idx 집합 (편집: 특정 문장만)
- page_break_before : 이 블록 앞에서 강제 페이지 나눔
- keep_with_next : 다음 블록과 붙여서 같은 페이지에 (헤더+흐름 등)
- one_per_page   : 문장마다 단독 페이지
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

A4_W, A4_H = 8.27, 11.69
MARGIN = 0.5
INK = "#1a1a1a"


@dataclass
class Block:
    """페이지에 배치되는 최소 단위(객체). draw(fig, rect)로 자기 자신을 그린다."""
    kind: str                       # 'header'|'flow'|'legend'|'sentence'|...
    height_in: float                # 필요한 최소 높이(인치)
    draw: Callable                  # draw(fig, (x0,y0,w,h)) figure-fraction 좌표
    key: str = ""                   # 편집 식별자 (예: 'sent-3')
    keep_with_next: bool = False    # 다음 블록과 같은 페이지 강제
    page_break_before: bool = False # 이 블록 앞에서 페이지 나눔
    min_height_in: float = 0.6      # 축소 허용 하한


def _usable_height():
    return A4_H - 2 * MARGIN


def paginate(blocks, gap_in=0.18):
    """블록들을 페이지로 나눈다. 블록은 절대 페이지 경계를 넘지 않는다.
    반환: list[page]; page = list[(block, h_in)] (실제 배치 높이).
    """
    content_h = _usable_height()
    pages, cur, used = [], [], 0.0
    i = 0
    n = len(blocks)
    while i < n:
        b = blocks[i]
        # 강제 페이지 나눔
        if b.page_break_before and cur:
            pages.append(cur); cur, used = [], 0.0

        # keep_with_next 그룹을 하나로 묶어 함께 판단
        group = [b]
        j = i
        while blocks[j].keep_with_next and j + 1 < n:
            j += 1
            group.append(blocks[j])
        group_h = sum(g.height_in for g in group) + gap_in * (len(group) - 1)

        # 그룹이 페이지보다 크면: 축소 불가피 → 그룹 내 블록을 비례 축소해 한 페이지에
        if group_h > content_h:
            if cur:
                pages.append(cur); cur, used = [], 0.0
            scale = content_h / group_h
            placed = [(g, max(g.min_height_in, g.height_in * scale)) for g in group]
            pages.append(placed)
            i = j + 1
            continue

        # 현재 페이지에 그룹이 안 들어가면 새 페이지
        need = group_h + (gap_in if cur else 0.0)
        if used + need > content_h and cur:
            pages.append(cur); cur, used = [], 0.0
            need = group_h
        for g in group:
            cur.append((g, g.height_in))
            used += g.height_in + gap_in
        i = j + 1
    if cur:
        pages.append(cur)
    return pages


def render_pages(blocks, path, justify=True, gap_in=0.18, dpi=130,
                 as_pdf=True):
    """페이지네이션 후 각 페이지를 그린다. justify=True면 남는 공간을
    블록 사이에 고르게 분배(빽빽하지만 안 잘림). 반환: 저장 경로 리스트/단일 PDF.
    """
    pages = paginate(blocks, gap_in=gap_in)
    x0 = MARGIN / A4_W
    w = 1 - 2 * MARGIN / A4_W
    content_h_in = _usable_height()

    figs = []
    for page in pages:
        fig = plt.figure(figsize=(A4_W, A4_H))
        total_block_h = sum(h for _, h in page)
        n_gap = max(1, len(page) - 1)
        if justify and len(page) > 1:
            extra = content_h_in - total_block_h
            gap = gap_in + max(0.0, extra) / n_gap
            # 너무 벌어지지 않게 상한
            gap = min(gap, gap_in + 1.2)
        else:
            gap = gap_in
        # 위에서 아래로 배치
        y_top_in = A4_H - MARGIN
        y = y_top_in
        for b, h in page:
            y -= h
            rect = (x0, y / A4_H, w, h / A4_H)
            b.draw(fig, rect)
            y -= gap
        figs.append(fig)

    if as_pdf:
        with PdfPages(path) as pdf:
            for f in figs:
                pdf.savefig(f); plt.close(f)
        return [path], len(pages)
    else:
        out = []
        for k, f in enumerate(figs):
            p = path.replace(".png", f"_p{k+1}.png")
            f.savefig(p, dpi=dpi, facecolor="white"); plt.close(f)
            out.append(p)
        return out, len(pages)
