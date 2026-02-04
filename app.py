import json
import re
import streamlit as st
from openai import OpenAI

# =====================
# 기본 설정
# =====================
client = OpenAI()

st.set_page_config(page_title="SOAP Note AI - Student", layout="centered")
st.title("SOAP 노트 작성 도우미 (실습생 제출용)")
st.write("S / O 입력 → 제출용 A / P 자동 생성")

body_part = st.text_input("부위 (선택, 예: 어깨 / 무릎 / 허리)", value="")
s_input = st.text_area("S (Subjective)", height=160)
o_input = st.text_area("O (Objective)", height=160)

# =====================
# AI: 정보만 JSON으로 추출
# =====================
def extract_json(part, s_text, o_text):
    part_line = f"부위: {part}\n" if part else ""
    prompt = f"""
아래 S/O에서 핵심 정보만 추출해 JSON만 출력해라.

규칙:
- 문장 생성 금지, 정보 추출만
- 입력에 없는 신체부위/검사/진단 추가 금지
- '빈 문자열', '없음' 같은 표현 절대 사용 금지
- 값이 없으면 "" 또는 false

JSON 형식:
{{
  "part": "",
  "pain_present": true/false,
  "aggravating": "",
  "functional_limit": "",
  "rom_limited": true/false,
  "pain_on_motion": true/false,
  "other_objective": ""
}}

{part_line}S:
{s_text}

O:
{o_text}
""".strip()

    resp = client.responses.create(
        model="gpt-4o-mini",
        input=prompt,
        temperature=0.0
    )

    text = resp.output_text or ""
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}

    try:
        return json.loads(match.group())
    except Exception:
        return {}

# =====================
# 값 정리 함수
# =====================
def clean(x):
    if not x:
        return ""
    if isinstance(x, bool):
        return ""
    x = str(x).strip()
    if x in ["빈 문자열", "없음", "null"]:
        return ""
    return x

# =====================
# 제출용 A / P 생성 (템플릿)
# =====================
def build_ap(info):
    part = clean(info.get("part")) or body_part or "해당 부위"

    aggravating = clean(info.get("aggravating"))
    functional = clean(info.get("functional_limit"))
    other_obj = clean(info.get("other_objective"))

    pain_on_motion = info.get("pain_on_motion", False)
    rom_limited = info.get("rom_limited", False)

    # ---- A (2문장 고정) ----
    a1 = f"{part} 통증으로 기능적 움직임 수행에 제한이 있는 양상이다."

    details = []
    if pain_on_motion:
        details.append("움직임 시 통증 반응이 관찰됨")
    if rom_limited:
        details.append("가동범위 제한이 동반됨")

    if other_obj and other_obj not in details:
        details.append(other_obj)

    a2 = ", ".join(details)

    tails = []
    if aggravating:
        tails.append(f"통증은 '{aggravating}'에서 악화되는 경향이 있다")
    if functional:
        tails.append(f"일상 기능에서는 '{functional}'과 관련된 제한이 예상된다")

    if tails:
        a2 += "; " + ". ".join(tails)

    A = f"{a1} {a2}."

    # ---- P (항상 동일한 안전 템플릿) ----
    P = [
        f"- {part}의 통증 허용 범위 내에서 ROM(가동범위) 운동을 시행한다.",
        f"- {part} 기능 회복을 위한 근력 강화 운동을 적용한다.",
        "- 통증 반응에 따라 운동 강도 및 범위를 단계적으로 조절한다.",
        "- 일상생활 중 통증 유발 동작에 대한 주의사항 및 자가관리 교육을 제공한다."
    ]

    return "A:\n" + A + "\n\nP:\n" + "\n".join(P)

# =====================
# 실행 버튼
# =====================
if st.button("A / P 생성"):
    if not s_input.strip() or not o_input.strip():
        st.warning("S와 O를 모두 입력하세요.")
    else:
        info = extract_json(body_part, s_input, o_input)
        result = build_ap(info)
        st.subheader("제출용 A / P")
        st.code(result)
