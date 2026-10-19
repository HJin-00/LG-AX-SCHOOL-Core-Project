"""검수된 동일 제품군·색상 정보만 사용한다. 모델명 유사성으로 묶지 않는다."""
import csv
from pathlib import Path

def variant_metadata():
    path=Path(__file__).parent.parent/'data/product_variants.csv'
    with path.open(encoding='utf-8-sig',newline='') as file:
        return {r['model_id']:r for r in csv.DictReader(file) if r['review_status']=='verified'}

def group_products(products):
    metadata=variant_metadata();groups={}
    for product in products:
        row=metadata.get(product['model_id'])
        if row:product={**product,**{k:row[k] for k in ('family_id','color_name','color_hex')}}
        # A family ID alone cannot merge different recorded specifications.
        key=(product.get('family_id',product['model_id']),repr(sorted(product['features'].items())))
        groups.setdefault(key,[]).append(product)
    result=[]
    for variants in groups.values():
        preferred=next((p for p in variants if p['model_id'].endswith('RH')),variants[0])
        result.append({**preferred,'variants':variants if len(variants)>1 else []})
    return sorted(result,key=lambda p:p['model_id'])
