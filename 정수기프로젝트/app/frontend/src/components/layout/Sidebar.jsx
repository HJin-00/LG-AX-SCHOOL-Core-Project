import React from 'react';
import { Link } from 'react-router-dom';
import lgSymbol from '../../assets/lg-symbol.png';
import ConsultationIcon from './ConsultationIcon.jsx';

export default function Sidebar({
  topics,
  activeTopic,
  onTopicSelect,
  onNewChat,
  disabled=false,
}) {
  return (
    <aside className="sidebar">
      <Link className="brand" to="/" aria-label="LG전자 홈으로">
        <span className="brand-symbol brand-logo">
          <img src={lgSymbol} alt="" />
        </span>

        <span className="consultation-brand-name">
          LG전자
          <small>정수기 상담</small>
        </span>
      </Link>

      <button
        className="new-chat"
        type="button"
        disabled={disabled}
        onClick={onNewChat}
        aria-label="새 대화"
      >
        <span className="sidebar-plus" aria-hidden="true">＋</span>
        <span className="sidebar-new-label">새 대화</span>
      </button>

      <div className="nav-title">상담 주제</div>

      <nav aria-label="상담 주제">
        {topics.map((topic) => (
          <button
            key={topic.id}
            className={activeTopic === topic.id ? 'selected' : ''}
            type="button" disabled={disabled}
            onClick={() => onTopicSelect(topic)}
            aria-label={topic.label}
            aria-pressed={activeTopic === topic.id}
            title={topic.label}
          >
            <span className="nav-icon">
              <ConsultationIcon name={topic.id} />
            </span>

            <span className="nav-label">
              {topic.label.replace(/\//g, '·')}
            </span>
          </button>
        ))}
      </nav>

      <Link className="sidebar-foot" to="/">
        ← 홈으로
      </Link>
    </aside>
  );
}