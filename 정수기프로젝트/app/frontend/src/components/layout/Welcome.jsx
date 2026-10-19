import React from 'react';
import { Link } from 'react-router-dom';
import { services } from './topics.js';
import lgSymbol from '../../assets/lg-symbol.png';
import purifierImage from '../../assets/consultation-purifier.png';
import ConsultationIcon from './ConsultationIcon.jsx';


export default function Welcome({
  busy=false,
  topics,
  serviceType,
  onTopicSelect,
  onLoadProduct,
  selectedProduct,
}) {
  if (!serviceType) {
    return (
      <section className="welcome home-welcome">
        <div className="home-lg-symbol">
          <img src={lgSymbol} alt="LG" />
        </div>

        <div className="overline">WATER PURIFIER ASSISTANT</div>
        <h1>정수기 상담 가이드</h1>
        <p>제품 구매와 구독 중 이용할 서비스를 선택해 주세요.</p>

        <div className="service-choice-grid">
          {Object.entries(services).map(([type, service]) => (
            <Link
              className="service-choice-card"
              key={type}
              to={`/${type}`}
            >
              <strong>{service.label}</strong>
              <small>상담 시작하기</small>
              <b aria-hidden="true">→</b>
            </Link>
          ))}
        </div>
      </section>
    );
  }

  const service = services[serviceType];

  if (!service) return null;

  const isExistingCustomer = serviceType === 'existing';
  const serviceTopics = topics || service.categories;
  const topicMap = Object.fromEntries(
    serviceTopics.map((topic) => [topic.id, topic]),
  );
  const primaryTopic = 'cancel';
  const contractTopic=isExistingCustomer?'contract':'purchase_method';
  const modelTopic=isExistingCustomer?'renewal':'recommend';

  function selectTopic(id) {
    const topic = topicMap[id];

    if (topic) {
      onTopicSelect?.(topic);
    }
  }

  return (
    <section className={'welcome bento-welcome'+(!isExistingCustomer?' bento-welcome--purchase':'')}>
      <div className="bento-intro">
        <h1>
          {isExistingCustomer
            ? '내 계약을 확인하고 유지·재구독을 비교해요'
            : '내 생활에 맞는 정수기를 찾아볼까요?'}
        </h1>

        <p>
          {isExistingCustomer
            ? '계속 사용·교체·해지, 원하시는 방향에 맞춰 필요한 정보를 확인해요.'
            : '제품 선택부터 계약 조건까지, 함께 살펴봐요.'}
        </p>
      </div>

      <div className="bento-grid">
        <article className="bento-product-card">
          <div className="bento-product-heading">
            <h2>
              {selectedProduct?.productName ||
                (isExistingCustomer
                  ? '내 정수기부터 확인해요'
                  : '내게 맞는 정수기를 찾아요')}
            </h2>

            <p>
              {selectedProduct
                ? '선택한 제품을 기준으로 상담해요.'
                : isExistingCustomer
                  ? '제품에 맞춰 안내받을 수 있어요.'
                  : '사용 환경에 맞춰 제품을 안내해요.'}
            </p>
          </div>

          <div className={'bento-product-visual'+(selectedProduct?.imageUrl?' bento-product-visual--owned':'')}>
            <img
              src={selectedProduct?.imageUrl||purifierImage}
              alt={selectedProduct?selectedProduct.modelId+' 내 정수기':'정수기 예시 이미지'}
            />
          </div>

          <button
            type="button"
            className="bento-product-button"
            disabled={busy || (isExistingCustomer ? !onLoadProduct : !topicMap[modelTopic])}
            onClick={() => {
              if (isExistingCustomer) {
                if(selectedProduct)selectTopic(modelTopic);
                else onLoadProduct?.();
              } else {
                selectTopic(modelTopic);
              }
            }}
          >
            <span>
              {isExistingCustomer
                ? selectedProduct
                  ? '이 제품과 다른 모델 비교'
                  : '내 제품 불러오기'
                : '제품 추천받기'}
            </span>
            <span aria-hidden="true">→</span>
          </button>
        </article>

        <button
          type="button"
          className="bento-action bento-assistance"
          onClick={() => selectTopic(primaryTopic)}
          disabled={busy||!topicMap[primaryTopic]}
        >
          <span className="bento-action-icon">
            <ConsultationIcon name={primaryTopic} />
          </span>

          <span className="bento-action-copy">
            <strong>
              {isExistingCustomer
                ? '지금 해지하면 얼마인가요?'
                : '궁금한 기능이 있나요?'}
            </strong>

            <span>
              {isExistingCustomer
                ? '검토일 기준 예상 정산을 확인해요.'
                : '제품의 기능과 사용법을 알아보세요.'}
            </span>
          </span>

          <span className="bento-action-link">
            {isExistingCustomer ? '예상 비용 확인' : '기능 알아보기'}
            <span aria-hidden="true">→</span>
          </span>

          <svg
            className="bento-assistance-art"
            viewBox="0 0 180 180"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            focusable="false"
          >
            <rect x="30" y="28" width="70" height="133" rx="7" />
            <path d="M100 28l42 7v117l-42 9" />
            <path d="M62 80s-9 10-9 16a9 9 0 0 0 18 0c0-6-9-16-9-16Z" />
            <rect x="49" y="145" width="30" height="16" rx="5" />
            <path d="M16 163h144" opacity=".35" />
          </svg>
        </button>

        {isExistingCustomer&&(<button
          type="button"
          className="bento-action bento-contract"
          onClick={() => selectTopic(contractTopic)}
          disabled={busy||!topicMap[contractTopic]}
        >
          <span className="bento-action-icon">
            <ConsultationIcon name="contract" />
          </span>

          <span className="bento-action-copy">
            <strong>{isExistingCustomer?'내 계약은 언제 끝나나요?':'구매·구독 선택'}</strong>
            <span>{isExistingCustomer?'약정과 해지 조건을 살펴봐요.':'구매와 구독의 차이를 살펴봐요.'}</span>
          </span>

          <span className="bento-action-arrow" aria-hidden="true">
            →
          </span>
        </button>)}

        <button
          type="button"
          className="bento-action bento-recommend"
          onClick={() => selectTopic(modelTopic)}
          disabled={busy||!topicMap[modelTopic]}
        >
          <span className="bento-action-icon">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
              aria-hidden="true"
              focusable="false"
            >
              <rect x="4" y="9" width="6" height="12" rx="1.5" />
              <rect x="14" y="3" width="6" height="18" rx="1.5" />
            </svg>
          </span>

          <span className="bento-action-copy">
            <strong>
              {isExistingCustomer
                ? '다른 정수기로 바꾸면 어떨까요?'
                : '내게 맞는 모델 찾기'}
            </strong>
            <span>{isExistingCustomer?'원하는 기능으로 후보를 찾고 내 계약과 비교해요.':'내 생활에 맞는 제품을 찾아요.'}</span>
          </span>

          <span className="bento-action-arrow" aria-hidden="true">
            →
          </span>
        </button>
      </div>
      <nav className="official-channel-links"><span>제품 구매·사용 상담은 공식 서비스에서</span><a href="https://www.lge.co.kr/category/water-purifiers" target="_blank" rel="noopener noreferrer">LG 정수기 제품 알아보기 ↗</a><a href="https://www.lge.co.kr/ai-commerce/aiAssistant" target="_blank" rel="noopener noreferrer">사용방법·오류 상담 / AI Chat ↗</a></nav>
    </section>
  );
}