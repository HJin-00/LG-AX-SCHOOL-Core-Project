"""고객용 상담 준비서 PDF. 한글 폰트 포함, 원문을 마크업으로 실행하지 않음."""
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
from reportlab.lib.pagesizes import A4


def write_brief_pdf(target, summary, facts, questions, sources):
    font='BriefKorean'
    if font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font,str(Path(__file__).parent/'assets/fonts/NanumGothic-Regular.ttf')))
    styles={
        'title':ParagraphStyle('title',fontName=font,fontSize=23,leading=32,textColor=colors.HexColor('#A50034'),spaceAfter=14,wordWrap='CJK'),
        'head':ParagraphStyle('head',fontName=font,fontSize=13,leading=20,textColor=colors.HexColor('#A50034'),spaceBefore=18,spaceAfter=8,keepWithNext=True,wordWrap='CJK'),
        'body':ParagraphStyle('body',fontName=font,fontSize=10,leading=17,spaceAfter=7,wordWrap='CJK'),
        'small':ParagraphStyle('small',fontName=font,fontSize=8,leading=13,textColor=colors.HexColor('#666666'),spaceAfter=6,wordWrap='CJK'),
    }
    def para(text,kind='body'):
        return Paragraph(escape(str(text)).replace('\n','<br/>'),styles[kind])
    story=[para('정수기 상담 준비서','title'),para('상담 전 확인한 내용과 질문을 한눈에 정리했어요.'),para('고객이 활용하는 문서입니다. 상담사에게 자동 전달되지 않습니다.','small')]
    story += [para('01  상담을 시작할 때 이렇게 말하세요','head'),para(summary)]
    story.append(para('02  상담사에게 확인할 질문','head'))
    for i,q in enumerate(questions,1):story.append(para(f'{i}. {q}'))
    if not questions:story.append(para('현재 추가 확인 항목은 없습니다. 상담 조건이 달라지면 다시 확인하세요.'))
    story.append(para('03  지금까지 확인한 내용','head'))
    for fact in facts:
        if not fact.startswith('[상세] '):story.append(para('- '+fact))
    details=[f.removeprefix('[상세] ') for f in facts if f.startswith('[상세] ')]
    if details:
        story.append(para('계산 기준과 상세 내역','head'))
        story.extend(para('- '+f,'small') for f in details)
    story += [para('04  다음 행동','head'),para('질문 목록을 상담 시 확인하고, 계약 변경 전에는 계약서와 최종 견적을 함께 확인하세요.'),para('자료 기준','head')]
    story.extend(para(s,'small') for s in sources)
    story.append(para('가상 계약·비용을 사용하는 시연 결과입니다. 실제 LG 계약·요금 확정, 해지 신청 또는 상담 접수는 진행되지 않았습니다.','small'))
    def page(canvas,doc):
        canvas.saveState();canvas.setStrokeColor(colors.HexColor('#E8DDE1'));canvas.line(42,42,A4[0]-42,42);canvas.setFont(font,8);canvas.setFillColor(colors.HexColor('#777777'));canvas.drawString(42,28,'정수기 계약 상담 | 고객용 준비서');canvas.drawRightString(A4[0]-42,28,str(doc.page));canvas.restoreState()
    SimpleDocTemplate(str(target),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=42,bottomMargin=56,title='정수기 상담 준비서',author='LG AX SCHOOL 4팀').build(story,onFirstPage=page,onLaterPages=page)
