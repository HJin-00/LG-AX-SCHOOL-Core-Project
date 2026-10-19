"""공개 원본에서 인사이트 리포트의 상담 추이와 그래프를 재현한다.

실행: python 분석_재현.py
필요 패키지: pandas, pillow
원본 CSV는 읽기만 하며, 같은 폴더에 PNG 두 개를 만든다.
"""

from pathlib import Path
import re

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
ROOT = next(path for path in HERE.parents if (path / "핵심프로젝트.md").exists())
GRAPH = HERE.parent / "그래프"
GRAPH.mkdir(exist_ok=True)
RAW = HERE.parent / "자료" / "원본"
MONTHLY = RAW / "품목별상담_월별"
QA = RAW / "표준답변" / "소비자상담_표준답변_20250725.csv"
FONT = str(ROOT / "02_팀공유_실행용/정수기프로젝트/app/mcp/assets/fonts/NanumGothic-Regular.ttf")


def read_csv(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "cp949"):
        try:
            frame = pd.read_csv(path, encoding=encoding, dtype=str)
            frame.columns = frame.columns.str.strip()
            return frame.map(lambda x: x.strip() if isinstance(x, str) else x)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"인코딩 확인 필요: {path}")


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size)


def monthly_data() -> pd.DataFrame:
    paths = sorted(MONTHLY.glob("품목별_상담현황_*.csv"))
    assert len(paths) == 13, f"월별 원본은 13개여야 함: {len(paths)}"
    required = ["연도", "월", "품목명", "상담건수", "전월대비 증감률", "전년동월대비 증감률"]
    frames = []
    for path in paths:
        frame = read_csv(path)
        assert len(frame) == 500, f"500행 확인 필요: {path.name}"
        assert list(frame.columns) == required, f"열 구조 확인 필요: {path.name}"
        assert not frame[required].isna().any().any(), f"결측 확인 필요: {path.name}"
        assert not frame[required].eq("").any().any(), f"공백 확인 필요: {path.name}"
        frame["연월"] = frame["연도"] + "-" + frame["월"].str.zfill(2)
        assert frame["연월"].nunique() == 1, f"파일 내 기준월 혼합: {path.name}"
        assert frame["연월"].iloc[0].replace("-", "") == re.search(r"_(\d{6})\d{2}\.csv$", path.name).group(1)
        frame["상담건수"] = pd.to_numeric(frame["상담건수"], errors="raise")
        assert (frame["상담건수"] % 1 == 0).all(), f"소수 건수 확인 필요: {path.name}"
        frame["원본파일"] = path.name
        frames.append(frame)
    all_rows = pd.concat(frames, ignore_index=True)
    assert sorted(all_rows["연월"].unique()) == [str(p)[:7] for p in pd.period_range("2025-07", "2026-07", freq="M")]
    assert not all_rows.duplicated(["연월", "품목명"]).any()
    assert (all_rows["상담건수"] >= 0).all()
    return all_rows


def draw_trend(all_rows: pd.DataFrame) -> None:
    names = ["정수기대여(렌트)", "냉장고", "TV"]
    series = all_rows[all_rows["품목명"].isin(names)].pivot(
        index="연월", columns="품목명", values="상담건수"
    )
    assert series.notna().all().all()
    width, height = 1280, 650
    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    draw.text((72, 32), "월별 소비자상담 건수", font=font(34), fill="#17212f")
    draw.text((72, 82), "1372 품목별 상위 500개 자료 · 각 품목은 별도 분류 · 2025.07–2026.07", font=font(20), fill="#5c6675")
    left, top, right, bottom = 94, 150, 1218, 534
    for value in (0, 200, 400, 600, 800):
        y = bottom - (value / 800) * (bottom - top)
        draw.line((left, y, right, y), fill="#dce3eb", width=1)
        draw.text((30, y - 11), str(value), font=font(17), fill="#566171")
    colors = {"정수기대여(렌트)": "#b32045", "냉장고": "#2b7295", "TV": "#64748b"}
    for name in names:
        vals = series[name].tolist()
        pts = [
            (left + i * (right - left) / 12, bottom - (v / 800) * (bottom - top))
            for i, v in enumerate(vals)
        ]
        draw.line(pts, fill=colors[name], width=4, joint="curve")
        for x, y in pts:
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=colors[name])
    for i, month in enumerate(series.index):
        x = left + i * (right - left) / 12
        draw.text((x - 27, bottom + 17), month[2:].replace("-", "."), font=font(15), fill="#566171")
    x = 84
    for name in names:
        draw.line((x, 606, x + 30, 606), fill=colors[name], width=5)
        draw.text((x + 40, 591), name, font=font(19), fill="#17212f")
        x += 300 if name == names[0] else 220
    image.save(GRAPH / "그래프_13개월_상담추이.png")


def draw_categories(qa: pd.DataFrame) -> None:
    purifier = qa[qa["품목명"].eq("정수기대여")].copy()
    categories = purifier["구분"].str.split("_").str[0].value_counts()
    assert len(purifier) == 43 and int(categories.sum()) == 43
    width, height = 1120, 680
    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    draw.text((60, 30), "정수기대여 표준답변의 문서 구성", font=font(34), fill="#17212f")
    draw.text((60, 82), "43행 · 원본 ‘구분’의 첫 항목 기준 · 실제 상담 유형별 빈도가 아님", font=font(20), fill="#a11b3b")
    left, top, max_width, row_h = 305, 145, 670, 61
    for i, (name, count) in enumerate(categories.items()):
        y = top + i * row_h
        draw.text((60, y + 7), name, font=font(21), fill="#17212f")
        draw.rounded_rectangle((left, y, left + max_width * count / 12, y + 36), radius=6, fill="#b32045")
        draw.text((left + max_width * count / 12 + 12, y + 7), str(count), font=font(21), fill="#17212f")
    draw.text((60, 632), "원본: 한국소비자원 소비자상담 표준답변(2025-07-25)", font=font(17), fill="#5c6675")
    image.save(GRAPH / "그래프_표준답변_문서구성.png")


if __name__ == "__main__":
    all_rows = monthly_data()
    qa = read_csv(QA)
    assert len(qa) == 1332 and not qa.isna().any().any()
    draw_trend(all_rows)
    draw_categories(qa)
    monthly = all_rows[all_rows["품목명"].eq("정수기대여(렌트)")].sort_values("연월")
    monthly_counts = monthly.set_index("연월")["상담건수"]
    print(f"월별 파일 13개, 총 행 {len(all_rows):,}개 확인")
    print(f"정수기대여 13개월 합계 {monthly['상담건수'].sum():,}건")
    print(f"2026-07 전월 대비 재계산 {(monthly_counts['2026-07'] / monthly_counts['2026-06'] - 1) * 100:+.1f}%")
    print("그래프 2개 생성 완료")
