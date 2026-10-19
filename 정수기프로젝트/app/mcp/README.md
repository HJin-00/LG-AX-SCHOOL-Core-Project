# 현재 코드 안내

정수기 계약 이해·정산·날짜 비교·유지/새 모델 재구독 비교·상담 준비가 현재 범위다. 사용방법·오류·관리 일정은 공식 AI Chat 화면으로 연결한다. 신규 구매는 공식 제품 페이지를 연다.

- agent/system_message.txt: 전체 프롬프트. agent/langchain_agent.py: LLM 도구 선택·검증.
- mcp/server.py: 11개 등록 도구. mcp/client_adapter.py: MCP 명세·서버 권한 주입.
- mcp/contracts: 계약 PDF·청구·정산·날짜 비교·준비서·후보일.
- mcp/subscription: 신규 구독 조건과 유지/재구독 비교. 기존 구현 유지.
- rag: 공용 검수 근거. 개인 계약 원문은 공용 RAG에서 제외.
- frontend: 계약 화면·제품 후보 카드·동의·비교·준비서.
- backend/ai: 로그인·세션·동의·본인확인 시연·API·파일 검증.
- web: Node 동일 출처 API 중계.

실행·Windows/MySQL 설정은 팀 공유 폴더 README와 ENV포함 ZIP 안내를 따른다. 키 제외 제출 소스의 SQLite 예시는 독립 검증 옵션이다. API키·쿠키·토큰을 프론트 코드에 넣지 않는다. FastMCP는 LangChain과 같은 Python 프로세스의 Client(mcp) 연결이며 n8n 상담 워크플로는 사용하지 않는다.
