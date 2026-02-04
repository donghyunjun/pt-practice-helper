import json
import re
import streamlit as st
from openai import OpenAI

client = OpenAI()

st.set_page_config(page_title="PT 실습 SOAP/Plan 도우미", layout="centered")
st.title("PT 실습 SOAP + Plan 도우미 (제출용/상세플랜)")
st.caption("주의: 본 도구는 학습/실습 기록 작성 보조용입니다. 임상 처방·의학적 판단을 대체하지 않습니다.")

mode = st.radio("출력 모드", ["제출용(깔끔/무난)", "상세 플랜(구체/전문)"], horizontal=True)

st.divider()

body_part = st.text_input("부위(선택, 예: 어깨/무릎/요추)", value="")
s_input = st.text_area("S (Subjective) - 환자 호소/악화요인/기능불편", height=140)
o_input = st.text_area("O (Objective) - 관찰/ROM/통증반응/검사소견", height=140)

st.divider()
st.subheader("Plan 구체화를 위한 추가 정보(체크/선택)")

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

st.divider()

# ---------- AI: S/O에서 '핵심요약'과 '악화요인'만 추출 (문장 생성 최소화) ----------
def extract_json(part, s_text, o_text):
    part_line = f"부위: {part}\n" if part else ""
    prompt = f"""
너는 물리치료 실습 기록을 돕는다.
아래 S/O에서 '정보만' 추출해 JSON만 출력하라. 문장 생성/추측 금지.
입력에 없는 검사/진단/치료는 추가하지 마라.
값이 없으면 "" 또는 false.

반드시 아래 키만 포함:
{{
  "part": "",
  "subjective_summary": "",
  "aggravating": "",
  "functional_limit": "",
  "objective_summary": "",
  "rom_limited": true/false,
  "pain_on_motion": true/false
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
    text = (resp.output_text or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
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

def dose_by_irritability(irrit):
    # 세트/반복 가이드 (안전한 범위, 과도한 단정 금지)
    if irrit == "높음":
        return {"sets": "1-2", "reps": "6-8", "rest": "60-90초", "tempo": "천천히", "note": "통증 허용 범위 내, 증상 악화 시 즉시 강도↓"}
    if irrit == "중간":
        return {"sets": "2-3", "reps": "8-12", "rest": "45-60초", "tempo": "통제된 속도", "note": "통증 0~3/10 범위, 다음날 통증 증가 시 강도↓"}
    if irrit == "낮음":
        return {"sets": "3-4", "reps": "10-15", "rest": "30-60초", "tempo": "통제된 속도", "note": "기능 목표 중심, 단계적 부하 증가"}
    return {"sets": "2-3", "reps": "8-12", "rest": "45-60초", "tempo": "통제된 속도", "note": "과도한 통증 유발 금지"}

def build_assessment(info, part_fallback):
    part = clean(info.get("part")) or part_fallback or "해당 부위"
    subj = clean(info.get("subjective_summary"))
    obj = clean(info.get("objective_summary"))
    aggrav = clean(info.get("aggravating"))
    func = clean(info.get("functional_limit"))

    base = f"{part} 통증/불편감으로 기능적 움직임 수행에 제한이 있는 양상이다."
    details = []

    if obj:
        details.append(obj)
    if aggrav:
        details.append(f"통증은 '{aggrav}'에서 악화되는 경향이 있다")
    if func:
        details.append(f"기능적으로는 '{func}' 관련 불편이 보고된다")

    if not details and subj:
        details.append(subj)

    if details:
        return base + " " + "; ".join(details) + "."
    return base

def plan_blocks(part, dose, impair, goals, precautions_list):
    # 규칙 기반으로 '항목+용량+진행기준'을 구성 (선택된 장애요인만 반영)
    blocks = []

    # 공통: 교육/자가관리
    edu = [
        "증상 유발 동작/자세를 확인하고, 통증을 줄이는 사용 패턴을 교육한다.",
        "자가관리: 온열/냉찜질은 상태에 따라 선택하되, 시행 후 증상 변화를 기록한다.",
    ]
    if "통증 감소" in goals:
        edu.append("통증은 0~3/10 범위에서 운동을 진행하고, 다음날 악화 시 강도를 낮춘다.")
    blocks.append(("교육/자가관리", edu))

    # ROM
    if "ROM 제한" in impair:
        blocks.append(("가동범위(ROM)", [
            f"{part}의 통증 허용 범위 내에서 ROM 운동을 시행한다.",
            f"용량: {dose['sets']}세트 × {dose['reps']}회, 휴식 {dose['rest']}, 속도 {dose['tempo']}.",
            "진행기준: 통증이 안정(또는 감소)되고 ROM이 증가하면 가동범위를 점진적으로 확대한다."
        ]))

    # 근력
    if "근력 저하" in impair:
        blocks.append(("근력강화", [
            f"{part} 관련 근력 강화 운동을 적용한다(저항은 단계적으로).",
            f"용량: {dose['sets']}세트 × {dose['reps']}회, 휴식 {dose['rest']}.",
            "진행기준: 동일 강도에서 통증 악화 없이 반복 수행 가능하면 저항 또는 반복수를 소폭 증가한다."
        ]))

    # 유연성/단축
    if "유연성/근육 단축" in impair:
        blocks.append(("유연성/스트레칭", [
            "단축/긴장된 연부조직을 대상으로 정적 스트레칭 또는 가벼운 가동성 운동을 포함한다.",
            "용량: 20-30초 유지 × 3-5회(통증 과도 유발 금지).",
            "진행기준: 당김 감소 및 가동범위 증가 시 유지시간/횟수를 점진적으로 증가한다."
        ]))

    # 관절 가동성
    if "관절 가동성 저하(강직)" in impair:
        blocks.append(("관절 가동성", [
            "관절 가동성 저하가 의심되면 가동성 회복을 위한 수동/능동 보조 움직임을 포함한다.",
            "용량: 짧은 범위 반복(통증 허용 범위 내), 단계적 확대.",
            "진행기준: 통증 반응이 안정적일 때 범위/반복을 점진적으로 늘린다."
        ]))

    # 자세/정렬
    if "자세/정렬 문제" in impair:
        blocks.append(("자세/움직임 패턴", [
            "통증을 유발하는 움직임 패턴을 확인하고, 중립 정렬/호흡/코어-견갑(해당 시) 등 기본 패턴을 교육한다.",
            "용량: 짧은 구간에서 정확도 우선(거울/피드백 활용).",
            "진행기준: 정확도가 올라가면 기능 동작(일상 동작)에 점진적으로 연결한다."
        ]))

    # 고유수용감각/균형
    if "고유수용감각/균형 저하" in impair:
        blocks.append(("균형/고유수용감각", [
            "안정된 환경 → 불안정 환경으로 단계적으로 진행하며 균형/고유수용감각 훈련을 포함한다.",
            "용량: 30-60초 유지 × 3-5세트(안전 확보).",
            "진행기준: 흔들림 감소/자세 유지 가능 시 난이도를 점진적으로 증가한다."
        ]))

    # 기능동작
    if "기능동작 제한(계단/보행/팔 들기 등)" in impair:
        blocks.append(("기능동작 훈련", [
            "문제 동작(계단/보행/팔 들기 등)을 작은 단위로 분해해 단계적으로 연습한다.",
            "용량: 짧은 반복(양질 우선) + 통증 모니터링.",
            "진행기준: 동작 질이 유지되면 범위/속도/반복을 점진적으로 증가한다."
        ]))

    # 신경학적 의심
    if "신경학적 증상 의심(저림/감각/근력저하 등)" in impair:
        blocks.append(("신경학적 주의", [
            "저림/감각 변화/근력 변화가 지속되면 담당자에게 즉시 공유하고, 증상 악화 유발 동작을 피한다.",
            "진행기준: 신경학적 증상이 안정적일 때만 운동 강도를 단계적으로 조절한다."
        ]))

    # 부종/염증
    if "부종/염증 소견" in impair:
        blocks.append(("부종/염증 관리", [
            "부종/염증 소견이 있으면 과부하를 피하고, 자세/활동 조절과 순환을 돕는 가벼운 운동을 포함한다.",
            "진행기준: 부종 감소 및 통증 안정 시 ROM/근력 훈련을 확대한다."
        ]))

    # 주의사항 반영(문구만)
    if precautions_list and "불명" not in precautions_list:
        blocks.append(("주의사항", [
            "다음 항목이 있는 경우 악화 여부를 우선 모니터링한다: " + ", ".join(precautions_list),
            "악화 시 강도를 낮추고, 필요 시 지도자/담당자와 상의한다."
        ]))

    return blocks

def format_plan(part, freq_choice, home_choice, follow_choice, dose, blocks):
    header = [
        f"- 치료 빈도(권장): {freq_choice}",
        f"- 자가운동 빈도(권장): {home_choice}",
        f"- 재평가/팔로업: {follow_choice}",
        f"- 용량 가이드: {dose['sets']}세트 × {dose['reps']}회, 휴식 {dose['rest']} ({dose['note']})"
    ]
    lines = ["P:", *[f"{h}" for h in header], ""]
    for title, items in blocks:
        lines.append(f"[{title}]")
        for it in items:
            lines.append(f"- {it}")
        lines.append("")
    return "\n".join(lines).strip()

# ---------- 실행 ----------
if st.button("A / P 생성"):
    if not s_input.strip() or not o_input.strip():
        st.warning("S와 O를 모두 입력하세요.")
        st.stop()

    info = extract_json(body_part, s_input, o_input)

    part = clean(info.get("part")) or body_part or "해당 부위"
    A_text = build_assessment(info, part)

    if mode == "제출용(깔끔/무난)":
        # 제출용은 간결 + 안전
        P_lines = [
            "P:",
            f"- {part}의 통증 허용 범위 내에서 ROM(가동범위) 운동을 시행한다.",
            f"- {part} 기능 회복을 위한 근력 강화 운동을 적용한다.",
            "- 통증 반응에 따라 운동 강도 및 범위를 단계적으로 조절한다.",
            "- 일상생활 중 통증 유발 동작에 대한 주의사항 및 자가관리 교육을 제공한다."
        ]
        output = "A:\n" + A_text + "\n\n" + "\n".join(P_lines)
        st.subheader("제출용 A / P")
        st.code(output)
    else:
        # 상세 플랜: 체크박스 기반 + 용량 + 진행기준 + 빈도 + 재평가
        dose = dose_by_irritability(irritability)
        blocks = plan_blocks(part, dose, impairments, goal_focus, precautions)
        output = "A:\n" + A_text + "\n\n" + format_plan(part, freq, home_freq, followup, dose, blocks)

        st.subheader("상세 플랜 A / P (학습/기록 보조용)")
        st.code(output)

        with st.expander("AI 추출(요약 JSON) 보기"):
            st.code(json.dumps(info, ensure_ascii=False, indent=2))
