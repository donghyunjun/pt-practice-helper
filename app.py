import json
import re
import streamlit as st
from openai import OpenAI

client = OpenAI()

st.set_page_config(page_title="PT SOAP 도우미 (실습생)", layout="centered")
st.title("PT SOAP 도우미 (실습생용)")
st.caption("입력은 '사실'만. AI가 S/O 분류 + A/P 작성. 사용자가 선택한 운동만 Plan에 반영.")

# -------------------------
# 출력 모드
# -------------------------
mode = st.radio("출력 모드", ["제출용(깔끔/무난)", "상세 플랜(구체/전문)"], horizontal=True)

# -------------------------
# 용어 변환(순우리말)
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

# 목
흉쇄유돌근 -> 목빗근
사각근 -> 목갈비사이근

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

# 대퇴/무릎
대퇴사두근 -> 넙다리네갈래근
햄스트링 -> 넙다리뒤근육
대퇴이두근 -> 넙다리두갈래근
반건양근 -> 반힘줄근
반막양근 -> 반막근

# 하퇴/발목
비복근 -> 장딴지근
가자미근 -> 가자미근
전경골근 -> 앞정강근

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
body_part = st.text_input("부위(예: 목/어깨/팔꿈치/손목/손/무릎/발목/허리)", value="")

patient_text = st.text_area(
    "환자 호소/상황",
    height=110,
    placeholder="예) 손목이 아파요. 키보드 오래 치면 더 아파요."
)
observer_text = st.text_area(
    "내 관찰/평가",
    height=110,
    placeholder="예) 손목 굽힘/폄 시 통증. 가동범위 제한."
)

# -------------------------
# 상세 플랜 옵션
# -------------------------
st.divider()
st.subheader("상세 플랜 구체화(선택)")

colA, colB = st.columns(2)
with colA:
    irritability = st.selectbox("자극 민감도(대략)", ["낮음", "중간", "높음", "불명"], index=3)
with colB:
    freq = st.selectbox("치료/운동 빈도(권장)", ["주 2회", "주 3회", "주 1회", "불명"], index=0)
    home_freq = st.selectbox("자가운동 빈도(권장)", ["매일", "주 5-6회", "주 3-4회", "불명"], index=1)
    followup = st.selectbox("재평가/팔로업", ["1주", "2주", "3-4주", "불명"], index=1)

impairments = st.multiselect(
    "장애요인(선택한 것만 운동 후보 생성에 반영)",
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
# 운동 라이브러리(요약: 이름, 용량, 포인트)
# -------------------------
EXERCISE_LIBRARY = {
    "목": {
        "ROM 제한": [
            ("목 굽힘/폄/돌림/기울임(통증 허용 범위)", "2-3세트 × 6-10회", "끝범위 강요 금지"),
            ("턱 당기기(경부 중립)", "2-4세트 × 6-12회(2-3초)", "턱만 당기고 목 뒤로 빼지 않기")
        ],
        "근력 저하": [
            ("등척성 목 버티기(앞/뒤/좌/우)", "2-4세트 × 6-10회(3초)", "통증 0~3/10"),
            ("밴드 로우", "2-4세트 × 8-15회", "어깨 으쓱 금지")
        ],
        "유연성/근육 단축": [
            ("상부승모근/견갑거근 스트레칭", "3-5회 × 20-30초", "저림 유발 시 중단"),
            ("가슴근 스트레칭(문틀)", "3-5회 × 20-30초", "허리 과신전 주의")
        ],
        "자세/정렬 문제": [
            ("벽 기대 정렬 리셋(귀-어깨-골반)", "2-3세트 × 30-60초", "호흡 유지"),
            ("업무 중 미니 휴식(목/어깨 가볍게 풀기)", "30-60분마다", "짧게라도 반복")
        ],
    },
    "어깨": {
        "ROM 제한": [
            ("벽 타기", "2-3세트 × 8-12회", "통증 허용 범위"),
            ("막대기/수건 보조 ROM", "2-3세트 × 8-12회", "반동 없이"),
            ("펜듈럼", "1-2세트 × 30-60초", "통증 심하면 범위↓")
        ],
        "근력 저하": [
            ("밴드 로우", "2-4세트 × 8-15회", "견갑 안정"),
            ("밴드 바깥돌림(팔꿈치 90도)", "2-4세트 × 8-15회", "통증 0~3/10"),
            ("벽/무릎 팔굽혀펴기 또는 푸시업 플러스", "2-4세트 × 6-12회", "견갑 조절")
        ],
        "유연성/근육 단축": [
            ("가슴근 스트레칭(문틀)", "3-5회 × 20-30초", "어깨 앞쪽 과신전 주의"),
            ("상부승모근/견갑거근 스트레칭", "3-5회 × 20-30초", "저림 시 중단")
        ],
        "기능동작 제한": [
            ("가벼운 물건 들기 패턴(통증 없는 범위)", "2-3세트 × 6-10회", "동작 질 우선"),
            ("스캡션(가벼운 저항)", "2-3세트 × 8-12회", "통증 허용 범위")
        ],
    },
    "팔꿈치": {
        "ROM 제한": [
            ("팔꿈치 굽힘/폄 AROM", "2-3세트 × 8-12회", "끝범위 강요 금지"),
            ("전완 엎침/뒤침", "2-3세트 × 8-12회", "통증 증가 시 범위↓")
        ],
        "근력 저하": [
            ("손목 폄(밴드/가벼운 아령)", "2-4세트 × 8-15회", "통증 0~3/10"),
            ("손목 굽힘(밴드/가벼운 아령)", "2-4세트 × 8-15회", "반동 금지"),
            ("악력(부드러운 공)", "2-4세트 × 10-15회", "통증 허용 범위")
        ],
        "유연성/근육 단축": [
            ("전완 폄근 스트레칭", "3-5회 × 20-30초", "저림/찌릿하면 중단"),
            ("전완 굽힘근 스트레칭", "3-5회 × 20-30초", "통증 과도 유발 금지")
        ],
    },
    "손목": {
        "ROM 제한": [
            ("손목 굽힘/폄 AROM", "2-3세트 × 8-12회", "통증 허용 범위"),
            ("자쪽/노쪽 치우침", "2-3세트 × 8-12회", "끝범위 강요 금지")
        ],
        "근력 저하": [
            ("손목 폄(밴드/가벼운 아령)", "2-4세트 × 8-15회", "통증 0~3/10"),
            ("손목 굽힘(밴드/가벼운 아령)", "2-4세트 × 8-15회", "반동 금지"),
            ("엎침/뒤침(가벼운 도구)", "2-4세트 × 8-12회", "통증 증가 시 강도↓"),
            ("악력(부드러운 공/퍼티)", "2-4세트 × 10-15회", "통증 모니터링")
        ],
        "유연성/근육 단축": [
            ("손목 폄근 스트레칭", "3-5회 × 20-30초", "저림 유발 시 중단"),
            ("손목 굽힘근 스트레칭", "3-5회 × 20-30초", "통증 과도 유발 금지")
        ],
        "기능동작 제한": [
            ("키보드/마우스 자세 + 휴식", "30-60분마다", "짧게 반복"),
        ],
    },
    "손": {
        "ROM 제한": [
            ("손가락 굽힘/폄 글라이딩", "2-3세트 × 8-12회", "통증 허용 범위"),
            ("엄지 맞대기/벌림", "2-3세트 × 8-12회", "정확도 우선")
        ],
        "근력 저하": [
            ("퍼티/부드러운 공 쥐기", "2-4세트 × 10-15회", "통증 0~3/10"),
            ("손가락 벌리기(고무밴드)", "2-4세트 × 10-15회", "반동 금지"),
            ("집게잡기(엄지-집게)", "2-4세트 × 8-12회", "정확도 우선")
        ],
        "기능동작 제한": [
            ("단추/지퍼/글쓰기 모의", "2-3세트 × 3-5분", "피로/통증 모니터링"),
        ],
    },
    "무릎": {
        "ROM 제한": [
            ("힐 슬라이드", "2-3세트 × 10-15회", "통증 허용 범위"),
            ("무릎 폄 유지(수건 받침)", "3-5회 × 20-30초", "과폄 금지")
        ],
        "근력 저하": [
            ("쿼드셋(등척성)", "2-4세트 × 8-12회(3-5초)", "통증 허용 범위"),
            ("직거상(SLR)", "2-4세트 × 8-12회", "허리 과신전 주의"),
            ("의자 앉았다 일어서기", "2-4세트 × 6-12회", "무릎 안쪽 붕괴 주의")
        ],
        "기능동작 제한": [
            ("스텝업(낮은 발판)", "2-3세트 × 6-10회", "정렬 체크"),
        ],
    },
    "발목": {
        "ROM 제한": [
            ("발목 위/아래 굽힘 AROM", "2-3세트 × 8-12회", "통증 허용 범위"),
            ("발목 원 그리기(작게)", "2-3세트 × 6-10회", "통증 증가 시 범위↓"),
            ("종아리 스트레칭(벽)", "3-5회 × 20-30초", "통증 과도 유발 금지")
        ],
        "근력 저하": [
            ("밴드 발등굽힘/발바닥쪽굽힘", "2-4세트 × 8-15회", "천천히 통제"),
            ("까치발 들기(양발→한발)", "2-4세트 × 6-12회", "균형 확보")
        ],
        "고유수용감각/균형 저하": [
            ("한발서기(안전 확보)", "3-5세트 × 30-60초", "흔들림 감소 목표"),
        ],
    },
    "허리": {
        "근력 저하": [
            ("맥길 컬업", "2-4세트 × 6-10회(2-3초)", "허리 꺾임 최소화"),
            ("버드독", "2-4세트 × 6-10회/측", "골반 흔들림 최소"),
            ("데드버그", "2-4세트 × 6-10회/측", "허리 뜨지 않게")
        ],
        "기능동작 제한": [
            ("힙 힌지 패턴", "2-3세트 × 6-10회", "허리 중립"),
            ("가벼운 브릿지", "2-4세트 × 8-12회", "통증 허용 범위")
        ],
    }
}

def normalize_part(part: str) -> str:
    p = (part or "").strip()
    if not p:
        return "해당 부위"
    if "목" in p or "경추" in p:
        return "목"
    if "어깨" in p:
        return "어깨"
    if "팔꿈치" in p or "주관절" in p:
        return "팔꿈치"
    if "손목" in p or "수근" in p:
        return "손목"
    if "손바닥" in p or "손" in p or "수부" in p:
        return "손"
    if "발목" in p or "족관절" in p:
        return "발목"
    if "무릎" in p:
        return "무릎"
    if "허리" in p or "요추" in p:
        return "허리"
    return p

def dose_note(irrit: str):
    if irrit == "높음":
        return "강도 낮게, 통증 허용 범위 내(다음날 악화 시 즉시 감소)"
    if irrit == "중간":
        return "통증 0~3/10 기준, 다음날 악화 시 강도/범위 감소"
    if irrit == "낮음":
        return "동작 질 유지되면 반복/저항을 점진적으로 증가"
    return "통증 과도 유발 금지, 무리한 진행 금지"

def build_assessment(part_norm: str, core: dict) -> str:
    aggrav = clean(core.get("aggravating"))
    func = clean(core.get("functional_limit"))
    obj = clean(core.get("objective_summary"))

    base = f"{part_norm} 통증/불편감으로 기능적 움직임 수행에 제한이 있는 양상이다."
    details = []
    if obj: details.append(obj)
    if aggrav: details.append(f"통증은 '{aggrav}'에서 악화되는 경향이 있다")
    if func: details.append(f"기능적으로는 '{func}' 관련 불편이 보고된다")
    return base + (" " + "; ".join(details) + "." if details else "")

def collect_candidates(part_norm: str, impair: list):
    lib = EXERCISE_LIBRARY.get(part_norm, {})
    candidates = []
    seen = set()
    for key in impair:
        for name, dose, cue in lib.get(key, []):
            k = f"{name}|{dose}|{cue}"
            if k in seen:
                continue
            seen.add(k)
            candidates.append({"impair": key, "name": name, "dose": dose, "cue": cue})
    return candidates

def build_plan_selected(part_norm: str, selected, freq: str, home: str, follow: str, irrit: str) -> str:
    lines = []
    lines.append("P:")
    lines.append(f"- 치료/운동 빈도(권장): {freq}")
    lines.append(f"- 자가운동 빈도(권장): {home}")
    lines.append(f"- 재평가/팔로업: {follow}")
    lines.append(f"- 강도 가이드: {dose_note(irrit)}")
    lines.append("")
    lines.append("[운동 처방(선택 반영)]")
    if not selected:
        lines.append("- (선택된 운동이 없습니다. 운동 후보에서 체크 후 생성하세요.)")
    else:
        for ex in selected:
            lines.append(f"- {ex['name']} : {ex['dose']}  (포인트: {ex['cue']})")
    lines.append("")
    lines.append("[진행/조절 기준]")
    lines.append("- 운동 중 통증이 과도하게 증가하거나 다음날 악화 시: 반복/저항/범위를 낮춘다.")
    lines.append("- 동작 질이 유지되고 증상이 안정적이면: 반복수 또는 저항을 소폭 증가한다.")
    return "\n".join(lines)

# -------------------------
# 1단계: 분류/후보 생성
# -------------------------
st.divider()
st.subheader("실행")

if "so_cache" not in st.session_state:
    st.session_state.so_cache = None
if "core_cache" not in st.session_state:
    st.session_state.core_cache = None
if "candidates" not in st.session_state:
    st.session_state.candidates = []
if "part_norm" not in st.session_state:
    st.session_state.part_norm = "해당 부위"

btn1 = st.button("1) S/O 자동 분류 + 운동 후보 생성")

if btn1:
    if not patient_text.strip() and not observer_text.strip():
        st.warning("최소한 '환자 호소/상황' 또는 '내 관찰/평가' 중 하나는 입력하세요.")
        st.stop()

    so = classify_to_SO(body_part, patient_text, observer_text)
    part = clean(so.get("part")) or body_part or "해당 부위"
    S = clean(so.get("S"))
    O = clean(so.get("O"))

    core = extract_core(part, S, O)
    part_norm = normalize_part(part)

    st.session_state.so_cache = {"part": part, "S": S, "O": O}
    st.session_state.core_cache = core
    st.session_state.part_norm = part_norm
    st.session_state.candidates = collect_candidates(part_norm, impairments)

# -------------------------
# 캐시가 있으면 보여주기
# -------------------------
if st.session_state.so_cache:
    so = st.session_state.so_cache
    core = st.session_state.core_cache or {}
    part_norm = st.session_state.part_norm

    A_text = build_assessment(part_norm, core)

    st.subheader("AI 분류 결과(S/O)")
    s_show = so["S"]
    o_show = so["O"]
    if use_pure_korean:
        s_show = apply_glossary(s_show, GLOSSARY)
        o_show = apply_glossary(o_show, GLOSSARY)
    st.code(f"S:\n{s_show}\n\nO:\n{o_show}")

    st.subheader("A(요약)")
    a_show = A_text
    if use_pure_korean:
        a_show = apply_glossary(a_show, GLOSSARY)
    st.code(a_show)

    # 제출용이면 여기서 끝
    if mode == "제출용(깔끔/무난)":
        st.info("제출용 모드는 운동 선택 단계 없이 간단 Plan을 출력합니다.")
        P_lines = [
            "P:",
            f"- {part_norm}의 통증 허용 범위 내에서 ROM(가동범위) 운동을 시행한다.",
            f"- {part_norm} 기능 회복을 위한 근력 강화 운동을 적용한다.",
            "- 통증 반응에 따라 운동 강도 및 범위를 단계적으로 조절한다.",
            "- 일상생활 중 통증 유발 동작에 대한 주의사항 및 자가관리 교육을 제공한다."
        ]
        out = f"S:\n{so['S']}\n\nO:\n{so['O']}\n\nA:\n{A_text}\n\n" + "\n".join(P_lines)
        if use_pure_korean:
            out = apply_glossary(out, GLOSSARY)
        st.subheader("최종 출력(제출용)")
        st.code(out)
    else:
        # 상세 플랜: 운동 후보 체크
        st.subheader("운동 후보(체크한 것만 최종 Plan에 반영)")
        cands = st.session_state.candidates or []

        if not cands:
            st.warning("운동 후보가 없습니다. (부위/장애요인 선택을 확인하세요.)")
        else:
            # 기본 체크: 각 장애요인에서 1개씩 자동 체크
            default_checks = {}
            first_by_impair = set()
            for idx, ex in enumerate(cands):
                if ex["impair"] not in first_by_impair:
                    first_by_impair.add(ex["impair"])
                    default_checks[idx] = True
                else:
                    default_checks[idx] = False

            selected = []
            for idx, ex in enumerate(cands):
                label = f"[{ex['impair']}] {ex['name']} / {ex['dose']} (포인트: {ex['cue']})"
                checked = st.checkbox(label, value=default_checks.get(idx, False))
                if checked:
                    selected.append(ex)

            btn2 = st.button("2) 체크한 운동으로 최종 P 생성")

            if btn2:
                P_text = build_plan_selected(part_norm, selected, freq, home_freq, followup, irritability)
                out = f"S:\n{so['S']}\n\nO:\n{so['O']}\n\nA:\n{A_text}\n\n{P_text}"
                if use_pure_korean:
                    out = apply_glossary(out, GLOSSARY)
                st.subheader("최종 출력(상세 플랜)")
                st.code(out)
