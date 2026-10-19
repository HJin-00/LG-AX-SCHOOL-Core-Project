import React from 'react';

function safeUrl(value){try{const url=new URL(value);return ['https:','http:'].includes(url.protocol)?url.href:null;}catch{return null;}}
export default function SourceBox({ sources = [] }) {
  if (!sources.length) return null;

  return (
    <div className="source-box">
      <span>참고 자료 · 개별 적용 여부 확인 필요</span>
      {sources.map((source, index) =>
        safeUrl(source.url) ? (
          <a
            key={source.document_id || `${source.title}-${index}`}
            href={safeUrl(source.url)}
            target="_blank"
            rel="noopener noreferrer"
          >
            {source.title}
            {source.section ? ` · ${source.section}` : ''} ↗
          </a>
        ) : (
          <span className="source-text" key={source.document_id || `${source.title}-${index}`}>
            {source.title}
            {source.section ? ` · ${source.section}` : ''}
          </span>
        ),
      )}
    </div>
  );
}