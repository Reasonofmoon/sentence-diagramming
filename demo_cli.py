"""
demo_cli.py — Streamlit 없이 분석 엔진 + SVG 렌더러를 검증하는 CLI.
사용: python demo_cli.py            (데모 지문)
      python demo_cli.py "your text here"
결과: out_flow.svg (글 흐름), out_sent_1.svg ... (문장별)
"""
import sys
import analyzer
import diagram

DEMO = ("Online learning has become increasingly popular. "
        "Students can study at their own pace, and they save commuting time. "
        "For example, a working adult can attend lectures late at night. "
        "However, online learning requires strong self-discipline. "
        "Therefore, successful online learners need good time-management skills.")


def main():
    text = sys.argv[1] if len(sys.argv) > 1 else DEMO
    result = analyzer.analyze(text)  # no API key -> rule-based
    print(f"sentences: {len(result.sentences)} | llm_used: {result.llm_used}")
    print("roles:", result.roles)
    for l in result.links:
        print(f"  S{l.src+1}->S{l.dst+1}: {l.relation} (marker='{l.marker}')")

    with open("out_flow.svg", "w") as f:
        f.write(diagram.render_flow_svg(result))
    for s in result.sentences:
        with open(f"out_sent_{s.idx+1}.svg", "w") as f:
            f.write(diagram.render_sentence_svg(s))
    print("wrote out_flow.svg and", len(result.sentences), "sentence svgs")


if __name__ == "__main__":
    main()
