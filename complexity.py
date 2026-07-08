"""문장 복잡도 채점 — 가장 복잡한 문장 k개 추출.

복잡도 = 구문적으로 학습 가치가 큰 문장(절 중첩·종속·수식 밀도)을 우선한다.
결정론적 가중합이라 같은 입력이면 항상 같은 순위가 나온다.
"""
from dataclasses import dataclass

import reedkellogg as _rk

# 의존 라벨 집합
_SUBORD = {"mark", "advcl", "relcl", "acl", "ccomp", "xcomp",
           "csubj", "csubjpass", "acl:relcl"}
_COORD = {"cc", "conj"}
_PREP = {"prep", "agent", "pcomp"}
_MOD = {"amod", "advmod", "nummod", "poss", "compound", "det",
        "nmod", "appos", "npadvmod"}

# 가중치 (해석 가능한 튜닝값)
_W = {
    "clauses": 2.4,      # RK 절(baseline) 수 — 중첩/종속/등위의 핵심 신호
    "subord": 1.6,       # 종속·관계·보문절
    "depth": 1.1,        # 의존트리 깊이
    "coord": 0.9,        # 등위접속
    "prep": 0.6,         # 전치사구
    "mod": 0.28,         # 수식어 밀도
    "tokens": 0.14,      # 길이(경미)
}


@dataclass
class ComplexityScore:
    idx: int
    text: str
    score: float
    n_clauses: int
    n_subord: int
    depth: int
    n_coord: int
    n_prep: int
    n_mod: int
    n_tokens: int

    def features_kr(self):
        """상위 기여 특징을 한국어 라벨로 (카드 부제용)."""
        parts = []
        if self.n_clauses > 1:
            parts.append(f"{self.n_clauses}개 절")
        if self.n_subord:
            parts.append(f"종속·관계절 {self.n_subord}")
        if self.n_coord:
            parts.append(f"등위 {self.n_coord}")
        if self.n_prep:
            parts.append(f"전치사구 {self.n_prep}")
        parts.append(f"깊이 {self.depth}")
        return " · ".join(parts)


def _tree_depth(sent):
    """의존트리 최대 깊이 (root→leaf 최장 경로)."""
    # head 로컬 인덱스 배열
    heads = {t.i: t.head for t in sent.tokens}
    root = sent.root
    best = 0
    for t in sent.tokens:
        d, cur, guard = 0, t.i, 0
        while cur != root and guard < 200:
            cur = heads.get(cur, root)
            d += 1
            guard += 1
        best = max(best, d)
    return best


def score_sentence(sent):
    """SentenceAnalysis 하나의 복잡도 점수."""
    toks = [t for t in sent.tokens if t.pos != "PUNCT"]
    n_tokens = len(toks)
    n_subord = sum(1 for t in sent.tokens if t.dep in _SUBORD)
    n_coord = sum(1 for t in sent.tokens if t.dep in _COORD)
    n_prep = sum(1 for t in sent.tokens if t.dep in _PREP)
    n_mod = sum(1 for t in sent.tokens if t.dep in _MOD)
    depth = _tree_depth(sent)
    # RK 절 수 (별도 baseline 수) — 파서 재사용
    try:
        n_clauses = max(1, _rk.n_rows(sent.text))
    except Exception:
        n_clauses = 1 + n_subord + n_coord
    score = (_W["clauses"] * n_clauses + _W["subord"] * n_subord
             + _W["depth"] * depth + _W["coord"] * n_coord
             + _W["prep"] * n_prep + _W["mod"] * n_mod
             + _W["tokens"] * n_tokens)
    return ComplexityScore(idx=sent.idx, text=sent.text, score=round(score, 2),
                           n_clauses=n_clauses, n_subord=n_subord, depth=depth,
                           n_coord=n_coord, n_prep=n_prep, n_mod=n_mod,
                           n_tokens=n_tokens)


def rank_sentences(analysis):
    """전체 문장을 복잡도 내림차순으로 정렬해 반환."""
    scored = [score_sentence(s) for s in analysis.sentences]
    scored.sort(key=lambda c: (-c.score, c.idx))
    return scored


def top_complex(analysis, k=3):
    """가장 복잡한 k개 문장을 복잡도순으로. 원문 순서 정보는 idx로 유지."""
    return rank_sentences(analysis)[:k]
