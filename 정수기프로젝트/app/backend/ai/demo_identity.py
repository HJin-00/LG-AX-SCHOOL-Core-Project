"""본인확인 흐름 시연. 신원을 증명하는 인증 서비스가 아니며 실제 고객정보에 사용 금지."""
import time
from .schemas import Model
from typing import Literal


class DemoIdentityRequest(Model):
    claimed_demo_customer_id: str
    outcome: Literal['success', 'failure'] = 'success'


class DemoIdentityStore:
    def __init__(self, clock=time.monotonic, ttl=600):
        self.clock, self.ttl = clock, ttl
        self.records = {}

    def clear(self, session_id):
        self.records.pop(session_id, None)

    def verify(self, session_id, selected_customer, claimed_customer, outcome):
        self.clear(session_id)
        if outcome != 'success': return 'DEMO_IDENTITY_FAILED'
        if selected_customer != claimed_customer: return 'DEMO_OWNER_MISMATCH'
        self.records = {k:v for k,v in self.records.items() if v[1] > self.clock()}
        if len(self.records) >= 1000: return 'DEMO_IDENTITY_CAPACITY'
        self.records[session_id] = (selected_customer, self.clock()+self.ttl)
        return None

    def valid(self, session_id, customer):
        r = self.records.get(session_id)
        return bool(r and r[0] == customer and r[1] > self.clock())


class InstallationEstimateRequest(Model):
    model_id: Literal['WD520VCT', 'WU923AWB']
    surface_material: Literal['artificial','natural','ceramic','unknown'] = 'unknown'
    drilling_needed: Literal['yes','no','unknown'] = 'unknown'
    pump_needed: Literal['yes','no','unknown'] = 'unknown'
    breaker_needed: Literal['yes','no','unknown'] = 'unknown'
    outlet_needed: Literal['yes','no','unknown'] = 'unknown'
    external_outlet_drilling: Literal['yes','no','unknown'] = 'unknown'
    external_water_drilling: Literal['yes','no','unknown'] = 'unknown'
    thick_sink: Literal['yes','no','unknown'] = 'unknown'
