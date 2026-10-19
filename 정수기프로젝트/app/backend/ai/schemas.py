"""공통 API v0.1 구현안. 세부 카드/문맥 필드는 A·B·E 통합 시 합의한다."""
from datetime import date
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, field_validator, model_validator

Text = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=2000)]
ShortText = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=120)]
SessionId = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9_-]{8,128}$")]
BriefId = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9_-]{8,80}$")]
Money = Annotated[int, Field(strict=True, ge=0)]
Topic = Literal["purchase", "troubleshoot", "care_subscription", "contract", "unknown"]
Status = Literal["needs_info", "answered", "brief_created", "error"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ContextInput(Model):
    """생략=유지, 명시적 null=삭제. 날짜는 YYYY-MM-DD만 허용한다."""
    symptom: Text | None = None
    occurred_at: ShortText | None = None
    lock_status: Literal["locked", "unlocked", "unknown"] | None = None
    continuous_after_wipe: Annotated[bool, Field(strict=True)] | None = None
    usage_type: Literal["purchase", "subscription", "unknown"] | None = None
    desired_features: Annotated[list[ShortText], Field(max_length=10)] | None = None
    installation_space: ShortText | None = None
    mandatory_end: date | None = None
    contract_end: date | None = None
    exit_date: date | None = None
    arrears: Money | None = None
    discount_return: Money | None = None

    @field_validator("mandatory_end", "contract_end", "exit_date", mode="before")
    @classmethod
    def iso_date_only(cls, value):
        if value is None or type(value) is date:
            return value
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("날짜는 YYYY-MM-DD 형식이어야 합니다.")
        return date.fromisoformat(value)

    @model_validator(mode="after")
    def period_order(self):
        if self.mandatory_end and self.contract_end and self.mandatory_end > self.contract_end:
            raise ValueError("의무사용 종료일은 전체 계약 종료일보다 늦을 수 없습니다.")
        return self


class ChatRequest(Model):
    session_id: SessionId = Field(description="클라이언트에서 생성한 무작위 ID. 새 대화는 새 ID 사용")
    message: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=4000)]
    product_model: ShortText | None = None
    context_input: ContextInput | None = None
    demo_fixture_id: Literal["DEMO-A", "DEMO-B", "DEMO-C", "DEMO-D", "DEMO-E", "DEMO-P1", "DEMO-P2"] | None = None


class Source(Model):
    document_id: ShortText
    title: Text
    url: HttpUrl | None = None
    section: ShortText | None = None
    model_id: ShortText | None = None
    checked_at: date | None = None


class PeriodSummary(Model):
    mandatory_end: date | None = None
    contract_end: date | None = None
    exit_date: date | None = None


class CostItem(Model):
    name: ShortText
    status: Literal["confirmed", "not_applicable", "unverified"]
    amount: Money | None
    source_ids: list[ShortText] = Field(default_factory=list)

    @model_validator(mode="after")
    def amount_status(self):
        if self.status == "unverified" and self.amount is not None:
            raise ValueError("미확인 금액은 null이어야 합니다.")
        if self.status == "confirmed" and self.amount is None:
            raise ValueError("확인된 항목에는 금액이 필요합니다.")
        if self.status == "not_applicable" and self.amount not in (0, None):
            raise ValueError("미적용 항목에 비용을 넣을 수 없습니다.")
        return self


class ContractData(Model):
    period_summary: PeriodSummary
    cost_items: list[CostItem]
    confirmed_subtotal: Money
    estimated_total: Money | None
    is_demo: bool
    limitations: Text

    @model_validator(mode="after")
    def amounts_consistent(self):
        subtotal = sum(x.amount or 0 for x in self.cost_items if x.status == "confirmed")
        if self.confirmed_subtotal != subtotal:
            raise ValueError("확인 소계가 확인된 항목 합계와 다릅니다.")
        if any(x.status == "unverified" for x in self.cost_items) and self.estimated_total is not None:
            raise ValueError("미확인 항목이 있으면 총액은 null입니다.")
        if self.estimated_total is not None and self.estimated_total != subtotal:
            raise ValueError("총액이 항목 합계와 다릅니다.")
        return self


class CardBenefitTier(Model):
    spend: int = Field(ge=0)
    base: int = Field(ge=0)
    promotion: int = Field(ge=0)


class CardBenefit(Model):
    promotion_service_start: date | None = None
    promotion_service_end: date | None = None
    base_duration_note: str | None = None
    id: ShortText
    name: ShortText
    annual_fee: int = Field(ge=0)
    months: int = Field(ge=1)
    promotion_start: date
    promotion_end: date
    tiers: list[CardBenefitTier]
    conditions: Text
    source_url: str


class PurchaseCardDiscount(Model):
    name: ShortText
    benefit: Text
    condition: Text


class InstallmentPeriod(Model):
    period: ShortText
    condition: Text


class InstallmentCard(Model):
    name: ShortText
    periods: list[InstallmentPeriod]


class SimplePaymentBenefit(Model):
    name: ShortText
    benefit: Text
    conditions: Text


class AdditionalPurchaseBenefit(Model):
    title: ShortText
    description: Text
    url: str


class HistoricalCoupon(Model):
    coupon_name: Text
    coupon_discount: Money
    coupon_price: Money
    checked_at: date
    source_url: str


class PurchaseBenefits(Model):
    historical_coupon: HistoricalCoupon | None = None
    historical_payment_cards: list[PurchaseCardDiscount] = Field(default_factory=list)
    historical_payment_checked_at: date | None = None
    historical_installment_cards: list[InstallmentCard] = Field(default_factory=list)
    member_price: Money
    coupon_price: Money | None
    coupon_name: Text | None
    coupon_discount: Money
    max_benefit_price: Money
    settlement_discount: Money
    payment_cards: list[PurchaseCardDiscount]
    installment_cards: list[InstallmentCard]
    simple_payment: list[SimplePaymentBenefit]
    additional: list[AdditionalPurchaseBenefit]
    notice: Text
    installment_notice: Text
    checked_at: date
    source_url: str


class ProductData(Model):
    family_id: ShortText | None = None
    color_name: ShortText | None = None
    color_hex: str | None = None
    variants: list['ProductData'] = Field(default_factory=list)
    comparison_supported: bool = False
    purchase_benefits: PurchaseBenefits | None = None
    card_benefits: list[CardBenefit] = Field(default_factory=list)
    display_name: ShortText | None = None
    image_url: str | None = None
    product_url: str | None = None
    purchase_price_status: Literal['available','unavailable','unverified'] | None = None
    purchase_price: int | None = Field(default=None, ge=0)
    subscription_monthly_from: int | None = Field(default=None, ge=0)
    price_checked_at: date | None = None
    price_note: Text | None = None
    model_id: ShortText
    features: dict[ShortText, str | bool | None]
    checked_at: date | None
    source_ids: list[ShortText]
    limitations: Text
    is_demo: bool


class TroubleshootData(Model):
    model_id: ShortText
    symptom: Text
    next_steps: list[Text]
    checked_at: date | None
    source_ids: list[ShortText]
    safety_notice: Text
    limitations: Text
    is_demo: bool


class CareData(Model):
    model_id: ShortText | None
    guidance: Text
    checked_at: date | None
    source_ids: list[ShortText]
    limitations: Text
    is_demo: bool


class PurchaseMethodOption(Model):
    name: ShortText
    payment: Text
    care: Text
    period: Text
    suitable: Text


class PurchaseMethodData(Model):
    options: list[PurchaseMethodOption]
    limitations: Text


class PurchaseMethodCard(Model):
    type: Literal["purchase_method"]
    data: PurchaseMethodData


class ContractCard(Model):
    type: Literal["contract"]
    data: ContractData


class ProductCard(Model):
    type: Literal["product"]
    data: ProductData


class TroubleshootCard(Model):
    type: Literal["troubleshoot"]
    data: TroubleshootData


class CareCard(Model):
    type: Literal["care_subscription"]
    data: CareData


class ComparisonOption(Model):
    exit_date: date
    additional_subscription_fee: Money
    exit_cost_total: Money
    additional_total: Money

    @model_validator(mode="after")
    def consistent_total(self):
        if self.additional_total != self.additional_subscription_fee + self.exit_cost_total:
            raise ValueError("추가 부담 합계 불일치")
        return self


class ComparisonData(Model):
    comparison_date: date
    options: Annotated[list[ComparisonOption], Field(min_length=2,max_length=2)]
    difference: Money
    limitations: Text
    is_demo: bool

    @model_validator(mode="after")
    def consistent_difference(self):
        if self.difference != abs(self.options[0].additional_total-self.options[1].additional_total):
            raise ValueError("비교 차이 불일치")
        return self


class ComparisonCard(Model):
    type: Literal["comparison"]
    data: ComparisonData


class RenewalProduct(Model):
    card_benefits: list[CardBenefit] = Field(default_factory=list)
    family_id: ShortText | None = None
    color_name: ShortText | None = None
    color_hex: str | None = None
    model_id: ShortText
    display_name: ShortText | None = None
    image_url: str | None = None
    product_url: str | None = None
    features: dict[str, str | bool | None]
    sources: list[Source] = Field(default_factory=list)


class RenewalOffer(Model):
    source_kind: Literal['official','synthetic'] = 'synthetic'
    offer_id: ShortText
    model_id: ShortText
    product: RenewalProduct | None = None
    care_details: ShortText
    monthly_fee: Money | None
    rate_note: ShortText
    contract_months: Annotated[int, Field(strict=True, ge=1)] | None
    mandatory_months: Annotated[int, Field(strict=True, ge=1)] | None
    selection_reason: Text


class RenewalCatalogData(Model):
    sort_by: Literal["default","monthly_fee"] = "default"
    offers: list[RenewalOffer]
    checked_for_date: date
    limitations: Text


class RenewalCatalogCard(Model):
    type: Literal['renewal_catalog']
    data: RenewalCatalogData


class RenewalRateSegment(Model):
    start_month: Annotated[int,Field(strict=True,ge=1,le=120)]
    end_month: Annotated[int,Field(strict=True,ge=1,le=120)]
    monthly_fee: Money

    @model_validator(mode='after')
    def ordered(self):
        if self.end_month<self.start_month:raise ValueError('요금 적용 회차 순서')
        return self


class RenewalBenefit(Model):
    status: Literal['conditional','not_applicable']
    window_start: str
    window_end: str
    assessment_date: str
    assessment_basis: str
    days_to_contract_end: int
    maximum_rate_percent: int | None = None
    confirmed_rate_percent: int | None = None
    maximum_scenario_saving: int | None = None
    source: Source
    note: str

class RenewalOption(Model):
    selected_card_benefit: dict | None = None
    selected_card_scenario_total: int | None = None
    maximum_card_benefit: dict | None = None
    maximum_card_scenario_total: int | None = None
    renewal_benefit: RenewalBenefit | None = None
    maximum_benefit_scenario_total: int | None = None
    choice: Literal['keep','renew']
    model_id: ShortText | None = None
    product: RenewalProduct | None = None
    care_details: ShortText | None = None
    existing_subscription_cost: Money | None = None
    exit_cost_total: Money | None = None
    subscription_cost: Money | None = None
    subscription_scenario_cost: Money | None = None
    subscription_months: Annotated[int,Field(strict=True,ge=0,le=120)] | None = None
    rate_segments: list[RenewalRateSegment] = Field(default_factory=list,max_length=20)
    scenario_total: Money | None = None
    price_note: Text | None = None
    initial_cost: Money | None = None
    maintenance_cost: Money | None = None
    arrears: Money | None = None
    exit_cost_items: list[dict] = Field(default_factory=list)
    confirmed_subtotal: Money
    estimated_total: Money | None
    missing_fields: list[ShortText]
    remaining_contract_months: Annotated[int,Field(strict=True,ge=0)] | None = None
    remaining_mandatory_months: Annotated[int,Field(strict=True,ge=0)] | None = None

    @model_validator(mode='after')
    def verified_total(self):
        if self.scenario_total is not None:
            if self.subscription_scenario_cost is None or self.scenario_total!=self.confirmed_subtotal+self.subscription_scenario_cost:
                raise ValueError('공식 스냅샷 가정 금액 불일치')
            if self.estimated_total is not None:
                raise ValueError('참고 시나리오를 확정 총액으로 표시할 수 없음')
        if self.estimated_total is None and not self.missing_fields:
            raise ValueError('총액 미확정에는 미확인 항목 필요')
        if self.estimated_total is not None and (self.missing_fields or self.estimated_total!=self.confirmed_subtotal):
            raise ValueError('총액과 확인 항목 불일치')
        return self


class RenewalRequest(Model):
    card_id: str = "none"
    card_spend: int | None = Field(default=None,ge=0)
    card_eligibility: Literal["unconfirmed","base","promotion"] = "unconfirmed"
    card_application_date: date | None = None
    planned_start_date: date | None = None
    offer_id: ShortText
    comparison_date: date
    comparison_months: Annotated[int,Field(strict=True,ge=1,le=120)]
    maintenance_monthly_fee: Money | None
    installation_conditions: dict[str,str]


class RenewalDecision(Model):
    lower_cost_choice: Literal['keep','renew','equal'] | None
    minimum_saving: Money | None
    basis: Literal['exact_modeled_cost','nonnegative_missing_cost_bound','needs_key_info']
    maintenance_break_even_monthly: float | None


class RenewalData(Model):
    decision: RenewalDecision | None = None
    assumptions: list[ShortText] = Field(default_factory=list)
    request: RenewalRequest
    comparison_start: date
    comparison_end: date
    renewal_start: date
    options: Annotated[list[RenewalOption],Field(min_length=2,max_length=2)]
    difference: Money | None
    limitations: Text
    is_demo: bool

    @model_validator(mode='after')
    def verified_difference(self):
        if self.comparison_start>self.comparison_end or self.renewal_start>self.comparison_end:
            raise ValueError('비교 기간 오류')
        if [o.choice for o in self.options]!=['keep','renew']:
            raise ValueError('유지/재구독 선택 순서')
        totals=[o.estimated_total for o in self.options]
        expected=abs(totals[0]-totals[1]) if all(v is not None for v in totals) else None
        if self.difference!=expected:raise ValueError('미확인 비용 또는 차이 불일치')
        return self


class RenewalCard(Model):
    type: Literal['renewal_comparison']
    data: RenewalData


class RenewalTimingData(Model):
    mandatory_end: date | None = None
    suggested_date: date
    contract_end: date
    reference_date: date
    reason: Text
    limitations: Text
    is_demo: bool

    @model_validator(mode='after')
    def future_candidate(self):
        if self.suggested_date<self.reference_date or self.suggested_date<=self.contract_end:
            raise ValueError('후보 날짜가 계약 종료 이전 또는 과거')
        return self


class RenewalTimingCard(Model):
    type: Literal['renewal_timing']
    data: RenewalTimingData


class UsageManualData(Model):
    model_id: ShortText
    title: ShortText
    url: str
    version: str | None = None
    checked_at: date
    limitations: Text


class UsageManualCard(Model):
    type: Literal['usage_manual']
    data: UsageManualData


Card = Annotated[UsageManualCard | ContractCard | PurchaseMethodCard | ProductCard | TroubleshootCard | CareCard | ComparisonCard | RenewalCard | RenewalCatalogCard | RenewalTimingCard, Field(discriminator="type")]


class ErrorDetail(Model):
    code: ShortText
    retryable: bool = False
    fields: list[ShortText] = Field(default_factory=list)


class AgentReply(Model):
    resolved_topic: Literal['usage','features','troubleshoot','care','contract','cancel','renewal','recommend','purchase_method','installation','product_information'] | None = None
    next_actions: list[Literal["compare_new", "exit_cost", "contract_fees", "contract_terms", "official_support"]] = Field(default_factory=list, max_length=3)
    benefit_guidance: Text | None = None
    consultation_recommended: bool = False
    consultation_reason: ShortText | None = None
    status: Status
    topic: Topic
    answer: Text
    sources: list[Source] = Field(default_factory=list)
    cards: list[Card] = Field(default_factory=list)
    missing_fields: list[ShortText] = Field(default_factory=list)
    brief_id: BriefId | None = None
    error: ErrorDetail | None = None

    @model_validator(mode="after")
    def consistent_status(self):
        if (self.status == "brief_created") != (self.brief_id is not None):
            raise ValueError("준비서 생성 상태와 brief_id가 일치해야 합니다.")
        if (self.status == "error") != (self.error is not None):
            raise ValueError("오류 상태에는 error가 필요합니다.")
        if self.status == "needs_info" and not self.missing_fields:
            raise ValueError("추가 질문에는 missing_fields가 필요합니다.")
        return self


class ChatResponse(AgentReply):
    trace_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class ContextUpdate(Model):
    """자연어에서 A가 추출한 수정값. API 응답에는 노출하지 않는다."""
    product_model: ShortText | None = None
    context_input: ContextInput | None = None


class AgentResult(Model):
    reply: AgentReply
    context_update: ContextUpdate | None = None


class HealthResponse(Model):
    status: Literal["ok"] = "ok"
    service: Literal["water-consultation-api"] = "water-consultation-api"
    version: Literal["0.1.0"] = "0.1.0"
    agent_mode: Literal["stub", "live", "langchain"]
    agent_connected: bool
    session_backend: Literal["memory"] = "memory"


class DemoSessionRequest(Model):
    demo_customer_id: Literal["DEMO-U01", "DEMO-U02", "DEMO-U03", "DEMO-U04"]


class ConsentEventRequest(Model):
    action: Literal["grant", "decline", "revoke", "select_profile"]
    scopes: list[Literal["contract_terms", "contract_costs", "care_info"]] = Field(default_factory=list, max_length=3)
    demo_customer_id: Literal["DEMO-U01", "DEMO-U02", "DEMO-U03", "DEMO-U04"] | None = None
