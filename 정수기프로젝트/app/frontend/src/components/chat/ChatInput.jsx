import React from 'react';

export default function ChatInput({
  value = '',
  onChange,
  onSubmit,
  disabled = false,
  showExample = false,
  busy=false,
}) {
  return (
    <form
      className="composer"
      onSubmit={(event) => {
        event.preventDefault();

        if (!disabled && value.trim()) {
          onSubmit();
        }
      }}
    >
      <label className="sr-only" htmlFor="message">
        정수기 관련 질문
      </label>

      <div className="consultation-input-copy">
        <input
          id="message"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="궁금한 내용을 바로 물어보세요"
          autoComplete="off"
          disabled={disabled}
        />


      </div>

      <button
        type="submit"
        disabled={disabled || !value.trim()}
        aria-label={busy ? '답변을 기다리는 중' : '질문 보내기'}
        title="질문 보내기"
      >
        <span aria-hidden="true">{disabled ? '…' : '↑'}</span>
      </button>
    </form>
  );
}