import React from 'react';

const icons = {
  recommend: (
    <>
      <path d="m12 3 9 5-9 5-9-5 9-5Z" />
      <path d="M3 8v8l9 5 9-5V8M12 13v8" />
    </>
  ),
  contract: (
    <>
      <rect x="5" y="3" width="14" height="18" rx="2" />
      <path d="M8 8h8M8 12h8M8 16h5" />
    </>
  ),
  usage: (
    <>
      <path d="M4 7h3m4 0h9M4 17h9m4 0h3" />
      <circle cx="9" cy="7" r="2" />
      <circle cx="15" cy="17" r="2" />
    </>
  ),
  troubleshoot: (
    <path d="M14.5 6.5a4 4 0 0 0-5 5L3 18a2 2 0 0 0 3 3l6.5-6.5a4 4 0 0 0 5-5l-3 3-3-3 3-3Z" />
  ),
  cancel: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="m9 9 6 6m0-6-6 6" />
    </>
  ),
  other: (
    <>
      <path d="M21 11a8 8 0 0 1-8 8H7l-4 3 1.5-5A8 8 0 1 1 21 11Z" />
      <circle cx="8" cy="11" r=".7" fill="currentColor" stroke="none" />
      <circle cx="12" cy="11" r=".7" fill="currentColor" stroke="none" />
      <circle cx="16" cy="11" r=".7" fill="currentColor" stroke="none" />
    </>
  ),
  product: (
    <>
      <rect x="5" y="2" width="14" height="20" rx="3" />
      <path d="M5 16h14M9 19h6" />
      <path d="M12 6s-2 2.5-2 4a2 2 0 0 0 4 0c0-1.5-2-4-2-4Z" />
    </>
  ),
};

export default function ConsultationIcon({ name }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {icons[({features:'usage',renewal:'recommend',care:'product',purchase_method:'contract',installation:'product'})[name]||name] || icons.other}
    </svg>
  );
}