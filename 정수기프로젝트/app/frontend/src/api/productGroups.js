export function groupColorOffers(offers){
 const groups=new Map();
 for(const offer of offers){
  const p=offer.product;
  const key=p?.family_id ? JSON.stringify([p.family_id,p.features,offer.care_details,offer.contract_months,offer.source_kind]) : offer.offer_id;
  if(!groups.has(key))groups.set(key,[]);
  groups.get(key).push(offer);
 }
 return [...groups.values()];
}
