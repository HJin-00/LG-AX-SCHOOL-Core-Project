import React from 'react';
export default function Icon({name,size=20}){
 const paths={menu:<path d="M4 6h16M4 12h16M4 18h16"/>,water:<><path d="M12 3C9 7 5 11 5 15a7 7 0 0 0 14 0c0-4-4-8-7-12Z"/><path d="M8 15a4 4 0 0 0 4 4"/></>,shield:<><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/></>,home:<><path d="m3 10 9-7 9 7v10H3Z"/><path d="M9 20v-7h6v7"/></>,arrow:<path d="M4 12h16m-6-6 6 6-6 6"/>,file:<><path d="M14 3H5v18h14V8Z"/><path d="M14 3v5h5M8 12h8m-8 4h8"/></>,left:<path d="M20 12H4m6-6-6 6 6 6"/>};
 return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]||paths.water}</svg>;
}
