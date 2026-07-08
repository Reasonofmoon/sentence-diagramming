"""
app.py — 지문 → 문장 다이어그램 + 글 흐름 다이어그램 생성 앱 (Streamlit)

실행:
    streamlit run app.py

문장 다이어그램은 spaCy 의존구조 파싱으로 항상 동작(API 키 불필요).
사이드바에 Claude API 키를 넣으면 글 흐름을 LLM으로 심화 분석(담화관계 + Toulmin).
"""
import io
import streamlit as st
import analyzer
import diagram
import a4report

st.set_page_config(page_title="지문 구조 다이어그래머", layout="wide")


def _svg_wrap(svg: str) -> str:
    return f"<div style='overflow:auto;background:white;'>{svg}</div>"


def _svg_height(result) -> int:
    n = len(result.sentences)
    return min(40 + n * 106 + 40, 1200)


def _sent_height(s) -> int:
    span = max([abs(t.head - t.i) for t in s.tokens], default=1)
    return int(min(90 + 26 * span + 60, 380))


DEMO = ("Online learning has become increasingly popular. "
        "Students can study at their own pace, and they save commuting time. "
        "For example, a working adult can attend lectures late at night. "
        "However, online learning requires strong self-discipline. "
        "Therefore, successful online learners need good time-management skills.")

# ---------------- 사이드바 ----------------
st.sidebar.title("⚙️ 설정")
api_key = st.sidebar.text_input("Claude API 키 (선택)", type="password",
    help="입력하면 글 흐름을 LLM으로 심화 분석합니다. 비워두면 담화표지 규칙 기반으로 분석합니다.")
model = st.sidebar.selectbox("LLM 모델", ["claude-3-5-haiku-latest",
                                          "claude-3-5-sonnet-latest"], index=0)
st.sidebar.markdown("---")
st.sidebar.subheader("📄 A4 리포트 옵션")
sent_label = st.sidebar.radio(
    "문장 다이어그램", ["Reed–Kellogg 도해 (한국 영문법)", "의존구조 (학술)"])
sentence_style = "dep" if sent_label.startswith("의존") else "rk"
tpl_label = st.sidebar.radio("템플릿", ["교사용 (정답 강조)", "학생용 (빈칸 워크시트)"])
template = "student" if tpl_label.startswith("학생") else "teacher"
flow_label = st.sidebar.radio("글 흐름 표기", ["담화표지 흐름 (선형)", "RST 담화 나무"])
flow_style = "rst" if flow_label.startswith("RST") else "linear"
layout_label = st.sidebar.radio(
    "레이아웃",
    ["전체 (다중 페이지)", "압축 (1페이지 요약)", "벤또 (복잡한 3문장 집중)",
     "스마트 (페이지 안 잘림 · 편집)"])
if layout_label.startswith("압축"):
    layout = "compact"
elif layout_label.startswith("벤또"):
    layout = "bento"
elif layout_label.startswith("스마트"):
    layout = "smart"
else:
    layout = "full"
st.sidebar.markdown("---")
st.sidebar.markdown("**문장 다이어그램**: spaCy 의존구조 (키 불필요)\n\n"
                    "**글 흐름**: 담화표지 규칙 (기본) / LLM (키 입력 시)")

# ---------------- 메인 ----------------
st.title("📊 지문 구조 다이어그래머")
st.caption("영어 지문을 입력하면 ① 각 문장의 의존구조 다이어그램과 "
           "② 글 전체의 논리 흐름 다이어그램이 유기적으로 생성됩니다.")

text = st.text_area("영어 지문 입력", value=DEMO, height=160)
go = st.button("🔍 분석하기", type="primary")

if go and text.strip():
    with st.spinner("분석 중..."):
        result = analyzer.analyze(text, api_key=api_key or None, model=model)

    mode = "LLM 심화 분석" if result.llm_used else "담화표지 규칙 기반"
    st.success(f"분석 완료 · 문장 {len(result.sentences)}개 · 글 흐름: {mode}")

    # ---- Smart editor (스마트 레이아웃 전용 편집 훅) ----
    smart_include = None
    smart_one_per_page = False
    if layout == "smart":
        with st.expander("✏️ Smart Editor — 포함할 문장·페이지 나눔 편집", expanded=True):
            opts = [f"S{s.idx+1}: {s.text[:40]}" for s in result.sentences]
            picked = st.multiselect(
                "리포트에 포함할 문장 (미선택 시 전체)", opts, default=opts)
            smart_include = [int(o.split(":")[0][1:]) - 1 for o in picked] \
                if picked else None
            smart_one_per_page = st.checkbox(
                "문장마다 페이지 나눔 (one-per-page)", value=False)
            st.caption("각 다이어그램은 블록 객체로 처리되어 페이지 경계에서 "
                       "잘리지 않습니다. 블록이 한 페이지보다 크면 그 블록만 "
                       "축소되어 담깁니다.")

    # ---- A4 인쇄용 PDF 다운로드 ----
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        pdf_path = os.path.join(td, "report.pdf")
        if layout == "smart":
            _, npg = a4report.build_smart_pdf(
                result, pdf_path, title="지문 구조 분석 리포트",
                template=template, flow_style=flow_style,
                sentence_style=sentence_style,
                include=smart_include, one_per_page=smart_one_per_page)
            st.caption(f"스마트 레이아웃 · 총 {npg}페이지 (다이어그램 안 잘림)")
        else:
            a4report.build_a4_pdf(result, pdf_path, title="지문 구조 분석 리포트",
                                  template=template, flow_style=flow_style,
                                  layout=layout, sentence_style=sentence_style)
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
    fname = f"passage_report_{template}_{flow_style}_{layout}.pdf"
    st.download_button(f"📄 A4 인쇄용 PDF 내려받기 ({tpl_label.split()[0]}·"
                       f"{'RST' if flow_style=='rst' else '선형'}·"
                       f"{layout})",
                       data=pdf_bytes, file_name=fname,
                       mime="application/pdf", type="primary")

    tab1, tab2, tab3 = st.tabs(["🌐 글 흐름 다이어그램", "🔤 문장 다이어그램", "📋 요약"])

    # ---- 글 흐름 ----
    with tab1:
        st.markdown("#### 글의 논리 흐름")
        st.markdown(diagram.role_legend_html(), unsafe_allow_html=True)
        st.write("")
        svg = diagram.render_flow_svg(result)
        st.components.v1.html(_svg_wrap(svg), height=_svg_height(result), scrolling=True)

    # ---- 문장별 ----
    with tab2:
        st.markdown("#### 문장별 의존구조 (핵어 → 의존어)")
        for s in result.sentences:
            role = result.roles.get(s.idx, "neutral")
            kr = diagram.ROLE_STYLE.get(role, ("",))[0]
            st.markdown(f"**S{s.idx+1}** ({kr}) — {s.text}")
            svg = diagram.render_sentence_svg(s)
            st.components.v1.html(_svg_wrap(svg), height=_sent_height(s), scrolling=True)
            st.write("")

    # ---- 요약 ----
    with tab3:
        if result.llm_used and result.llm_summary:
            summ = result.llm_summary
            if summ.get("thesis"):
                st.markdown(f"**논지(thesis)**: {summ['thesis']}")
            t = summ.get("toulmin") or {}
            if t:
                st.markdown("##### Toulmin 논증 구조")
                st.markdown(f"- **주장(Claim)**: {t.get('claim','—')}")
                gr = t.get("grounds") or []
                st.markdown("- **근거(Grounds)**: " +
                            ("; ".join(gr) if gr else "—"))
                st.markdown(f"- **전제(Warrant)**: {t.get('warrant','—')}")
                st.markdown(f"- **반론(Rebuttal)**: {t.get('rebuttal','—')}")
        else:
            st.info("LLM 심화 분석을 켜면(사이드바에 API 키 입력) 논지와 "
                    "Toulmin 논증 구조 요약이 표시됩니다.")
        st.markdown("##### 담화 관계 목록")
        for l in result.links:
            relkr = diagram.RELATION_STYLE.get(l.relation, ("연속",))[0]
            mk = f" (표지: {l.marker})" if l.marker else ""
            st.markdown(f"- S{l.src+1} → S{l.dst+1}: **{relkr}**{mk}")
