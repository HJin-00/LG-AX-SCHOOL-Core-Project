export function cardComponents({card,monthlyFee,spend,eligible,eligibility,applicationDate,today,chargeDate,promotionMonth=1}){
 const status=eligibility??(eligible?'promotion':'unconfirmed');
 if(!card||status==='unconfirmed'||spend===''||spend==null||!Number.isFinite(Number(spend))||Number(spend)<0)return {base:0,promotion:0,discount:0};
 const tier=[...card.tiers].sort((a,b)=>b.spend-a.spend).find(t=>Number(spend)>=t.spend);
 if(!tier)return {base:0,promotion:0,discount:0};
 const registered=applicationDate||today;const bill=chargeDate||today;
 const active=status==='promotion'&&registered>=card.promotion_start&&registered<=card.promotion_end&&(!card.promotion_service_start||bill>=card.promotion_service_start)&&(!card.promotion_service_end||bill<=card.promotion_service_end)&&promotionMonth<=card.months;
 const base=Math.min(monthlyFee,tier.base);const discount=Math.max(0,Math.min(monthlyFee,tier.base+(active?tier.promotion:0)));
 return {base,promotion:discount-base,discount};
}
export function cardDiscount(input){return cardComponents(input).discount;}
