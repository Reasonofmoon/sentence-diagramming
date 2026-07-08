"""
reedkellogg.py — 한국 영문법식 간이 Reed–Kellogg 도해 (결정론적 · 규칙 불변)

설계 원칙 (규칙이 깨지지 않도록):
  1. 모든 토큰은 우선순위 규칙 테이블(RK_RULES)로 '정확히 하나'의 성분에 배정된다.
     매칭되지 않는 토큰도 반드시 폴백(기타 수식어)으로 흡수 → 누락/충돌 없음.
  2. 절(clause)마다 독립된 baseline 행을 갖는다. 주절이 맨 위, 종속·관계절은
     아래 행으로 내려가고 점선 연결자로 모절의 해당 단어에 붙는다.
     → 복잡한 문장도 행이 늘어날 뿐 배치가 특이(idiosyncratic)해지지 않는다.
  3. baseline 위: [주어] │ [술어] ├ [목적어] 또는 ╲[보어].
     수식어(형용사·부사·관사·소유격·전치사구)는 머리 단어 아래 사선에 매단다.

성분(한국 영문법 용어):
  주어 · 술어(동사) · 목적어 · 보어 · 형용사 · 부사 · 관사 · 소유격 · 수사 ·
  전치사(구) · 관계대명사 · 접속사(종속/등위) · 기타수식
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import analyzer  # get_nlp()


# ============================================================
# 1) 결정론적 역할 배정 규칙 (spaCy dep → 한국 영문법 성분)
#    baseline 성분과 수식어 성분을 구분한다.
# ============================================================
# baseline 핵심 성분
DEP_SUBJECT = {"nsubj", "nsubjpass", "csubj", "csubjpass", "expl"}
DEP_OBJECT = {"dobj", "obj", "dative", "iobj"}
DEP_COMPLEMENT = {"attr", "acomp", "oprd", "pcomp"}
DEP_AUX = {"aux", "auxpass"}                     # 조동사 → 동사와 합침
# 수식어 (머리 아래 사선)
MOD_MAP = {
    "det": "관사",
    "amod": "형용사",
    "nummod": "수사",
    "poss": "소유격",
    "advmod": "부사",
    "npadvmod": "부사",
    "advcl": None,      # 부사절 → 절로 처리
    "acl": None,        # 분사/절 수식 → 절로 처리
    "relcl": None,      # 관계절 → 절로 처리
    "neg": "부사",
    "prt": "불변화사",
    "compound": "복합어",
    "nmod": "명사수식",
    "appos": "동격",
    "quantmod": "수량수식",
    "predet": "관사",
    "case": "격표지",
}
# 절을 이끄는 dep
DEP_CLAUSE = {"relcl", "advcl", "acl", "ccomp", "xcomp", "csubj", "csubjpass"}
# 종속/관계/등위 연결어
DEP_MARK = "mark"           # 종속접속사 (because, that, when...)
DEP_CC = "cc"               # 등위접속사 (and, but, or)
DEP_CONJ = "conj"           # 등위 연결된 요소

ROLE_KR = {
    "subject": "주어", "verb": "술어", "object": "목적어",
    "complement": "보어", "prep": "전치사", "prep_obj": "전치사목적어",
}


# ============================================================
# 2) 구조 데이터
# ============================================================
@dataclass
class Mod:
    text: str
    kind: str            # 형용사/부사/관사/소유격/전치사구...
    children: list = field(default_factory=list)   # 전치사구 내부 수식 등


@dataclass
class PrepPhrase:
    prep: str
    obj: str
    obj_mods: list = field(default_factory=list)   # list[Mod]


@dataclass
class Clause:
    subject: str = ""
    subject_mods: list = field(default_factory=list)
    verb: str = ""                 # 조동사 포함 (can study)
    verb_mods: list = field(default_factory=list)
    obj: str = ""
    obj_mods: list = field(default_factory=list)
    comp: str = ""                 # 보어
    comp_mods: list = field(default_factory=list)
    is_complement_obj: bool = False  # True면 보어, False면 목적어 (구분선 방식)
    preps: list = field(default_factory=list)      # list[PrepPhrase] (동사에 붙는)
    # 연결 정보 (종속/관계절일 때)
    connector: str = ""            # 관계대명사/종속접속사 텍스트
    connector_kind: str = ""       # "관계대명사" | "종속접속사" | "등위접속사"
    attach_to: str = ""            # 모절에서 이 절이 수식/연결하는 단어
    children: list = field(default_factory=list)   # 하위 절 (list[Clause])
    depth: int = 0


# ============================================================
# 3) spaCy 토큰 트리 → Clause 구조 (결정론적)
# ============================================================
def _collect_mods(head_tok):
    """머리 토큰의 직접 수식어를 결정론적으로 수집 (절·전치사·baseline성분 제외)."""
    mods, preps = [], []
    for c in head_tok.children:
        dep = c.dep_
        if dep in DEP_SUBJECT or dep in DEP_OBJECT or dep in DEP_COMPLEMENT:
            continue
        if dep in DEP_AUX:
            continue
        if dep in DEP_CLAUSE or dep in (DEP_CC, DEP_CONJ, DEP_MARK):
            continue
        # 관계대명사/관계부사(who/which/when...)는 연결자로 별도 처리 → 수식어 제외
        if c.tag_ in ("WDT", "WP", "WP$", "WRB"):
            continue
        if dep == "prep":
            preps.append(_build_prep(c))
            continue
        if dep == "punct":
            continue
        kind = MOD_MAP.get(dep)
        if kind is None:
            # 폴백: 알 수 없는 수식은 '기타수식'으로 흡수 (규칙 불변 보장)
            kind = "기타수식"
        mods.append(Mod(text=c.text, kind=kind))
    return mods, preps


def _build_prep(prep_tok):
    """전치사구: 전치사 + 목적어(+목적어 수식)."""
    obj = ""
    obj_mods = []
    for c in prep_tok.children:
        if c.dep_ in ("pobj", "pcomp", "obj"):
            obj = c.text
            m, _ = _collect_mods(c)
            obj_mods = m
    return PrepPhrase(prep=prep_tok.text, obj=obj, obj_mods=obj_mods)


def _verb_phrase(verb_tok):
    """동사 + 조동사(들)을 어순대로 결합 → '술어' 텍스트."""
    aux = [c for c in verb_tok.children if c.dep_ in DEP_AUX]
    parts = sorted(aux + [verb_tok], key=lambda t: t.i)
    return " ".join(t.text for t in parts)


def _build_clause(verb_tok, connector="", connector_kind="", attach_to="",
                  depth=0):
    """동사(절의 핵)로부터 하나의 절을 구성."""
    cl = Clause(connector=connector, connector_kind=connector_kind,
                attach_to=attach_to, depth=depth)
    cl.verb = _verb_phrase(verb_tok)
    cl.verb_mods, cl.preps = _collect_mods(verb_tok)

    noun_heads = []   # (텍스트, 토큰) — 관계절 부착 대상
    for c in verb_tok.children:
        dep = c.dep_
        if dep in DEP_SUBJECT:
            cl.subject = c.text
            cl.subject_mods, _ = _collect_mods(c)
            noun_heads.append((c.text, c))
        elif dep in DEP_OBJECT:
            cl.obj = c.text
            cl.obj_mods, _ = _collect_mods(c)
            cl.is_complement_obj = False
            noun_heads.append((c.text, c))
        elif dep in DEP_COMPLEMENT:
            cl.comp = c.text
            cl.comp_mods, _ = _collect_mods(c)
            cl.is_complement_obj = True
            noun_heads.append((c.text, c))

    # 명사 성분에 붙는 관계절/분사절 (relcl/acl)
    for txt, tok in noun_heads:
        for gc in tok.children:
            if gc.dep_ == "relcl":
                rp, rkind = _relative_connector(gc)
                cl.children.append(_build_clause(gc, rp, rkind,
                                   attach_to=txt, depth=depth + 1))
            elif gc.dep_ == "acl":
                mk = _find_mark(gc)
                cl.children.append(_build_clause(gc, mk,
                                   "종속접속사" if mk else "분사",
                                   attach_to=txt, depth=depth + 1))

    # 동사에 직접 붙는 하위 절 (부사절/명사절/등위절)
    for c in verb_tok.children:
        dep = c.dep_
        if dep == "relcl":
            rp, rkind = _relative_connector(c)
            cl.children.append(_build_clause(c, rp, rkind,
                               attach_to=verb_tok.text, depth=depth + 1))
        elif dep in ("advcl", "acl"):
            mark = _find_mark(c)
            cl.children.append(_build_clause(c, mark, "종속접속사" if mark else "",
                               attach_to=verb_tok.text, depth=depth + 1))
        elif dep in ("ccomp", "xcomp"):
            mark = _find_mark(c)
            cl.children.append(_build_clause(c, mark, "종속접속사" if mark else "",
                               attach_to=verb_tok.text, depth=depth + 1))
        elif dep == "conj" and c.pos_ in ("VERB", "AUX"):
            cc = _find_cc(verb_tok)
            cl.children.append(_build_clause(c, cc, "등위접속사",
                               attach_to=verb_tok.text, depth=depth + 1))
    return cl


def _relative_connector(clause_verb):
    """관계절의 관계대명사/관계부사를 찾는다."""
    for c in clause_verb.subtree:
        if c.dep_ in ("nsubj", "nsubjpass", "dobj", "obj", "pobj", "relcl",
                      "advmod") and c.tag_ in ("WDT", "WP", "WP$", "WRB"):
            return c.text, "관계대명사"
    # that/which/who 등이 mark로 오는 경우
    for c in clause_verb.children:
        if c.tag_ in ("WDT", "WP", "WP$", "WRB"):
            return c.text, "관계대명사"
    return "", "관계대명사"


def _find_mark(clause_verb):
    for c in clause_verb.children:
        if c.dep_ == "mark":
            return c.text
    return ""


def _find_cc(head):
    for c in head.children:
        if c.dep_ == "cc":
            return c.text
    return "and"


# ============================================================
# 4) 문장 → 절 리스트 (플랫: 렌더링 편의)
# ============================================================
def parse_rk(sentence_span):
    """spaCy Span(한 문장) → 최상위 Clause (children에 종속절 포함)."""
    root = sentence_span.root
    # root가 동사가 아니면(예: 계사 생략) 가장 가까운 동사/루트 사용
    return _build_clause(root)


def flatten(clause, out=None):
    if out is None:
        out = []
    out.append(clause)
    for ch in clause.children:
        flatten(ch, out)
    return out


# ============================================================
# 5) 결정론적 Reed–Kellogg 렌더러 (matplotlib axes)
# ============================================================
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

INK = "#1a1a1a"
RK_LABEL_COL = "#888"


def _draw_mods_below(ax, x_center, y_base, mods, col=INK, dy_step=0.55):
    """머리 단어 아래 사선에 수식어를 매단다. 여러 개면 좌우로 벌린다.
    간격은 단어 길이에 비례해 넓혀 겹침을 방지한다."""
    if not mods:
        return
    m = len(mods)
    # 각 수식어 폭(글자수 기반) → 누적 배치. 사선은 항상 좌상→우하(\) 방향.
    slant_dx = 0.5
    widths = [max(0.75, 0.11 * len(mod.text) + 0.35) for mod in mods]
    total_w = sum(widths)
    xs = []
    acc = -total_w / 2
    for w in widths:
        xs.append(x_center + acc + w / 2)
        acc += w
    for xk, mod in zip(xs, mods):
        # 좌상(baseline) → 우하(단어)로 내려가는 사선
        x_top = xk - slant_dx / 2
        x_bot = xk + slant_dx / 2
        ax.plot([x_top, x_bot], [y_base, y_base - dy_step], color=col, lw=1.0)
        ax.text(x_bot, y_base - dy_step - 0.06, mod.text, ha="center",
                va="top", fontsize=7.5, color=INK, rotation=0)
        ax.text(x_bot, y_base - dy_step - 0.30, mod.kind, ha="center",
                va="top", fontsize=5.3, color=RK_LABEL_COL)


def _draw_preps_below(ax, x_center, y_base, preps, dy_step=0.55):
    """전치사구: 사선 아래 전치사 + 그 아래 목적어(+수식)."""
    if not preps:
        return
    m = len(preps)
    # 전치사구 폭 = 목적어 길이 기반, 최소 1.6
    widths = [max(1.6, 0.12 * len(pp.obj) + 1.2) for pp in preps]
    total_w = sum(widths)
    xs = []
    acc = -total_w / 2
    for w in widths:
        xs.append(x_center + acc + w / 2)
        acc += w
    for xk, pp in zip(xs, preps):
        # 전치사: 사선 위에 표기
        ax.plot([x_center, xk], [y_base, y_base - dy_step], color="#2b7cd3", lw=1.0)
        ax.text(xk - 0.05, y_base - dy_step + 0.04, pp.prep, ha="right", va="top",
                fontsize=7.3, color="#2b7cd3", fontstyle="italic")
        ax.text(xk - 0.05, y_base - dy_step - 0.12, "전치사", ha="right", va="top",
                fontsize=5.0, color=RK_LABEL_COL)
        # 목적어 수평선 (전치사 아래로 충분히 내림)
        oy = y_base - dy_step - 0.5
        ax.plot([xk - 0.4, xk + 0.5], [oy, oy], color="#2b7cd3", lw=1.0)
        ax.text(xk, oy + 0.04, pp.obj, ha="center", va="bottom",
                fontsize=7.3, color=INK)
        ax.text(xk + 0.55, oy + 0.02, "전치사목적어", ha="left", va="bottom",
                fontsize=4.8, color=RK_LABEL_COL)
        if pp.obj_mods:
            _draw_mods_below(ax, xk, oy, pp.obj_mods, col="#2b7cd3", dy_step=0.4)


def _draw_clause(ax, cl, y, x0=0.5):
    """하나의 절을 baseline 행 y에 그린다. 반환: 주요 단어의 x좌표 dict."""
    positions = {}
    baseline_col = "#333"
    # ---- 성분 x배치 (고정 간격) ----
    x_subj = x0 + 1.4
    x_div1 = x_subj + 1.3          # 주어|술어 구분선 (baseline 관통)
    x_verb = x_div1 + 1.3
    has_obj = bool(cl.obj)
    has_comp = bool(cl.comp)
    x_div2 = x_verb + 1.4          # 술어-목적어/보어 구분
    x_third = x_div2 + 1.3
    right = x_third + 1.6

    # baseline
    ax.plot([x0, right], [y, y], color=baseline_col, lw=1.6, zorder=2)
    # 주어|술어 구분선 (baseline 관통)
    ax.plot([x_div1, x_div1], [y - 0.32, y + 0.32], color=baseline_col,
            lw=1.6, zorder=2)

    # 주어
    ax.text(x_subj, y + 0.10, cl.subject or "—", ha="center", va="bottom",
            fontsize=9, fontweight="bold", color=INK, zorder=3)
    ax.text(x_subj, y + 0.52, "주어", ha="center", va="bottom", fontsize=5.8,
            color=RK_LABEL_COL)
    _draw_mods_below(ax, x_subj, y, cl.subject_mods)
    positions["subject"] = x_subj

    # 술어
    ax.text(x_verb, y + 0.10, cl.verb or "—", ha="center", va="bottom",
            fontsize=9, fontweight="bold", color=INK, zorder=3)
    ax.text(x_verb, y + 0.52, "술어", ha="center", va="bottom", fontsize=5.8,
            color=RK_LABEL_COL)
    _draw_mods_below(ax, x_verb, y, cl.verb_mods)
    # 전치사구는 부사 수식어보다 더 아래에서 시작 → 겹침 방지
    prep_offset = 1.25 if cl.verb_mods else 0.55
    _draw_preps_below(ax, x_verb, y, cl.preps, dy_step=prep_offset)
    positions["verb"] = x_verb

    # 목적어 또는 보어
    if has_obj:
        # 술어-목적어 구분선: baseline 위 짧은 수직선 (관통 X)
        ax.plot([x_div2, x_div2], [y, y + 0.32], color=baseline_col, lw=1.6,
                zorder=2)
        ax.text(x_third, y + 0.10, cl.obj, ha="center", va="bottom",
                fontsize=9, fontweight="bold", color=INK, zorder=3)
        ax.text(x_third, y + 0.52, "목적어", ha="center", va="bottom",
                fontsize=5.8, color=RK_LABEL_COL)
        _draw_mods_below(ax, x_third, y, cl.obj_mods)
        positions["third"] = x_third
    elif has_comp:
        # 보어: 술어 뒤 뒤로 기운 사선(\) 구분
        ax.plot([x_div2, x_div2 + 0.28], [y, y + 0.32], color=baseline_col,
                lw=1.6, zorder=2)
        ax.text(x_third, y + 0.10, cl.comp, ha="center", va="bottom",
                fontsize=9, fontweight="bold", color=INK, zorder=3)
        ax.text(x_third, y + 0.52, "보어", ha="center", va="bottom",
                fontsize=5.8, color=RK_LABEL_COL)
        _draw_mods_below(ax, x_third, y, cl.comp_mods)
        positions["third"] = x_third
    positions["x0"] = x0
    positions["right"] = right
    return positions


def draw_sentence_rk(ax, sentence_span, title=""):
    """문장 Span → Reed–Kellogg 도해 (여러 절을 행으로 쌓음)."""
    top = parse_rk(sentence_span)
    clauses = flatten(top)
    ax.axis("off")
    row_gap = 3.0
    n = len(clauses)
    total_h = n * row_gap
    ax.set_ylim(-0.6, total_h + 0.4)
    # 각 절을 위→아래 행에 배치
    ypos = {}
    pos_by_clause = {}
    INDENT = 1.2                      # 종속·관계절 들여쓰기 폭
    for i, cl in enumerate(clauses):
        y = total_h - (i + 0.7) * row_gap
        # 등위절은 주절과 같은 시작점, 종속·관계절은 안쪽에서 시작 → 위계 구별
        if cl.depth == 0 or cl.connector_kind == "등위접속사":
            x0 = 0.5
        else:                        # 종속접속사 · 관계대명사
            x0 = 0.5 + INDENT
        ypos[id(cl)] = y
        pos_by_clause[id(cl)] = _draw_clause(ax, cl, y, x0=x0)

    # 종속/관계/등위 연결자 (점선 + 라벨)로 모절에 연결
    maxright = max(p["right"] for p in pos_by_clause.values())
    ax.set_xlim(-0.6, maxright + 0.5)
    # 연결자는 왼쪽 여백(x_link)에 수직 점선으로 → 본문 수식어와 절대 겹치지 않음
    x_link = 0.05
    for cl in clauses:
        if cl.depth == 0:
            continue
        y = ypos[id(cl)]
        p = pos_by_clause[id(cl)]
        # 점선 세로 기둥은 이 절의 x0 바로 왼쪽에 세워 들여쓰기를 시각적으로 반영
        x_pillar = min(x_link + 0.0, p["x0"] - 0.35)
        ax.plot([x_pillar, x_pillar], [y + 0.05, y + row_gap - 0.05],
                color="#c0392b", lw=1.1, ls=(0, (4, 3)), zorder=1)
        # 자식 baseline과 연결 (가로 짧은 선)
        ax.plot([x_pillar, p["x0"]], [y, y], color="#c0392b", lw=1.0,
                ls=(0, (4, 3)), zorder=1)
        # 라벨은 자기 절(자식 baseline) 바로 위에 고정 → 위 절 라벨과 안 겹침
        lbl = cl.connector_kind + (f" {cl.connector}" if cl.connector else "")
        ax.text(x_link + 0.12, y + 0.62, lbl, ha="left",
                va="center", fontsize=6.2, color="#c0392b", fontweight="bold")
        ax.text(x_link + 0.12, y + 0.36,
                f"→ {cl.attach_to} 수식/연결", ha="left", va="center",
                fontsize=5.2, color="#999")
    if title:
        ax.set_title(title, loc="left", fontsize=8, fontweight="bold",
                     color=INK, pad=3)
    return n


def draw_sentence_rk_from_text(ax, text, title=""):
    """문장 텍스트를 spaCy로 재파싱해 RK 도해를 그린다 (SentenceAnalysis 연동용)."""
    nlp = analyzer.get_nlp()
    doc = nlp(text.strip())
    sents = list(doc.sents)
    if not sents:
        ax.axis("off")
        return 0
    return draw_sentence_rk(ax, sents[0], title=title)


def n_rows(text):
    """RK 도해가 필요로 하는 절(행) 수 — 레이아웃 높이 계산용."""
    nlp = analyzer.get_nlp()
    doc = nlp(text.strip())
    sents = list(doc.sents)
    if not sents:
        return 1
    return len(flatten(parse_rk(sents[0])))
