"""
analyzer.py — 지문 분석 엔진
- 문장 단위: spaCy 의존구조 파싱 (API 키 불필요)
- 담화(글 흐름) 단위: 담화표지 규칙 기반 분석 (기본) + 선택적 LLM 심화 분석
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

import spacy

# ---- spaCy 모델 로드 (지연 로딩, 캐시) ----
_NLP = None


def get_nlp():
    global _NLP
    if _NLP is None:
        try:
            _NLP = spacy.load("en_core_web_sm")
        except OSError:
            from spacy.cli import download
            download("en_core_web_sm")
            _NLP = spacy.load("en_core_web_sm")
    return _NLP


# ============================================================
# 담화표지 사전 — 접속표현 → 담화 관계 유형
# ============================================================
DISCOURSE_MARKERS = {
    # 인과 (Cause / Reason)
    "because": "cause", "since": "cause", "as": "cause", "therefore": "result",
    "thus": "result", "hence": "result", "consequently": "result",
    "so": "result", "as a result": "result", "for this reason": "result",
    # 첨가 (Addition)
    "moreover": "addition", "furthermore": "addition", "in addition": "addition",
    "additionally": "addition", "also": "addition", "besides": "addition",
    "what is more": "addition",
    # 대조·양보 (Contrast / Concession)
    "however": "contrast", "but": "contrast", "yet": "contrast",
    "nevertheless": "concession", "nonetheless": "concession",
    "on the other hand": "contrast", "in contrast": "contrast",
    "although": "concession", "though": "concession", "even though": "concession",
    "whereas": "contrast", "while": "contrast", "still": "concession",
    # 예시 (Example)
    "for example": "example", "for instance": "example", "such as": "example",
    "to illustrate": "example", "namely": "example", "in particular": "example",
    # 순서·나열 (Sequence)
    "first": "sequence", "firstly": "sequence", "second": "sequence",
    "secondly": "sequence", "next": "sequence", "then": "sequence",
    "finally": "sequence", "lastly": "sequence",
    # 요약·결론 (Conclusion)
    "in conclusion": "conclusion", "in summary": "conclusion",
    "to sum up": "conclusion", "overall": "conclusion", "in short": "conclusion",
    # 조건 (Condition)
    "if": "condition", "unless": "condition", "provided that": "condition",
}

# 관계 유형 → (한글명, 색상)
# K-Jumak 웜톤: 인과·근거=청양 그린(양념), 대조=다대기 오렌지(고온),
# 결론=수저 골드(프리미엄), 조건·예시=뚝배기 브라운 계열.
RELATION_STYLE = {
    "cause":      ("인과(근거)",   "#6D8C7C"),
    "result":     ("결과",        "#6D8C7C"),
    "addition":   ("첨가",        "#8AA596"),
    "contrast":   ("대조",        "#FF5722"),
    "concession": ("양보",        "#E5643C"),
    "example":    ("예시",        "#A9743E"),
    "sequence":   ("순서·나열",   "#D4AF37"),
    "conclusion": ("결론·요약",   "#C79A2E"),
    "condition":  ("조건",        "#C0562A"),
    "continue":   ("연속",        "#8A6E5D"),
}

# 각 관계 유형이 나타내는 문장의 담화 역할(색상 분류용)
ROLE_BY_RELATION = {
    "cause": "evidence", "result": "claim", "addition": "evidence",
    "contrast": "counter", "concession": "counter", "example": "evidence",
    "sequence": "evidence", "conclusion": "claim", "condition": "evidence",
    "continue": "neutral",
}
# 역할 카드: (한글, 형광펜 배경 틴트, 테두리·라벨색) — K-Jumak 웜톤
ROLE_STYLE = {
    "claim":    ("주장·결론", "#F7ECC9", "#C79A2E"),   # 수저 골드
    "evidence": ("근거·부연", "#E4ECE6", "#6D8C7C"),   # 청양 그린(양념)
    "counter":  ("대조·반론", "#FBE2D8", "#FF5722"),   # 다대기 오렌지(고온)
    "neutral":  ("서술",      "#F1EADF", "#8A6E5D"),   # 육수/브라운 그레이
}


# ============================================================
# 데이터 구조
# ============================================================
@dataclass
class Token:
    i: int
    text: str
    pos: str
    dep: str
    head: int  # index of head token within the sentence


@dataclass
class SentenceAnalysis:
    idx: int
    text: str
    tokens: list = field(default_factory=list)     # list[Token]
    root: int = 0                                   # sentence-local root index

    def to_dict(self):
        d = asdict(self)
        return d


@dataclass
class DiscourseLink:
    src: int          # source sentence idx
    dst: int          # target sentence idx (dst follows src)
    relation: str     # relation key
    marker: str       # the discourse marker text (or "")


@dataclass
class DocAnalysis:
    sentences: list = field(default_factory=list)   # list[SentenceAnalysis]
    links: list = field(default_factory=list)       # list[DiscourseLink]
    roles: dict = field(default_factory=dict)       # sent idx -> role key
    llm_used: bool = False
    llm_summary: Optional[dict] = None              # optional Toulmin / thesis map


# ============================================================
# 문장 단위 분석 (spaCy 의존구조)
# ============================================================
def analyze_sentences(text: str) -> list:
    nlp = get_nlp()
    doc = nlp(text.strip())
    results = []
    for si, sent in enumerate(doc.sents):
        base = sent.start
        toks = []
        root_local = 0
        for t in sent:
            local_i = t.i - base
            head_local = t.head.i - base
            if t.dep_ == "ROOT" or t.head == t:
                root_local = local_i
                head_local = local_i
            toks.append(Token(i=local_i, text=t.text, pos=t.pos_,
                              dep=t.dep_, head=head_local))
        results.append(SentenceAnalysis(idx=si, text=sent.text.strip(),
                                        tokens=toks, root=root_local))
    return results


# ============================================================
# 담화(글 흐름) 분석 — 규칙 기반
# ============================================================
def _detect_marker(sent_text: str):
    """문장 첫머리(및 내부)의 담화표지를 탐지."""
    low = sent_text.lower().strip()
    # 다어절 표지 우선 매칭
    multi = sorted([m for m in DISCOURSE_MARKERS if " " in m],
                   key=len, reverse=True)
    for m in multi:
        if low.startswith(m) or (", " + m + " ") in (", " + low):
            return m, DISCOURSE_MARKERS[m]
    # 단어 표지: 문장 첫 단어 우선
    first = re.split(r"[\s,]+", low)[0] if low else ""
    if first in DISCOURSE_MARKERS:
        return first, DISCOURSE_MARKERS[first]
    # 내부 등장 (but, so, because 등)
    for m in ["because", "but", "so", "although", "though", "if", "unless",
              "while", "whereas", "yet"]:
        if re.search(r"\b" + re.escape(m) + r"\b", low):
            return m, DISCOURSE_MARKERS[m]
    return "", "continue"


def analyze_discourse_rulebased(sentences: list) -> tuple:
    links, roles = [], {}
    for i, s in enumerate(sentences):
        marker, rel = _detect_marker(s.text)
        if i == 0:
            roles[i] = "claim"       # 첫 문장은 주제/주장으로 가정
            continue
        links.append(DiscourseLink(src=i - 1, dst=i, relation=rel, marker=marker))
        roles[i] = ROLE_BY_RELATION.get(rel, "neutral")
    # 마지막 문장이 결론 표지를 가지면 claim으로
    if sentences:
        last_marker, last_rel = _detect_marker(sentences[-1].text)
        if last_rel == "conclusion":
            roles[len(sentences) - 1] = "claim"
    return links, roles


# ============================================================
# 선택적 LLM 심화 분석 (Claude API)
# ============================================================
LLM_PROMPT = """You are a discourse-analysis engine for an English reading/writing tutor.
Analyze the passage below. Return ONLY valid JSON (no markdown fences) with this schema:
{
  "roles": {"0": "claim|evidence|counter|neutral", "1": "...", ...},   // per 0-based sentence index
  "links": [{"src": 0, "dst": 1, "relation": "cause|result|addition|contrast|concession|example|sequence|conclusion|condition|continue", "marker": "however"}],
  "toulmin": {"claim": "...", "grounds": ["..."], "warrant": "...", "rebuttal": "..."},
  "thesis": "one-sentence main point of the whole passage"
}
Sentences (0-indexed):
{SENTS}
"""


def analyze_discourse_llm(sentences: list, api_key: str, model: str = "claude-3-5-haiku-latest"):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    numbered = "\n".join(f"{i}: {s.text}" for i, s in enumerate(sentences))
    prompt = LLM_PROMPT.replace("{SENTS}", numbered)
    msg = client.messages.create(
        model=model, max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    import json
    data = json.loads(raw)
    links = [DiscourseLink(src=int(l["src"]), dst=int(l["dst"]),
                           relation=l.get("relation", "continue"),
                           marker=l.get("marker", "")) for l in data.get("links", [])]
    roles = {int(k): v for k, v in data.get("roles", {}).items()}
    summary = {"toulmin": data.get("toulmin"), "thesis": data.get("thesis")}
    return links, roles, summary


# ============================================================
# 통합 진입점
# ============================================================
def analyze(text: str, api_key: Optional[str] = None,
            model: str = "claude-3-5-haiku-latest") -> DocAnalysis:
    sentences = analyze_sentences(text)
    llm_used = False
    summary = None
    if api_key:
        try:
            links, roles, summary = analyze_discourse_llm(sentences, api_key, model)
            llm_used = True
        except Exception:
            links, roles = analyze_discourse_rulebased(sentences)
    else:
        links, roles = analyze_discourse_rulebased(sentences)
    return DocAnalysis(sentences=sentences, links=links, roles=roles,
                       llm_used=llm_used, llm_summary=summary)
