# LG AX SCHOOL 핵심프로젝트

## 정수기 계약 상담 AI · 티라노4우르스

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

### 팀원
- 김현진: 전체 통합, Agent, Node.js
- 변시연: React, 디자인, 시연 영상
- 나홍주: FastAPI
- 김산: RAG, 데이터 분석
- 김시현: FastMCP
