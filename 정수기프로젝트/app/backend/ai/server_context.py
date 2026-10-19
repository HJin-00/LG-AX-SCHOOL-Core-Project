"""서버 기준일. 고객 입력으로 평가 기준일을 변경하지 않습니다."""
import os
from datetime import datetime, date
from zoneinfo import ZoneInfo

def reference_date():
    fixed = os.environ.get('EVALUATION_REFERENCE_DATE', '').strip()
    return date.fromisoformat(fixed).isoformat() if fixed else datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
