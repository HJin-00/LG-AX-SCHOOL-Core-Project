import React from 'react';
import { Link } from 'react-router-dom';
import purifierImage from '../../assets/publicwater-purifier.jpg';
import lgSymbol from '../../assets/lg-symbol.png';


export default function HomeHero() {
  return (
    <main className="minimal-home">
      <header className="minimal-home__header">
        <div className="minimal-home__brand">
          <img src={lgSymbol} alt="LG" />
          <span>LG전자</span>
        </div>

        <span className="minimal-home__header-text">
          정수기 구독 상담
        </span>
      </header>

      <div className="minimal-home__layout">
        <div className="minimal-home__image">
          <img
            src={purifierImage}
            alt="정수기 제품"
          />
        </div>

        <section className="minimal-home__content">
          <div className="minimal-home__label">
            정수기 구독 상담
          </div>

          <h1>
            <span>정수기,</span>
            <span className="minimal-home__title-end">
              바꾸기 전에
            </span>
          </h1>

          <p className="minimal-home__description">
            내 계약을 이해하고, 날짜별 추가 부담을 비교하세요.
          </p>

          <div className="minimal-home__actions">
            <Link
              to="/existing"
              className="minimal-home__button minimal-home__button--primary"
            >
              내 계약 상담 시작
              <span aria-hidden="true">→</span>
            </Link>

            <a
              href="https://www.lge.co.kr/category/water-purifiers" target="_blank" rel="noopener noreferrer"
              className="minimal-home__button minimal-home__button--secondary"
            >
              LG 공식 제품 알아보기
              <span aria-hidden="true">→</span>
            </a>
          </div>

          <p className="minimal-home__hint">
            계약기간 · 예상 정산 · 시점 비교 · 상담 준비
          </p>
        </section>
      </div>
    </main>
  );
}