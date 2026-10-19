"""A의 async run_agent(message, session_context)를 연결하는 경계."""

from .schemas import AgentReply, AgentResult


class AgentUnavailable(Exception):
    pass


class ModelProviderFailure(AgentUnavailable):
    def __init__(self, code, answer):
        self.code,self.answer=code,answer
        super().__init__(answer)


class ToolFailure(Exception):
    pass


async def stub_agent(message: str, session_context: dict) -> AgentResult:
    if not session_context.get("product_model"):
        reply = AgentReply(status="needs_info", topic="unknown",
                           answer="[API 연결 테스트] 실제 AI 상담은 아직 연결되지 않았습니다. 정수기 모델명을 알려주시겠어요?",
                           missing_fields=["product_model"])
    else:
        reply = AgentReply(status="answered", topic="unknown",
                           answer="[API 연결 테스트] 모델과 입력 형식을 확인했습니다. 실제 제품 안내·계약 계산·Tool 실행은 A/D/E 연결 후 제공됩니다.")
    return AgentResult(reply=reply)


def load_agent(mode: str):
    if mode == "stub":
        return stub_agent
    if mode == "langchain":
        from 정수기프로젝트.app.agent.langchain_agent import configured_runner
        return configured_runner()
    return None
