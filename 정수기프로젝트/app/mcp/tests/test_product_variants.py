from copy import deepcopy
from 정수기프로젝트.app.mcp.tools import lookup_product_features
from 정수기프로젝트.app.mcp.support.product_variants import group_products
from 정수기프로젝트.app.agent.langchain_agent import verified_result

def test_same_family_colors_keep_their_own_images_prices_and_model_ids():
    products=lookup_product_features(['WD721RH','WD721RE','WD721RK'])['products']
    grouped=group_products(products)
    assert len(grouped)==1
    raw={'reply':{'status':'answered','topic':'purchase','answer':'후보','sources':[],'cards':[],'missing_fields':[]}}
    result=verified_result(raw,[{'status':'ok','requirements':[],'products':grouped,'message':'색상 선택'}]).reply
    variants={p.model_id:p for p in result.cards[0].data.variants}
    assert {v.color_name for v in variants.values()}=={'에센스 화이트','카밍 베이지','블랙'}
    for original in products:
        assert variants[original['model_id']].image_url==original['image_url']
        assert variants[original['model_id']].purchase_price==original['purchase_price']
    assert len({v.image_url for v in variants.values()})==3

def test_different_features_or_series_are_not_grouped_as_colors():
    products=lookup_product_features(['WD721RH','WD721RE','WD722RH'])['products']
    changed=deepcopy(products);changed[1]['features']['온수']=False
    assert len(group_products(changed))==3
    assert len(group_products(products))==2
