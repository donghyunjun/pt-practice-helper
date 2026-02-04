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

default_glossary = """\
# 상지/어깨띠
삼각근 -> 어깨세모근
상완이두근 -> 위팔두갈래근
상완삼두근 -> 위팔세갈래근
상완근 -> 위팔근
오훼완근 -> 부리위팔근
회전근개 -> 돌림근띠
극상근 -> 가시위근
극하근 -> 가시아래근
소원근 -> 작은원근
견갑하근 -> 어깨밑근
대흉근 -> 큰가슴근
소흉근 -> 작은가슴근
전거근 -> 앞톱니근
승모근 -> 등세모근
광배근 -> 넓은등근
능형근 -> 마름근
견갑거근 -> 어깨올림근

# 전완/손
원회내근 -> 원엎침근
방형회내근 -> 네모엎침근
상완요골근 -> 위팔노근
요측수근신근 -> 노쪽손목폄근
척측수근신근 -> 자쪽손목폄근
요측수근굴근 -> 노쪽손목굽힘근
척측수근굴근 -> 자쪽손목굽힘근
장장근 -> 긴손바닥근
지신근 -> 손가락폄근
지굴근 -> 손가락굽힘근
장무지굴근 -> 긴엄지굽힘근
장무지외전근 -> 긴엄지벌림근

# 체간/코어
복직근 -> 배곧은근
복횡근 -> 배가로근
외복사근 -> 바깥배빗근
내복사근 -> 안쪽배빗근
척추기립근 -> 척주세움근
다열근 -> 여러갈래근
요방형근 -> 허리네모근

# 둔부/고관절
대둔근 -> 큰볼기근
중둔근 -> 볼기중간근
소둔근 -> 볼기작은근
장요근 -> 엉덩허리근
대퇴근막장근 -> 넙다리근막긴장근
이상근 -> 궁둥구멍근
폐쇄내근 -> 속폐쇄근
폐쇄외근 -> 바깥폐쇄근
대퇴사각근 -> 넙다리네모근

# 대퇴/무릎
대퇴사두근 -> 넙다리네갈래근
대퇴직근 -> 넙다리곧은근
외측광근 -> 가쪽넓은근
내측광근 -> 안쪽넓은근
중간광근 -> 중간넓은근
햄스트링 -> 넙다리뒤근육
대퇴이두근 -> 넙다리두갈래근
반건양근 -> 반힘줄근
반막양근 -> 반막근
봉공근 -> 넙다리빗근
박근 -> 두덩근
장내전근 -> 긴모음근
단내전근 -> 짧은모음근
대내전근 -> 큰모음근
박내전근 -> 얇은근

# 하퇴/발목/발
비복근 -> 장딴지근
가자미근 -> 가자미근
전경골근 -> 앞정강근
장지신근 -> 긴발가락폄근
장무지신근 -> 긴엄지폄근
장비골근 -> 긴종아리근
단비골근 -> 짧은종아리근
후경골근 -> 뒤정강근
장지굴근 -> 긴발가락굽힘근
장무지굴근 -> 긴엄지굽힘근

# 뼈
견갑골 -> 어깨뼈
쇄골 -> 빗장뼈
상완골 -> 위팔뼈
요골 -> 노뼈
척골 -> 자뼈
대퇴골 -> 넙다리뼈
경골 -> 정강뼈
비골 -> 종아리뼈

# 움직임(주의: 외전=벌림, 외회전=바깥돌림)
외전 -> 벌림
내전 -> 모음
굴곡 -> 굽힘
신전 -> 폄
외회전 -> 바깥돌림
내회전 -> 안쪽돌림
회내 -> 엎침
회외 -> 뒤침
"""

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

def apply_glossary(s: str, mapping: dict) -> str:
    if not s or not mapping:
        return s
    for k in sorted(mapping.keys(), key=len, reverse=True):
        s = s.replace(k, mapping[k])
    return s

with st.expander("용어 변환표(수정/추가 가능)"):
    glossary_text = st.text_area("기존용어 -> 순우리말", value=default_glossary, height=260)
GLOSSARY = parse_glossary(glossary_text)

# -------------------------
# 입력(사실만)
# -------------------------
st.divider()
st.subheader("입력(사실만 작성)")
body_part = st.text_input("부위(선택, 예: 어깨/무릎/허리)", value="")

patient_text = st.text_area(
    "환자 호소/상황(그냥 써도 됨)",
    height=120,
    placeholder="예) 어깨가 아파요. 팔을 들 때 더 아파요."
)
observer_text = st.text_area(
    "내 관찰/평가(그냥 써도 됨)",
    height=120,
    placeholder="예) 팔 들어 올릴 때 통증 반응. 가동범위 제한."
)

# -------------------------
# 상세 플랜 옵션
# -------------------------
st.divider()
st.subheader("상세 플랜 구체화(선택)")

colA, colB = st.columns(2)
with colA:
    pain_level = st.select_slider("통증 강도(주관적)", options=["없음", "경미", "중등도", "심함"], value="중등도")
    stage = st.selectbox("상태 단계(대략)", ["급성/초기", "아급성", "만성/회복기", "불명"], index=3)
    irritability = st.selectbox("자극 민감도(대략)", ["낮음", "중간", "높음", "불명"], index=3)

with colB:
    freq = st.selectbox("치료/운동 빈도(권장)", ["주 2회", "주 3회", "주 1회", "불명"], index=0)
    home_freq = st.selectbox("자가운동 빈도(권장)", ["매일", "주 5-6회", "주 3-4회", "불명"], index=1)
    followup = st.selectbox("재평가/팔로업", ["1주", "2주", "3-4주", "불명"], index=1)

impairments = st.multiselect(
    "장애요인(선택한 것만 Plan에 반영)",
    ["ROM 제한", "근력 저하", "유연성/근육 단축", "기능동작 제한", "자세/정렬 문제", "고유수용감각/균형 저하"]
)

# -------------------------
# AI: S/O 자동 분류 & 핵심 추출
# -------------------------
def call_model_json(prompt: str) -> dict:
    resp = client.responses.create(model="gpt-4o-mini", input=prompt, temperature=0.0)
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

def classify_to_SO(part: str, patient: str, observer: str) -> dict:
    part_line = f"부위: {part}\n" if part.strip() else ""
    prompt = f"""
너는 물리치료 실습 SOAP 작성 보조자다.
아래 입력을 S(주관)와 O(객관)로 분류/정리만 하라.
- 추측/추가 금지
- 진단명/검사명/치료법 새로 만들기 금지
- 문장은 짧고 자연스럽게
JSON만 출력:
{{"part":"","S":"","O":""}}
{part_line}
[환자 호소/상황]
{patient}
[실습생 관찰/평가]
{observer}
""".strip()
    return call_model_json(prompt)

def extract_core(part: str, S: str, O: str) -> dict:
    part_line = f"부위: {part}\n" if part.strip() else ""
    prompt = f"""
아래 S/O에서 정보만 추출해 JSON만 출력하라(추측 금지).
{{"part":"","aggravating":"","functional_limit":"","objective_summary":""}}
{part_line}
S:{S}
O:{O}
""".strip()
    return call_model_json(prompt)

# -------------------------
# “구체 운동 라이브러리(규칙 기반)”
# - 결제 가치의 핵심
# -------------------------
EXERCISE_LIBRARY = {
    "어깨": {
        "ROM 제한": [
            ("벽 타기(손으로 벽 따라 올리기)", "2-3세트 × 8-12회", "통증 허용 범위 내, 범위 점진 확대"),
            ("막대기/수건 보조 가동범위", "2-3세트 × 8-12회", "반동 없이 천천히"),
            ("펜듈럼(몸통 기울여 팔 흔들기)", "1-2세트 × 30-60초", "통증이 심하면 범위 축소")
        ],
        "근력 저하": [
            ("밴드 로우(당기기)", "2-4세트 × 8-15회", "견갑 안정 유지"),
            ("밴드 바깥돌림(팔꿈치 90도 고정)", "2-4세트 × 8-15회", "통증 0~3/10"),
            ("벽/무릎 팔굽혀펴기 또는 푸시업 플러스", "2-4세트 × 6-12회", "견갑 날개뼈 조절")
        ],
        "유연성/근육 단축": [
            ("가슴근 스트레칭(문틀)", "3-5회 × 20-30초", "어깨 앞쪽 과신전 주의"),
            ("상부승모근/견갑거근 스트레칭", "3-5회 × 20-30초", "저림 발생 시 중단")
        ],
        "기능동작 제한": [
            ("가벼운 물건 들기 패턴 연습(통증 없는 범위)", "2-3세트 × 6-10회", "동작 질 우선"),
            ("스캡션(30도 전방거상, 가벼운 저항)", "2-3세트 × 8-12회", "통증 허용 범위")
        ],
    },
    "무릎": {
        "ROM 제한": [
            ("힐 슬라이드(누워서 무릎 굽힘)", "2-3세트 × 10-15회", "통증 허용 범위"),
            ("무릎 폄 수건 받침(가벼운 폄 유지)", "3-5회 × 20-30초", "무리한 과폄 금지")
        ],
        "근력 저하": [
            ("쿼드셋(넙다리네갈래근 등척성 수축)", "2-4세트 × 8-12회(3-5초 유지)", "통증 허용 범위"),
            ("직거상(SLR)", "2-4세트 × 8-12회", "허리 과신전 주의"),
            ("미니스쿼트/의자 앉았다 일어서기", "2-4세트 × 6-12회", "무릎 안쪽 붕괴 주의")
        ],
        "기능동작 제한": [
            ("스텝업(낮은 발판)", "2-3세트 × 6-10회", "통증/정렬 체크"),
            ("계단 패턴 연습(작은 범위)", "2-3세트 × 6-10회", "동작 질 우선")
        ],
    },
    "허리": {
        "근력 저하": [
            ("맥길 컬업(변형 윗몸일으키기)", "2-4세트 × 6-10회(2-3초 유지)", "허리 꺾임 최소화"),
            ("버드독", "2-4세트 × 6-10회/측", "골반 흔들림 최소"),
            ("데드버그", "2-4세트 × 6-10회/측", "허리 뜨지 않게")
        ],
        "유연성/근육 단축": [
            ("고관절 굽힘근(엉덩허리근) 스트레칭", "3-5회 × 20-30초", "허리 과신전 주의"),
            ("햄스트링(넙다리뒤근육) 스트레칭", "3-5회 × 20-30초", "저림 유발 시 중단")
        ],
        "기능동작 제한": [
            ("힙 힌지(엉덩관절 접기) 패턴", "2-3세트 × 6-10회", "허리 중립 유지"),
            ("가벼운 브릿지", "2-4세트 × 8-12회", "통증 허용 범위")
        ],
    }
}

def normalize_part(part: str) -> str:
    p = part.strip()
    if not p:
        return "해당 부위"
    if "어깨" in p: return "어깨"
    if "무릎" in p: return "무릎"
    if "허리" in p or "요추" in p: return "허리"
    return p

def dose_note(irrit: str):
    if irrit == "높음":
        return "강도 낮게, 통증 허용 범위 내(다음날 악화 시 즉시 감소)"
    if irrit == "중간":
        return "통증 0~3/10 기준, 다음날 악화 시 강도/범위 감소"
    if irrit == "낮음":
        return "동작 질 유지되면 반복/저항을 점진적으로 증가"
    return "통증 과도 유발 금지, 무리한 진행 금지"

def build_assessment(part: str, core: dict) -> str:
    aggrav = clean(core.get("aggravating"))
    func = clean(core.get("functional_limit"))
    obj = clean(core.get("objective_summary"))

    base = f"{part} 통증/불편감으로 기능적 움직임 수행에 제한이 있는 양상이다."
    details = []
    if obj: details.append(obj)
    if aggrav: details.append(f"통증은 '{aggrav}'에서 악화되는 경향이 있다")
    if func: details.append(f"기능적으로는 '{func}' 관련 불편이 보고된다")
    return base + (" " + "; ".join(details) + "." if details else "")

def build_plan_detailed(part_norm: str, impair: list, freq: str, home: str, follow: str, irrit: str) -> str:
    lines = []
    lines.append("P:")
    lines.append(f"- 치료/운동 빈도(권장): {freq}")
    lines.append(f"- 자가운동 빈도(권장): {home}")
    lines.append(f"- 재평가/팔로업: {follow}")
    lines.append(f"- 강도 가이드: {dose_note(irrit)}")
    lines.append("")
    lines.append("[운동 처방(예시)]")
    lines.append("- 아래 운동은 '예시'이며, 실습생은 현장 지도/평가에 따라 선택·수정한다.")
    lines.append("")

    lib = EXERCISE_LIBRARY.get(part_norm, {})
    picked = 0
    for key in impair:
        for ex in lib.get(key, []):
            name, dose, cue = ex
            lines.append(f"- {name} : {dose}  (포인트: {cue})")
            picked += 1
            if picked >= 8:
                break
        if picked >= 8:
            break

    if picked == 0:
        lines.append("- (선택된 장애요인에 해당하는 운동 예시가 부족합니다. 장애요인을 선택하거나 부위를 구체화하세요.)")

    lines.append("")
    lines.append("[진행/조절 기준]")
    lines.append("- 운동 중 통증이 과도하게 증가하거나 다음날 악화 시: 반복/저항/범위를 낮춘다.")
    lines.append("- 동작 질이 유지되고 증상이 안정적이면: 반복수 또는 저항을 소폭 증가한다.")
    return "\n".join(lines)

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

    core = extract_core(part, S, O)
    part_show = normalize_part(part)

    A_text = build_assessment(part_show, core)

    if mode == "제출용(깔끔/무난)":
        P_lines = [
            "P:",
            f"- {part_show}의 통증 허용 범위 내에서 ROM(가동범위) 운동을 시행한다.",
            f"- {part_show} 기능 회복을 위한 근력 강화 운동을 적용한다.",
            "- 통증 반응에 따라 운동 강도 및 범위를 단계적으로 조절한다.",
            "- 일상생활 중 통증 유발 동작에 대한 주의사항 및 자가관리 교육을 제공한다."
        ]
        output = "S:\n" + S + "\n\nO:\n" + O + "\n\nA:\n" + A_text + "\n\n" + "\n".join(P_lines)
    else:
        output = "S:\n" + S + "\n\nO:\n" + O + "\n\nA:\n" + A_text + "\n\n" + build_plan_detailed(part_show, impairments, freq, home_freq, followup, irritability)

    if use_pure_korean:
        output = apply_glossary(output, GLOSSARY)

    st.subheader("최종 출력")
    st.code(output)
