import React,{useRef,useState}from 'react';
export default function ProductCarousel({children,label='추천 제품'}){
 const items=React.Children.toArray(children);const track=useRef(null);const[index,setIndex]=useState(0);
 function move(next){
  const target=Math.max(0,Math.min(items.length-1,next));const item=track.current?.children[target];
  if(item)track.current.scrollTo({left:item.offsetLeft,behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
 }
 if(items.length<2)return <>{items}</>;
 return <section className="product-carousel" aria-label={label}>
  <div className="product-carousel-toolbar"><strong>{label}</strong><div><button type="button" aria-label={label+' 이전 제품'} disabled={index===0} onClick={()=>move(index-1)}>‹</button><span aria-live="polite">{index+1} / {items.length}</span><button type="button" aria-label={label+' 다음 제품'} disabled={index===items.length-1} onClick={()=>move(index+1)}>›</button></div></div>
  <div className="product-carousel-track" ref={track} tabIndex={0} aria-label="좌우 방향키 또는 스와이프로 제품 넘기기" onKeyDown={e=>{if(e.target!==e.currentTarget)return;if(e.key==='ArrowRight'){e.preventDefault();move(index+1);}if(e.key==='ArrowLeft'){e.preventDefault();move(index-1);}}} onScroll={e=>{const element=e.currentTarget;const first=element.children[0];const second=element.children[1];const stride=second?second.offsetLeft-first.offsetLeft:element.clientWidth;setIndex(Math.min(items.length-1,Math.max(0,Math.round(element.scrollLeft/stride))));}}>
   {items.map((item,n)=><div className="product-carousel-slide" key={item.key||n} role="group" inert={n!==index} aria-label={(n+1)+'번째 제품'}>{item}</div>)}
  </div><p className="product-carousel-hint">화살표로 넘겨보세요. 모바일에서는 좌우로 밀어볼 수 있어요.</p>
 </section>;
}
