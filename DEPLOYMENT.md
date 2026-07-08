# 영어 지문 다이어그램 앱 — 기술 스택 & 배포 제안

수능 모의고사·학습용 영어 지문을 입력하면 문장(Reed–Kellogg)·글 흐름(담화표지)
다이어그램이 A4 PDF로 출력되는 앱의 배포 설계.

---

## 0. 현재 구성 (as-is)
| 계층 | 현재 |
|---|---|
| UI | **Streamlit** (사이드바 옵션 + 3탭 + PDF 다운로드) |
| 문장 분석 | **spaCy** `en_core_web_sm` (의존구조 → RK 성분 매핑) |
| 담화 분석 | 담화표지 규칙 (+ 선택적 Claude API) |
| 렌더링 | **matplotlib** (A4 벡터 PDF), SVG (화면 탭) |
| 폰트 | Apple SD Gothic Neo (**macOS 전용 경로 — 배포 시 깨짐**) |

핵심 특성: ① 상태 유지형 웹소켓 앱(Streamlit) → **프로세스 상주형 호스팅** 필요
(요청당 서버리스 부적합), ② spaCy 로드 시 상시 RAM ~300–400MB, ③ CPU만으로 충분
(GPU 불필요), ④ 사용자 입력 텍스트 외 상태 없음(무DB로 시작 가능).

---

## 1. 배포 전 필수 수정 (blocker)

### (a) 한글 폰트를 저장소에 번들 — 최우선
현재 `_setup_font()`는 macOS 시스템 경로를 찾습니다. 리눅스 서버엔 없으므로
**폰트 파일을 repo에 포함**하고 파일 경로로 등록해야 합니다.
```
diagram_app/fonts/NanumGothic.ttf        # repo에 커밋 (OFL 라이선스, 재배포 가능)
```
`a4report._setup_font()` / `reedkellogg`의 폰트 후보 리스트 맨 앞에
`os.path.join(os.path.dirname(__file__), "fonts", "NanumGothic.ttf")` 추가.
→ macOS·리눅스·도커 어디서나 동일하게 렌더링.

### (b) spaCy 모델 설치를 빌드에 고정
`requirements.txt`에 모델을 **직접 URL**로 pin (런타임 `spacy download` 회피):
```
spacy==3.8.*
https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
```

### (c) 모델 1회 로드 캐시
```python
@st.cache_resource
def get_nlp(): return spacy.load("en_core_web_sm")
```
매 요청 재로드 방지 (응답속도·메모리 안정).

### (d) API 키는 `st.secrets`로
프로덕션에선 사이드바 평문 입력 대신 `st.secrets["ANTHROPIC_API_KEY"]`
(키 없으면 규칙 기반으로 자동 폴백 — 현재 로직 유지).

---

## 2. 대상 규모별 권장 스택 (핵심 결정)

### 시나리오 A — 개인/소수 학급 (~수십 명, 무료 우선) ★추천 시작점
**Streamlit 그대로 + Streamlit Community Cloud** 또는 **Hugging Face Spaces**
- 코드 변경 최소(위 1번 수정만), GitHub 연결 후 자동 배포
- 무료, HTTPS·도메인 자동 제공
- spaCy sm 모델이 무료 티어 RAM(1GB) 안에 들어감
- 한계: 공개 URL(비공개 원하면 HF Spaces private), 동시접속·리소스 제한

### 시나리오 B — 학원/학교 (수백 명, 계정·이력 저장·커스텀 도메인)
**FastAPI(백엔드) + React/Next.js(프론트) + Postgres**
- 백엔드: spaCy 분석 + PDF 생성을 REST API로 (`POST /analyze` → JSON, `POST /report.pdf`)
- 프론트: 지문 입력 UI, 옵션 토글, 결과 뷰어(모바일 대응)
- 인증(학생/교사), 지문·리포트 이력 DB 저장
- 배포: 백엔드 컨테이너(Fly.io/Railway/Render) + 프론트(Vercel)
- Streamlit → React 전환 이유: 다중 사용자·모바일·브랜딩·속도

### 시나리오 C — 공개 SaaS (수익화)
B + 결제(Stripe/토스), LLM 호출 큐·레이트리밋, CDN, 사용량 로깅, 문제집 배치 생성

| | A: Streamlit Cloud | B: FastAPI+React | C: SaaS |
|---|---|---|---|
| 개발량 | 최소 | 중 | 대 |
| 비용/월 | $0 | $5–20 | $50+ |
| 사용자 | ~수십 | 수백 | 무제한 |
| 계정/이력 | ✗ | ✓ | ✓ |
| 모바일 최적 | △ | ✓ | ✓ |

---

## 3. 컨테이너화 (B/C 또는 자체 서버용)

`Dockerfile` 골격:
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y fonts-nanum && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```
- `fonts-nanum` apt 설치로 폰트 문제 이중 방어
- Streamlit이면 위 CMD, FastAPI면 `uvicorn main:app --host 0.0.0.0 --port 8000`

배포 대상별:
- **Fly.io**: 무료 크레딧 넉넉, 글로벌, `fly launch`로 Dockerfile 자동 인식 — 상주 앱에 적합
- **Railway**: GitHub push→배포, 사용량 과금, 설정 간단
- **Render**: 무료 티어는 유휴 시 슬립(첫 응답 지연) — 개인용 OK, 수업 중엔 유료 권장
- **자체 VPS**(AWS Lightsail / 네이버클라우드): 기관 내부망·로그인 뒤 배치 가능

---

## 4. 성능·안정성 팁
- **PDF 캐시**: 입력 텍스트 해시 키로 생성 결과 캐시(동일 지문 재생성 회피)
- **입력 제한**: 지문 길이 상한(예: 60문장) — 과도한 페이지·메모리 방지
- **모델 선택**: `en_core_web_sm` 유지 권장(경량·저메모리). `trf`는 torch(~2GB)
  필요 → 무료 티어에 부적합, 정확도 향상분 대비 비용 큼
- **비동기 LLM**: 담화 심화 분석(Claude)은 선택적·백그라운드로 — 없어도 규칙 기반 동작
- **관측**: 요청 수·에러 로깅(Sentry 무료 티어)만 붙여도 운영 안정

---

## 5. 권장 실행 순서
1. **지금**: 폰트 번들(1a) + 모델 pin(1b) + 캐시(1c) 적용 → 배포 가능한 상태로 전환
2. **1주차**: Streamlit Community Cloud 또는 HF Spaces에 올려 실사용 검증 (시나리오 A)
3. **수요 확인 후**: 계정·이력·모바일이 필요해지면 FastAPI+React로 확장 (시나리오 B)
4. **수익화 시점**: 결제·배치·CDN 추가 (시나리오 C)

> 요지: **코드 재작성 없이 폰트·모델·캐시 3가지만 고치면 오늘 배포 가능**하며,
> 사용자가 늘면 백엔드를 API로 떼어내 React 프론트로 확장하는 2단계 경로가 가장
> 비용 효율적입니다.
