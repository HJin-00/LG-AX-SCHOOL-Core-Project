# LG AX SCHOOL 핵심프로젝트

## 정수기 계약 상담 AI

정수기 이용 고객이 유지·교체·해지를 고민할 때, 자신의 계약 조건과 새 구독 조건을 함께 확인하고 다음 행동을 판단하도록 돕는 고객용 AI Agent입니다.

### 주요 기능
- 동의한 범위의 가상 계약 정보 조회와 계약 기간·연차별 월요금 안내
- 오늘 또는 지정한 날짜 기준 예상 해지 비용 계산
- 기존 제품 유지와 새 제품 구독 비용·주요 기능 비교
- 교체 이유에 따른 상담과 제품 후보 선택
- 상담 내용을 정리한 PDF 상담 준비서 다운로드

실제 계약 해지·가입·결제는 수행하지 않습니다. 사용방법·고장 문의는 LG 공식 AI Chat으로 안내합니다. LG 실제 고객 시스템과 연동된 서비스가 아니며, 계약서는 가상 데이터입니다.

### 구성
| 경로 | 내용 |
| --- | --- |
| `정수기프로젝트/app/frontend` | React 화면 |
| `정수기프로젝트/app/web` | Node.js 중계 서버 |
| `정수기프로젝트/app/backend/ai` | FastAPI 요청 처리 |
| `정수기프로젝트/app/agent` | LangChain Agent와 시스템 프롬프트 |
| `정수기프로젝트/app/mcp` | 계약 조회·계산·PDF 생성 도구 |
| `정수기프로젝트/app/rag` | 공식 자료와 검색·벡터 인덱스 코드 |
| `docs` | 데이터 분석, CX 문제 정의, Agent 설계서, 평가 요약, 최종 발표자료 |

React → Node.js → FastAPI → LangChain → RAG / FastMCP 흐름입니다. MySQL은 계정·세션·동의 등 서비스 정보를 관리하고, Chroma는 공개 문서 검색용 벡터 인덱스를 저장합니다. 개인 계약 자료는 공개 문서 검색 자료와 분리합니다.

### Windows 실행
1. Python 3.12와 Node.js를 설치합니다. 설치가 필요하면 `INSTALL_WINDOWS.cmd`를 실행합니다.
2. `정수기프로젝트/app/config/app.env.example`을 같은 폴더의 `app.env`로 복사합니다.
3. 본인의 API 키와 사용 가능한 MySQL 접속 정보를 입력합니다. MySQL 스키마·초기 데이터 준비 방법은 `정수기프로젝트/app/database` 및 실행 안내를 확인합니다.
4. `START_WINDOWS.cmd`를 실행합니다. 첫 실행은 의존성 설치와 프런트엔드 빌드에 시간이 걸립니다.
5. 브라우저에서 `http://127.0.0.1:3001`을 확인합니다.

자세한 내용은 `Windows_실행방법.txt`를 확인하세요. Windows 실제 PC에서의 최종 실행 확인은 별도로 필요합니다.

### macOS / Linux 실행
Python 3.12와 Node.js 설치 후 저장소 루트에서 실행합니다.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r 정수기프로젝트/app/requirements.txt
cp 정수기프로젝트/app/config/app.env.example 정수기프로젝트/app/config/app.env
# app.env에 API 키와 MySQL 접속 정보 입력
python -m 정수기프로젝트.app.run api
```

다른 터미널에서:

```bash
cd 정수기프로젝트/app/frontend
npm ci
npm run build
npm start
```

### RAG 인덱스
가상환경을 활성화한 저장소 루트에서 `python -m 정수기프로젝트.app.run rag-index`로 생성합니다. 공개 문서 임베딩에 API 비용이 발생할 수 있습니다. 생성한 로컬 인덱스와 실행 로그는 Git에 포함하지 않습니다.

### 평가 자료
평가 시나리오와 개선 내용은 `docs/05_평가` 및 Agent 설계서에 있습니다. 개선 후 결과는 같은 평가셋을 재검증한 결과이며, 모든 새로운 질문에서의 성공을 뜻하지 않습니다.

### 설정과 자료 관리
API 키·DB 비밀번호·실제 ENV·기존 ENV 포함 ZIP·실행 로그는 제외했습니다. 팀원의 접속 설정은 별도로 안전하게 전달해야 합니다. 제3자 공식 문서·제품 이미지·로고·음원의 권리는 각 권리자에게 있습니다.

시연 영상 음성: Typecast 소이 (https://typecast.ai/kr). 배경음: Monkeys Spinning Monkeys — Kevin MacLeod (incompetech.com), CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), 편집 사용.

### 담당 및 기여 · 김현진

프로젝트 전체 통합과 Agent 개발을 중심으로, 팀원이 작성한 초기 구현을 연결하고 FastAPI·FastMCP·React·RAG까지 추가 구현 및 수정했습니다. 아래는 초기 역할 분담이 아닌 최종 개발 과정에서 직접 진행한 작업 범위입니다.

| 영역 | 구현·개선 내용 | 관련 코드 |
| --- | --- | --- |
| 서비스 설계·전체 통합 | 데이터 인사이트와 CX 문제를 계약 상담 흐름에 연결하고, 계약 이해 → 비용 확인 → 유지·교체 비교 → 상담 준비로 서비스 범위 정리. React·Node.js·FastAPI·Agent·MCP 연결 | `정수기프로젝트/app` |
| LangChain Agent | LLM이 질문과 대화 맥락을 보고 도구를 선택하도록 구성. 교체 이유·해지 의도·후속 질문 처리, 시스템 프롬프트 통합 정리, 도구 입력과 실행 결과 검증. OpenAI·Anthropic 설정 전환 | `app/agent`, `app/config` |
| FastAPI 추가 구현 | 채팅과 Agent 실행 연결, 로그인·세션·동의 상태 관리, 계약 연결과 서버 측 권한 전달, 대화 상태 유지, 입력·응답 검증, 상담 준비서 파일 처리 보완 | `app/backend/ai` |
| FastMCP 추가 구현 | 11개 도구의 설명·입력 명세 정리와 Agent 연결. 계약 조회, 연차별 월요금, 해지 정산, 두 날짜 비용 비교, 유지·재구독 비교, 상담 준비서 생성 로직 보완 | `app/mcp/server.py`, `app/mcp/client_adapter.py`, `app/mcp/contracts`, `app/mcp/subscription` |
| 비용 계산·계약 데이터 | 오늘 또는 고객이 고른 날짜를 기준으로 계산하고, 기존 계약 해지 비용과 새 구독 조건을 같은 기간으로 비교하도록 수정. 가상 계약을 케이스별로 구분하고 계약·청구 정보 반영 | `app/mcp/contracts`, `app/mcp/subscription`, `정수기프로젝트/04_Agent설계` |
| Node.js | 화면과 FastAPI 간 동일 출처 API 중계, 로그인 쿠키 전달, 프런트엔드 제공과 실행 연결 | `app/web` |
| React 추가 구현 | 교체 이유 선택과 후속 행동, 대화 내 동의, 제품 후보·기능 필터·색상 묶음, 비교 결과와 날짜 변경, 응답 중 표시, 계약 연결·로그인 후 대화 복귀, PDF 다운로드 동선 개선 | `app/frontend` |
| RAG 연결·검색 개선 | 팀원이 수집한 공식 문서를 서비스에 연결하고, Chroma 벡터 검색과 키워드 검색 결합. 적용 모델·조건에 맞는 검색과 검증을 보완하고 개인 계약 자료를 공용 검색에서 분리 | `app/rag` |
| 테스트·평가 개선 | 기능별·대화 흐름별 테스트와 회귀 검증. 도구 선택·날짜·비용 누락·권한·맥락 오류를 수정하고 동일 평가 시나리오로 개선 전후 확인 | 각 모듈의 `tests`, `docs/05_평가` |
| 실행 환경·산출물 | Windows 실행 스크립트와 의존성 구성, 팀 공유·제출용 파일 정리. Agent 설계서·시연 시나리오·발표자료·발표 대본 정리 및 개선 | 저장소 루트 실행 파일, `docs` |

표의 `app/...` 경로는 `정수기프로젝트` 폴더 기준입니다. 팀 프로젝트의 공동 결과물을 바탕으로 수행한 통합·추가 개발·개선 범위를 정리했습니다.
