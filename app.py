import json
import re
import streamlit as st
from openai import OpenAI

client = OpenAI()

st.set_page_config(page_title="PT SOAP 도우미 (실습생)", layout="centered")
st.title("PT SOAP 도우미 (실습생용)")
st.caption("입력은 '사실'만. AI가 S/O 분류 + A/P 작성. (학습/기록 보조용)")

# -------------------------
# 출력 모드
# -------------------------
mode = st.radio("출력 모드", ["제출용(깔끔/무난)", "상세 플랜(구체/전문)"], horizontal=True)

# -------------------------
# 용어 변환(순우리말) 옵션
# -------------------------
st.divider()
st.subheader("용어 출력 설정(선택)")
use_pure_korean = st.toggle("해부학/운동학 용어를 순우리말로 변환해서 출력", value=True)

with st.expander("기본 용어 변환표(수정/추가 가능)"):
    st.write("형식: `기존용어 -> 순우리말` (한 줄에 하나)")
    default_glossary = """\
대퇴사두근 -> 넙다리네갈래근
햄스트링 -> 넙다리뒤근육
대둔근 -> 큰볼기근
중둔근 -> 볼기중간근
소둔근 -> 볼기작은근
장요근 -> 엉덩허리근
비복근 -> 장딴지근
가자미근 -> 가자미근
전경골근 -> 앞정강근
상완이두근 -> 위팔두갈래근
상완삼두근 -> 위팔세갈래근
삼각근 -> 어깨세모근
견갑골 -> 어깨뼈
쇄골 -> 빗장뼈
대퇴골 -> 넙다리뼈
경골 -> 정강뼈
비골 -> 종아리뼈
요추 -> 허리뼈
경추 -> 목뼈
흉추 -> 등뼈
외전 -> 벌림
내전 -> 모음
굴곡 -> 굽힘
신전 -> 폄
외회전 -> 바깥돌림
내회전 -> 안쪽돌림
회내 -> 엎침
회외 -> 뒤침
"""
    glossary_text = st.text_area("용어 변환표", value=default_glossary, height=240)

def parse_glossary(text: str) -> dict:
    mapping = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "->" not in line:
            continue
        src, dst = line.split("->", 1)
        src, dst = src.strip(), dst.strip()
        if src and dst:
            mapping[src] = dst
    return mapping

GLOSSARY = parse_glossary(glossary_text)

def apply_glossary(s: str, mapping: dict) -> str:
    """긴 용어부터 치환해서 중첩/부분치환 문제를 줄임."""
    if not s or not mapping:
        return s
    # 길이 긴 키부터 적용
    for k in sorted(mapping.keys(), key=len, reverse=True):
        s = s.replace(k, mapping[k])
    return s

# -------------------------
# 입력: 실습생이 '사실'만 적는 구조
# -------------------------
st.divider()
st.subheader("입력(사실만 작성)")

body_part = st.text_input("부위(선택, 예: 어깨/무릎/허리)", value="")

patient_text = st.text_area(
    "환자 호소/상황(그냥 써도 됨)",
    height=140,
    placeholder="예) 어깨가 아파요. 팔을 들 때 더 아파요. 밤에는 덜해요."
)

observer_text = st.text_area(
    "내 관찰/평가(그냥 써도 됨)",
    height=140,
    placeholder="예) 팔 들어 올릴 때 통증 반응. 가동범위 제한. 움직임 느림."
)

# -------------------------
# 상세 플랜 구체화 옵션(기존 상세플랜 로직 유지)
# -------------------------
st.divider()
st.subheader("상세 플랜 구체화(선택)")

colA, colB = st.columns(2)
with colA:
    pain_level = st.select_slider("통증 강도(주관적)", options=["없음", "경미", "중등도", "심함"], value="중등도")
    stage = st.selectbox("상태 단계(대략)", ["급성/초기", "아급성", "만성/회복기", "불명"], index=3)
    irritability = st.selectbox("자극 민감도(대략)", ["낮음", "중간", "높음", "불명"], index=3)

with colB:
    freq = st.selectbox("치료/운동 빈도(권장값 선택)", ["주 2회", "주 3회", "주 1회", "불명"], index=0)
    home_freq = st.selectbox("자가운동 빈도(권장값 선택)", ["매일", "주 5-6회", "주 3-4회", "불명"], index=1)
    followup = st.selectbox("재평가/팔로업", ["1주", "2주", "3-4주", "불명"], index=1)

impairments = st.multiselect(
    "장애요인(관찰/평가 기반으로 선택) — 선택한 것만 Plan에 반영됨",
    [
        "ROM 제한", "근력 저하", "통증으로 인한 움직임 회피/경직",
        "자세/정렬 문제", "유연성/근육 단축", "관절 가동성 저하(강직)",
        "고유수용감각/균형 저하", "기능동작 제한(계단/보행/팔 들기 등)",
        "신경학적 증상 의심(저림/감각/근력저하 등)", "부종/염증 소견"
    ]
)

precautions = st.multiselect(
    "주의/금기(해당 시 선택)",
    ["야간통/안정시 심한 통증", "저림/감각저하", "현저한 근력저하", "발열/전신증상", "외상 후 악화", "불명"]
)

goal_focus = st.multiselect(
    "이번 1~2주 목표(선택)",
    ["통증 감소", "ROM 회복", "근력 회복", "기능동작 개선", "자세/사용패턴 교정", "자가관리 교육"]
)

# -------------------------
# AI 호출 유틸
# -------------------------
def call_model_json(prompt: str) -> dict:
    resp = client.responses.create(
        model="gpt-4o-mini",
        input=prompt,
        temperature=0.0
    )
    txt = (resp.output_text or "").strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}

def clean(x):
    if not x:
        return ""
    if isinstance(x, bool):
        return ""
    x = str(x).strip()
    if x in ["빈 문자열", "없음", "null"]:
        return ""
    return x

# -------------------------
# 1) S/O 자동 분류 프롬프트(핵심)
# -------------------------
def classify_to_SO(part: str, patient: str, observer: str) -> dict:
    part_line = f"부위: {part}\n" if part.strip() else ""
    prompt = f"""
너는 물리치료 실습 SOAP 작성 보조자다.
아래 입력을 S(주관)와 O(객관)로 '분류/정리'만 하라.
- 입력에 없는 정보 추가(추측) 금지
- 진단명/검사명/치료법 새로 만들기 금지
- 문장은 짧고 자연스러운 한국어로(과장 금지)
- 없으면 빈 문자열 "" 로 둔다

JSON만 출력:
{{
  "part": "",
  "S": "",
  "O": ""
}}

{part_line}
[환자 호소/상황]
{patient}

[실습생 관찰/평가]
{observer}
""".strip()
    return call_model_json(prompt)

# -------------------------
# 2) S/O 기반 핵심정보 추출(기존 안정성 유지)
# -------------------------
def extract_core(part: str, S: str, O: str) -> dict:
    part_line = f"부위: {part}\n" if part.strip() else ""
    prompt = f"""
너는 물리치료 실습 기록을 돕는다.
아래 S/O에서 '정보만' 추출해 JSON만 출력하라. 추측 금지.
값이 없으면 "" 또는 false.

반드시 아래 키만 포함:
{{
  "part": "",
  "aggravating": "",
  "functional_limit": "",
  "objective_summary": "",
  "rom_limited": true/false,
  "pain_on_motion": true/false
}}

{part_line}S:
{S}

O:
{O}
""".strip()
    return call_model_json(prompt)

def dose_by_irritability(irrit):
    if irrit == "높음":
        return {"sets": "1-2", "reps": "6-8", "rest": "60-90초", "tempo": "천천히", "note": "통증 허용 범위 내, 악화 시 강도↓"}
    if irrit == "중간":
        return {"sets": "2-3", "reps": "8-12", "rest": "45-60초", "tempo": "통제된 속도", "note": "통증 0~3/10, 다음날 악화 시 강도↓"}
    if irrit == "낮음":
        return {"sets": "3-4", "reps": "10-15", "rest": "30-60초", "tempo": "통제된 속도", "note": "기능 목표 중심, 단계적 부하 증가"}
    return {"sets": "2-3", "reps": "8-12", "rest": "45-60초", "tempo": "통제된 속도", "note": "과도한 통증 유발 금지"}

def build_assessment(part: str, info: dict) -> str:
    aggrav = clean(info.get("aggravating"))
    func = clean(info.get("functional_limit"))
    obj = clean(info.get("objective_summary"))

    base = f"{part} 통증/불편감으로 기능적 움직임 수행에 제한이 있는 양상이다."
    details = []
    if obj:
        details.append(obj)
    if aggrav:
        details.append(f"통증은 '{aggrav}'에서 악화되는 경향이 있다")
    if func:
        details.append(f"기능적으로는 '{func}' 관련 불편이 보고된다")

    if details:
        return base + " " + "; ".join(details) + "."
    return base

def plan_blocks(part, dose, impair, goals, precautions_list):
    blocks = []
    edu = [
        "증상 유발 동작/자세를 확인하고, 통증을 줄이는 사용 패턴을 교육한다.",
        "자가관리: 상태에 따라 온열/냉찜질을 선택하고, 시행 후 증상 변화를 기록한다.",
    ]
    if "통증 감소" in goals:
        edu.append("통증은 0~3/10 범위에서 운동을 진행하고, 다음날 악화 시 강도를 낮춘다.")
    blocks.append(("교육/자가관리", edu))

    if "ROM 제한" in impair:
        blocks.append(("가동범위(ROM)", [
            f"{part}의 통증 허용 범위 내에서 ROM 운동을 시행한다.",
            f"용량: {dose['sets']}세트 × {dose['reps']}회, 휴식 {dose['rest']}, 속도 {dose['tempo']}.",
            "진행기준: 통증이 안정(또는 감소)되고 ROM이 증가하면 가동범위를 점진적으로 확대한다."
        ]))
    if "근력 저하" in impair:
        blocks.append(("근력강화", [
            f"{part} 관련 근력 강화 운동을 적용한다(저항은 단계적으로).",
            f"용량: {dose['sets']}세트 × {dose['reps']}회, 휴식 {dose['rest']}.",
            "진행기준: 통증 악화 없이 반복 수행 가능하면 저항 또는 반복수를 소폭 증가한다."
        ]))
    if "유연성/근육 단축" in impair:
        blocks.append(("유연성/스트레칭", [
            "단축/긴장된 연부조직을 대상으로 정적 스트레칭 또는 가벼운 가동성 운동을 포함한다.",
            "용량: 20-30초 유지 × 3-5회(통증 과도 유발 금지).",
            "진행기준: 당김 감소 및 가동범위 증가 시 유지시간/횟수를 점진적으로 증가한다."
        ]))
    if "관절 가동성 저하(강직)" in impair:
        blocks.append(("관절 가동성", [
            "가동성 저하가 의심되면 수동/능동 보조 움직임을 포함한다.",
            "용량: 짧은 범위 반복(통증 허용 범위 내), 단계적 확대.",
            "진행기준: 통증 반응이 안정적일 때 범위/반복을 점진적으로 늘린다."
        ]))
    if "자세/정렬 문제" in impair:
        blocks.append(("자세/움직임 패턴", [
            "통증을 유발하는 움직임 패턴을 확인하고, 중립 정렬/호흡/기본 패턴을 교육한다.",
            "용량: 정확도 우선(피드백 활용).",
            "진행기준: 정확도가 올라가면 기능 동작에 점진적으로 연결한다."
        ]))
    if "고유수용감각/균형 저하" in impair:
        blocks.append(("균형/고유수용감각", [
            "안정된 환경 → 불안정 환경으로 단계적으로 진행하며 균형 훈련을 포함한다.",
            "용량: 30-60초 유지 × 3-5세트(안전 확보).",
            "진행기준: 흔들림 감소 시 난이도를 점진적으로 증가한다."
        ]))
    if "기능동작 제한(계단/보행/팔 들기 등)" in impair:
        blocks.append(("기능동작 훈련", [
            "문제 동작을 작은 단위로 분해해 단계적으로 연습한다.",
            "용량: 짧은 반복(질 우선) + 통증 모니터링.",
            "진행기준: 동작 질이 유지되면 범위/속도/반복을 점진적으로 증가한다."
        ]))
    if "신경학적 증상 의심(저림/감각/근력저하 등)" in impair:
        blocks.append(("신경학적 주의", [
            "저림/감각 변화/근력 변화가 지속되면 지도자/담당자에게 즉시 공유한다.",
            "악화 유발 동작을 피하고, 증상이 안정적일 때만 강도를 단계적으로 조절한다."
        ]))
    if "부종/염증 소견" in impair:
        blocks.append(("부종/염증 관리", [
            "부종/염증 소견이 있으면 과부하를 피하고 순환을 돕는 가벼운 운동을 포함한다.",
            "진행기준: 부종 감소 및 통증 안정 시 ROM/근력 훈련을 확대한다."
        ]))

    if precautions_list and "불명" not in precautions_list:
        blocks.append(("주의사항", [
            "다음 항목이 있는 경우 악화 여부를 우선 모니터링한다: " + ", ".join(precautions_list),
            "악화 시 강도를 낮추고 필요 시 상의한다."
        ]))

    return blocks

def format_plan(freq_choice, home_choice, follow_choice, dose, blocks):
    header = [
        f"- 치료/운동 빈도(권장): {freq_choice}",
        f"- 자가운동 빈도(권장): {home_choice}",
        f"- 재평가/팔로업: {follow_choice}",
        f"- 용량 가이드: {dose['sets']}세트 × {dose['reps']}회, 휴식 {dose['rest']} ({dose['note']})"
    ]
    lines = ["P:", *header, ""]
    for title, items in blocks:
        lines.append(f"[{title}]")
        for it in items:
            lines.append(f"- {it}")
        lines.append("")
    return "\n".join(lines).strip()

# -------------------------
# 실행
# -------------------------
if st.button("S/O 자동 분류 + A/P 생성"):
    if not patient_text.strip() and not observer_text.strip():
        st.warning("최소한 '환자 호소/상황' 또는 '내 관찰/평가' 중 하나는 입력하세요.")
        st.stop()

    so = classify_to_SO(body_part, patient_text, observer_text)
    part = clean(so.get("part")) or body_part or "해당 부위"
    S = clean(so.get("S"))
    O = clean(so.get("O"))

    st.subheader("AI 분류 결과(S/O)")
    st.code(f"S:\n{S}\n\nO:\n{O}")

    core = extract_core(part, S, O)
    part2 = clean(core.get("part")) or part

    A_text = build_assessment(part2, core)

    if mode == "제출용(깔끔/무난)":
        P_lines = [
            "P:",
            f"- {part2}의 통증 허용 범위 내에서 ROM(가동범위) 운동을 시행한다.",
            f"- {part2} 기능 회복을 위한 근력 강화 운동을 적용한다.",
            "- 통증 반응에 따라 운동 강도 및 범위를 단계적으로 조절한다.",
            "- 일상생활 중 통증 유발 동작에 대한 주의사항 및 자가관리 교육을 제공한다."
        ]
        output = "A:\n" + A_text + "\n\n" + "\n".join(P_lines)
    else:
        dose = dose_by_irritability(irritability)
        blocks = plan_blocks(part2, dose, impairments, goal_focus, precautions)
        output = "A:\n" + A_text + "\n\n" + format_plan(freq, home_freq, followup, dose, blocks)

    if use_pure_korean:
        output = apply_glossary(output, GLOSSARY)
        S_out = apply_glossary(S, GLOSSARY)
        O_out = apply_glossary(O, GLOSSARY)
    else:
        S_out, O_out = S, O

    st.subheader("최종 출력(제출/학습용)")
    st.code(output)

    with st.expander("S/O (변환 적용본)"):
        st.code(f"S:\n{S_out}\n\nO:\n{O_out}")

    with st.expander("AI 추출(핵심 JSON) 보기"):
        st.code(json.dumps(core, ensure_ascii=False, indent=2))
