from 정수기프로젝트.app.mcp.tools import lookup_product_features
from 정수기프로젝트.app.mcp.subscription.subscription_offers import demo_catalog_model_ids
from 정수기프로젝트.app.agent.langchain_agent import verified_result

def test_all_demo_color_models_have_checked_purchase_price_stages():
 ids=sorted(demo_catalog_model_ids());products=[]
 for i in range(0,len(ids),8):products+=lookup_product_features(ids[i:i+8])['products']
 assert {p["model_id"] for p in products}==set(ids)
 assert sum(bool(p.get("purchase_benefits")) for p in products)==14
 for product in products:
  b=product.get('purchase_benefits')
  if not b:
   assert product['price_checked_at']=='2026-10-08'
   assert product['subscription_monthly_from'] is not None
   continue
  assert b['member_price']==product['purchase_price']
  assert b['member_price']>=b['max_benefit_price']>=0
  assert b['checked_at']=='2026-10-13'
  assert b['source_url'].startswith('https://www.lge.co.kr/')
  if b.get('historical_coupon'):
   assert b['historical_coupon']['checked_at']<b['checked_at']
   assert b['coupon_price'] is None

def test_current_and_historical_coupon_are_not_merged_in_reply():
 raw={'reply':{'status':'answered','topic':'purchase','answer':'가격','sources':[],'cards':[],'missing_fields':[]}}
 reply=verified_result(raw,[lookup_product_features(['WD721RH','WD721RE'])]).reply
 values={c.data.model_id:c.data.purchase_benefits for c in reply.cards}
 assert values['WD721RH'].member_price==2089000
 assert values['WD721RH'].coupon_price is None
 assert values['WD721RH'].historical_coupon.coupon_discount==120000
