# app.py
# PT SOAP 도우미 (실습생용) - 단일 파일 배포용
# 핵심: (1) 어색한 단어/문구 원천 차단 + 자동 정리
#      (2) 사이드바 "프로젝트 전체 스캔" 버튼 복구
#      (3) S/O/A/P 모두 생성 + P 누락 방지(폴백)
#      (4) 제출용 vs 상세 플랜 모드 차등
#
# 실행: streamlit run app.py

from __future__ import annotations

import os
import re
import json
import time
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st


# -----------------------------
# 0) 앱 버전/해시 (실행 중 코드 확인용)
# -----------------------------
APP_VERSION = "PT-SOAP-FINAL-2026-02-05-v4"
_THIS_FILE = os.path.abspath(__file__)


def _file_hash(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:12]
    except Exception:
        return "unknownhash"


APP_HASH = _file_hash(_THIS_FILE)


# -----------------------------
# 1) "어색한 단어/문구" 오염 방지/정리
# -----------------------------
# 사용자가 계속 보고한 오염 단어/문구들(원문 그대로)
BANNED_TOKENS = [
    "킄", "큭", "와", "서프",
    "입주자", "거주민",
    "엑음", "기본적으로", "낮",  # 잘못된 자극감도 표기
    "스위치동범위", "스위치동 범위",  # 오타
    "탄력건포", "쥐어짜기", "근육질", "자/정렬문제",
    "초밥/선택",
]

# 안전한 치환(정상 문구로 강제)
REPLACE_MAP = {
    # 입력 라벨/필드
    "입주자/생활환경": "환자 호소/상황(주관적 정보)",
    "거주민/생활생활(주관적 정보)": "환자 호소/상황(주관적 정보)",
    "거주민": "환자",
    "입주자": "환자",

    # 자극감도(대략)
    "낮": "낮음",
    "기본적으로": "중간",
    "엑음": "높음",

    # 장애요인(문구 정리)
    "탄력건포": "연부조직(근막/근긴장/유연성) 제한",
    "쥐어짜기/근육질": "근긴장 증가/과긴장",
    "자/정렬문제": "정렬/자세 문제",
    "스위치동범위": "관절가동범위(ROM) 제한",

    # 버튼/라벨 오염
    "초밥/선택": "초기화/선택 초기화",
}

# “킄/와/서프” 같은 짧은 잡음 토큰이 선택지에 섞여 들어가는 경우를 강제로 필터링
NOISE_PATTERN = re.compile(r"^(?:[ㄱ-ㅎ]{1,2}|[ㅏ-ㅣ]{1,2}|[가-힣]{1,2})$")


def normalize_text(s: str) -> str:
    """화면/저장/AI입력에 들어가기 전에 문구를 강제 정리."""
    if not isinstance(s, str):
        return s

    out = s

    # 1) 치환
    for k, v in REPLACE_MAP.items():
        out = out.replace(k, v)

    # 2) 금칙 토큰이 '단독' 혹은 '구분자'로 들어간 경우 제거(선택지 오염 방지)
    # 예: "킄", "와" 등이 줄바꿈/쉼표로 섞임
    for tok in BANNED_TOKENS:
        # 단독 토큰(앞뒤 공백/구분자) 제거
        out = re.sub(rf"(^|[\s,/\|·\-]+){re.escape(tok)}([\s,/\|·\-]+|$)", r"\1", out)

    # 3) 다중 공백 정리
    out = re.sub(r"[ \t]+", " ", out).strip()

    return out


def clean_options(options: List[str], allow_other_label: Optional[str] = None) -> List[str]:
    """드롭다운 선택지에서 오염/잡음 제거 + 중복 제거 + 정렬 유지."""
    cleaned: List[str] = []
    seen = set()

    for opt in options:
        if not isinstance(opt, str):
            continue
        x = normalize_text(opt)

        # 너무 짧은 잡음(킄/와/큭 등) 방지
        if x in BANNED_TOKENS:
            continue
        if NOISE_PATTERN.match(x) and x not in ("목", "눈", "코"):  # 혹시라도 단어로 쓰일 수 있는 예외 최소만
            # "목" 같은 정상 부위는 통과, 그 외 1~2글자 잡음은 제거
            continue

        if allow_other_label and x == allow_other_label:
            pass

        if x and x not in seen:
            cleaned.append(x)
            seen.add(x)

    return cleaned


# -----------------------------
# 2) 정상 용어(선택지) - 여기만 고치면 화면이 안전해짐
# -----------------------------
BODY_PARTS_BASE = [
    "어깨", "목", "등(흉추)", "허리(요추)",
    "팔꿈치", "손목", "손/손가락",
    "고관절", "무릎", "발목", "발/발가락",
    "기타(직접입력)",
]
BODY_PARTS = clean_options(BODY_PARTS_BASE, allow_other_label="기타(직접입력)")

STIMULUS_LEVELS_BASE = ["불명", "낮음", "중간", "높음"]
STIMULUS_LEVELS = clean_options(STIMULUS_LEVELS_BASE)

# 장애요인(선택한 항목으로 P를 더 구체화)
BARRIERS_BASE = [
    "관절가동범위(ROM) 제한",
    "근력 저하/근지구력 저하",
    "통증(부하 민감)",
    "제한 동작(특정 동작의 통증/불안정)",
    "반대/자세(스폴라·골반·하지 말고 등) 문제",
    "고유수용감각/균형 저하",
    "연부조직(근막/근긴장/유연성) 제한",
]
BARRIERS = clean_options(BARRIERS_BASE)

TREAT_FREQ = ["주 1회", "주 2회", "주 3회", "주 4회"]
EXER_FREQ = ["주 2-3회", "주 3-4회", "주 5-6회", "매일(가벼운 강도)"]
FOLLOW_UP = ["1주", "2주", "4주", "6주"]


# -----------------------------
# 3) 기록 저장/불러오기(JSON)
# -----------------------------
DATA_DIR = os.path.join(os.path.dirname(_THIS_FILE), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DEFAULT_DB_PATH = os.path.join(DATA_DIR, "soap_notes.json")


def load_db(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"notes": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            db = json.load(f)
        if not isinstance(db, dict):
            return {"notes": []}
        if "notes" not in db or not isinstance(db["notes"], list):
            db["notes"] = []
        return db
    except Exception:
        return {"notes": []}


def save_db(path: str, db: Dict[str, Any]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"저장 실패: {e}")


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# -----------------------------
# 4) OpenAI (선택) + 폴백 생성기
# -----------------------------
@dataclass
class SoapInput:
    mode: str  # "제출용" | "상세"
    body_part: str
    body_part_free: str
    s_text: str
    o_text: str
    stimulus: str
    treat_freq: str
    exer_freq: str
    follow_up: str
    barriers: List[str]


def _has_openai_key() -> bool:
    # Streamlit secrets 우선, 그 다음 환경변수
    key = st.secrets.get("OPENAI_API_KEY", None) if hasattr(st, "secrets") else None
    if not key:
        key = os.getenv("OPENAI_API_KEY", "")
    return bool(key and isinstance(key, str) and len(key) > 10)


def _get_openai_key() -> str:
    key = st.secrets.get("OPENAI_API_KEY", None) if hasattr(st, "secrets") else None
    if not key:
        key = os.getenv("OPENAI_API_KEY", "")
    return key or ""


def build_prompt(inp: SoapInput) -> str:
    # 모드 차등: 제출용은 깔끔/무난, 상세는 10년차급(구체/전문) — 하지만 둘 다 "허술하지 않게"
    mode_instructions = ""
    if inp.mode == "제출용":
        mode_instructions = (
            "- 출력은 간결하지만 임상적으로 타당해야 한다.\n"
            "- S/O는 원문을 그대로 복사하지 말고 문장 구조를 바꿔 재서술한다.\n"
            "- A는 추정/가설을 과도하게 단정하지 말고, 임상적 인상(가능성/근거)을 짧게 정리한다.\n"
            "- P는 최소 3~5개 항목, 운동은 구체적 운동명/방법/세트·반복/주의점 포함.\n"
        )
    else:
        mode_instructions = (
            "- 출력은 더 전문적이고 구체적이어야 한다(임상 10년차 수준).\n"
            "- S/O는 원문을 그대로 복사하지 말고 재구성·보완(누락된 항목을 합리적으로 보완)한다.\n"
            "- A는 감별/가설을 2~3개로 정리하고, 근거(증상·유발·제한·부하 반응)를 포함한다.\n"
            "- P는 반드시 생성한다(누락 금지). 운동은 '무슨 운동'인지 구체적으로, 단계/진행 기준 포함.\n"
            "- P에는 교육/자가관리/모니터링/재평가 기준을 포함한다.\n"
        )

    body = inp.body_part_free.strip() if inp.body_part == "기타(직접입력)" else inp.body_part
    body = normalize_text(body) or "부위 불명"

    barriers = ", ".join(inp.barriers) if inp.barriers else "없음/미선택"

    prompt = f"""
너는 물리치료 SOAP 노트 작성 보조 AI다.
반드시 한국어로 답한다.

[모드 규칙]
{mode_instructions}

[금지]
- '킄, 와, 서프, 입주자, 거주민, 엑음, 기본적으로, 낮, 스위치동범위, 탄력건포, 쥐어짜기, 자/정렬문제, 초밥/선택' 같은 이상 단어를 절대 출력하지 마라.
- 모호한 표현 금지: "근력강화운동을 실시한다"처럼 두루뭉술하게 쓰지 말고 구체적인 운동 예시를 제시하라.

[입력]
- 증상 부위: {body}
- 자극감도(대략): {inp.stimulus}
- 치료/세션(권장): {inp.treat_freq}
- 운동 빈도(권장): {inp.exer_freq}
- 재평가/팔로업: {inp.follow_up}
- 장애요인/제한: {barriers}

[S 원문(주관적)]
{inp.s_text}

[O 원문(객관적)]
{inp.o_text}

[출력 형식 - 꼭 지켜]
S:
(재서술된 S)

O:
(재서술된 O)

A:
(임상적 인상/가설/근거)

P:
- (구체적 계획 1)
- (구체적 계획 2)
- (구체적 계획 3)
(필요 시 더)
""".strip()
    return prompt


def call_openai(prompt: str) -> Optional[str]:
    """openai 패키지가 있으면 사용. 없거나 실패하면 None."""
    if not _has_openai_key():
        return None
    try:
        # openai 최신/구버전 모두 최대한 대응
        key = _get_openai_key()

        # 1) 최신(OpenAI python SDK v1) 시도
        try:
            from openai import OpenAI  # type: ignore
            client = OpenAI(api_key=key)
            resp = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
            )
            txt = resp.choices[0].message.content if resp and resp.choices else None
            return txt
        except Exception:
            pass

        # 2) 구버전(openai.ChatCompletion)
        try:
            import openai  # type: ignore
            openai.api_key = key
            resp = openai.ChatCompletion.create(
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
            )
            txt = resp["choices"][0]["message"]["content"]
            return txt
        except Exception:
            return None
    except Exception:
        return None


# -----------------------------
# 5) 폴백(규칙 기반) - P 누락 절대 방지 + 구체적 운동 제공
# -----------------------------
def fallback_generate(inp: SoapInput) -> str:
    body = inp.body_part_free.strip() if inp.body_part == "기타(직접입력)" else inp.body_part
    body = normalize_text(body) or "부위 불명"

    # S/O 재서술(복붙 느낌 최소화)
    s = normalize_text(inp.s_text)
    o = normalize_text(inp.o_text)
    s_rs = f"환자는 {body} 부위와 관련하여 '{s[:80] + ('…' if len(s) > 80 else '')}'와 같은 불편을 호소한다."
    o_rs = f"관찰/검사에서 '{o[:80] + ('…' if len(o) > 80 else '')}'와 같은 소견이 확인된다."

    # 간단 A(단정 피하고 근거 기반)
    a_lines = [
        f"{body} 통증/불편으로 기능적 움직임 수행에 제한이 의심된다.",
    ]
    if "ROM" in " ".join(inp.barriers) or "가동" in " ".join(inp.barriers):
        a_lines.append("관절가동범위 제한 및 통증 회피 패턴이 가능하다.")
    if "근력" in " ".join(inp.barriers) or "근지구력" in " ".join(inp.barriers):
        a_lines.append("근력/근지구력 저하로 부하 내성이 낮아졌을 수 있다.")
    if "정렬" in " ".join(inp.barriers) or "자세" in " ".join(inp.barriers):
        a_lines.append("정렬/자세 요인이 증상 지속에 기여했을 가능성이 있다.")
    a = " ".join(a_lines)

    # 부위별 구체 P 템플릿 (너무 위험한 의료행위 지시는 피하고, 교육용/임상 검토 전제로)
    P = build_specific_plan(inp, body)

    return f"S:\n{s_rs}\n\nO:\n{o_rs}\n\nA:\n{a}\n\nP:\n" + "\n".join([f"- {line}" for line in P])


def build_specific_plan(inp: SoapInput, body: str) -> List[str]:
    mode = inp.mode
    barriers = set(inp.barriers or [])
    stim = inp.stimulus

    # 강도/볼륨 가이드(대략)
    if stim == "높음":
        vol = "통증 0~3/10 범위에서"
        prog = "통증/야간통/다음날 악화 여부를 기준으로 진행"
    elif stim == "낮음":
        vol = "통증 허용 범위 내(0~4/10)에서"
        prog = "피로감은 허용하되 통증 급증/야간통은 피하며 진행"
    else:
        vol = "통증 허용 범위 내에서"
        prog = "증상 반응(당일/다음날)을 기준으로 점진적 진행"

    # 공통 계획
    base = [
        f"교육: 증상 유발 동작/부하 조절(특히 통증 악화 자세·반복 동작 회피), {prog}.",
        f"자가관리: 온열/냉각은 본인 선호 및 반응에 따라 선택(피부 상태 확인).",
        f"재평가: {inp.follow_up} 후 통증(강도/빈도), 기능, ROM/근력 변화로 계획 조정.",
    ]

    # 부위별 운동 세트(구체)
    body_lower = body.replace(" ", "")
    is_shoulder = any(k in body_lower for k in ["어깨", "견"])
    is_neck = "목" in body_lower or "경추" in body_lower
    is_lowback = any(k in body_lower for k in ["허리", "요추"])
    is_knee = "무릎" in body_lower
    is_ankle = "발목" in body_lower or "발/" in body_lower or "발가락" in body_lower

    plan: List[str] = []

    # 치료 빈도 반영
    plan.append(f"치료/세션: {inp.treat_freq} 내원 기준, 홈운동 {inp.exer_freq} 권장(불가 시 최소 주 3회).")

    # 장애요인 반영(ROM/근력/통증/정렬)
    if is_shoulder:
        plan += [
            f"관절가동범위(ROM) 회복: 펜듈럼(코드만) 1~2분 × 2세트, 테이블/벽 슬라이드 10~12회 × 2세트, {vol}.",
            f"회전근개 등척성: 문틀/수건 이용 외회전·내회전 등척 5~10초 유지 × 8~10회 × 2세트(통증 없는 각도).",
            f"견갑 안정화: 견갑골 후인/하강(스캡 셋) 5초 × 10회 × 2세트 → 탄성밴드 로우 12회 × 2~3세트.",
            f"어깨 굴곡/외전 진행: 벽슬라이드 → 스틱 AAROM → 통증 허용 시 덤벨 프론트/레터럴 레이즈(가벼운 중량) 8~12회 × 2~3세트.",
            f"상지 기능 통합: 벽 푸시업+ 8~12회 × 2세트(견갑 전인 포함) → 점진적으로 난이도 상승.",
        ]
        if "통증(부하 민감)" in barriers:
            plan.append("통증 조절 우선: 과부하 동작(오버헤드 반복, 고중량 프레스)은 일시 제한하고, 통증 없는 범위에서 노출을 단계적으로 증가.")
        if mode == "상세":
            plan += [
                "진행 기준(예): 외전 90°에서 통증 3/10 이하 + 다음날 악화 없음 → 외전 범위/부하 10~20% 증가.",
                "스캡/흉추 보완: 폼롤러 흉추 신전 6~8회 × 2세트, 견갑면 거상 시 상부승모 과활성 시 큐잉(목 힘 빼고 하부승모/전거근 활성).",
            ]

    elif is_neck:
        plan += [
            f"자세/부하 교육: 화면 높이·턱 내밀기 감소, 30~40분마다 1~2분 휴식.",
            f"심부경부굴곡근 운동: 턱 당기기(치킨턱) 5초 × 10회 × 2세트 → 누워서 압력바이오피드백(가능 시) 22~26mmHg 단계.",
            f"견갑 안정화: 밴드 로우 12회 × 2~3세트 + Y/T(가벼운 강도) 8~10회 × 2세트.",
            f"가동성: 상부승모/견갑거근 스트레칭 20~30초 × 2~3회(통증 유발 금지), 흉추 회전 운동 8회 × 2세트.",
        ]
        if mode == "상세":
            plan.append("두통/방사통/신경학적 증상 동반 시: 신경학적 스크리닝(감각/근력/반사) 및 의뢰 기준 확인(악화/야간통/진행성 저림 등).")

    elif is_lowback:
        plan += [
            f"가동성/통증완화: 맥켄지(신전 선호 시) 프론프레스업 8~10회 × 2세트 또는 캣카우 8~10회 × 2세트, {vol}.",
            f"코어 안정화: 데드버그 6~10회 × 2~3세트, 버드독 6~10회 × 2~3세트(허리 꺾임 방지).",
            f"둔근 강화: 글루트 브리지 10~12회 × 2~3세트 → 밴드 몬스터 워크 10m × 3회.",
            f"기능 훈련: 힙힌지 패턴(막대기) 8~10회 × 2세트 → 통증 허용 시 스쿼트 범위 점진 확대.",
        ]
        if mode == "상세":
            plan.append("진행 기준(예): 일상 동작(앉기/서기) 통증 3/10 이하 + 다음날 악화 없음 → 저항/반복 10~20% 증가, 고난도(데드리프트 패턴)로 단계화.")

    elif is_knee:
        plan += [
            f"ROM/부종 관리(필요 시): 무릎 굴곡 AAROM 10회 × 2세트, 슬개골 주변 가벼운 가동(통증 없는 범위).",
            f"대퇴사두/둔근 강화: 쿼드셋 5초 × 10회 × 2세트 → 미니 스쿼트 8~12회 × 2~3세트.",
            f"힙/무릎 정렬: 클램셸 12회 × 2~3세트 + 사이드 스텝(밴드) 10m × 3회.",
            f"기능: 스텝업(낮은 높이) 8~10회 × 2세트 → 통증 허용 시 높이/부하 점진 증가.",
        ]
        if mode == "상세":
            plan.append("통증 위치(전방/내측/외측)에 따라 부하 조절(예: 전방 통증이면 깊은 굴곡 스쿼트 일시 제한, 힙 힌지 비중↑).")

    elif is_ankle:
        plan += [
            f"ROM: 발목 펌프/원 그리기 20~30회 × 2세트, 무릎-벽(DF) 테스트 겸 스트레치 8~10회 × 2세트.",
            f"근력: 밴드 저항 PF/DF/EV/IV 12회 × 2~3세트.",
            f"균형/고유수용감각: 한발서기 20~30초 × 3회 → 쿠션 위/눈 감기 등 단계화.",
            f"기능: 카프 레이즈 8~12회 × 2~3세트(가능 시) → 보행/계단 노출 점진 증가.",
        ]
        if mode == "상세":
            plan.append("재부상 예방: 점프/컷팅 복귀 전(통증 0~2/10, 좌우 카프 레이즈 반복수 차이 <10%, Y-balance/홉 테스트 단계 통과) 같은 기준을 설정.")

    else:
        # 기타/미분류: 범용 템플릿
        plan += [
            f"ROM: 통증 없는 범위에서 AAROM 10~12회 × 2세트, {vol}.",
            f"근력: 해당 부위 저항운동(밴드/가벼운 중량) 8~12회 × 2~3세트.",
            f"안정화/조절: 자세 큐잉 + 천천히(3초 이완) 수행, 보상동작 최소화.",
        ]
        if mode == "상세":
            plan.append("진행 기준: 통증/피로 반응(당일/다음날), 기능 점수(예: 동작 수행 가능 범위)로 단계적 증량(10~20%).")

    # 마지막에 공통/안전/추적 추가
    plan += base

    # “제출용”은 너무 길어지지 않게 컷(하지만 구체성은 유지)
    if mode == "제출용":
        # 핵심 6~9줄로 유지
        if len(plan) > 9:
            plan = plan[:9]

    # 최종 정리(금칙어 방지)
    plan = [normalize_text(x) for x in plan if normalize_text(x)]
    return plan


def parse_soap(text: str) -> Dict[str, str]:
    """AI 응답에서 S/O/A/P 블록을 뽑아내되, 없으면 빈 문자열."""
    if not text:
        return {"S": "", "O": "", "A": "", "P": ""}

    t = normalize_text(text)

    # 라벨 기준 분리(대충 나눠도 됨)
    def grab(label: str, next_labels: List[str]) -> str:
        idx = t.find(label + ":")
        if idx < 0:
            return ""
        start = idx + len(label) + 1
        end = len(t)
        for nl in next_labels:
            j = t.find(nl + ":", start)
            if j >= 0:
                end = min(end, j)
        return t[start:end].strip()

    s = grab("S", ["O", "A", "P"])
    o = grab("O", ["A", "P"])
    a = grab("A", ["P"])
    p = grab("P", [])

    return {"S": s, "O": o, "A": a, "P": p}


def ensure_p_not_empty(inp: SoapInput, soap: Dict[str, str]) -> Dict[str, str]:
    """P 누락 방지: 비어 있으면 폴백으로 채운다."""
    if soap.get("P", "").strip():
        return soap

    # 폴백에서 P만 추출
    fb = fallback_generate(inp)
    fb_parsed = parse_soap(fb)
    soap["P"] = fb_parsed.get("P", "").strip()
    if not soap["P"]:
        # 최후의 최후: 최소 계획
        soap["P"] = "- 통증 허용 범위 내에서 ROM 유지 및 가벼운 근력운동을 시행하고, 증상 반응에 따라 강도를 조절한다.\n- 일상 동작 교육 및 {0} 후 재평가한다.".format(inp.follow_up)
    return soap


# -----------------------------
# 6) "프로젝트/문구 스캔" (사이드바 버튼)
# -----------------------------
SCAN_HINT = (
    "아래에 금칙어 탐지 결과가 나오면,\n"
    "① 아직 다른 파일/이전 코드를 실행 중이거나\n"
    "② 프로젝트 어딘가(다른 .py / JSON)에 오염 문구가 남아있다는 뜻이에요.\n\n"
    "권장: '프로젝트 전체 스캔 실행(권장)' 버튼으로 확인하세요."
)


def scan_project_texts(root_dir: str) -> List[Tuple[str, int, str]]:
    """root_dir 아래 .py/.json/.txt에서 BANNED/REPLACE 키워드 탐지."""
    hits: List[Tuple[str, int, str]] = []
    target_ext = (".py", ".json", ".txt", ".md")
    max_file_size = 2_000_000  # 2MB

    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            if not fn.lower().endswith(target_ext):
                continue
            path = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(path) > max_file_size:
                    continue
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except Exception:
                continue

            for i, line in enumerate(lines, start=1):
                line_n = line.strip()
                for tok in BANNED_TOKENS:
                    if tok and tok in line_n:
                        hits.append((path, i, f"term= {tok} | {line_n[:120]}"))
                        break
                # 또한, 잘못된 라벨(입주자/생활환경)도 탐지
                for bad in ["입주자/생활환경", "거주민/생활생활", "초밥/선택", "스위치동범위"]:
                    if bad in line_n:
                        hits.append((path, i, f"term= {bad} | {line_n[:120]}"))
                        break

    return hits


# -----------------------------
# 7) Streamlit UI
# -----------------------------
def init_state() -> None:
    defaults = {
        "db_path": DEFAULT_DB_PATH,
        "db": load_db(DEFAULT_DB_PATH),
        "keyword": "",
        "filter_body": "",
        "selected_note_id": "",

        "mode": "제출용",
        "body_part": "기타(직접입력)",
        "body_part_free": "",
        "s_text": "",
        "o_text": "",
        "stimulus": "불명",
        "treat_freq": "주 2회",
        "exer_freq": "주 5-6회",
        "follow_up": "2주",
        "barriers": [],

        "soap_out": {"S": "", "O": "", "A": "", "P": ""},
        "scan_hits": [],
        "last_generate_at": 0.0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def sidebar_notes() -> None:
    st.sidebar.markdown("## 🗂️ 노트 기록")
    st.sidebar.caption("로컬 실행: 저장 유지 / Streamlit Cloud: (JSON)로 백업 권장")

    # 실행 확인(버전/해시)
    st.sidebar.success(f"실행 확인: {APP_VERSION} | {os.path.basename(_THIS_FILE)} 해시: {APP_HASH}")

    # 스캔 UI
    with st.sidebar.expander("🧪 진단(문구/단어 오염 탐지)", expanded=True):
        st.write(SCAN_HINT)
        if st.button("프로젝트 전체 스캔 실행(권장)", use_container_width=True):
            root = os.path.dirname(_THIS_FILE)
            st.session_state["scan_hits"] = scan_project_texts(root)
        hits = st.session_state.get("scan_hits", [])
        if hits:
            st.error(f"금칙어/오염 발견: {len(hits)}건")
            # 최대 30건까지만 표시
            for path, line, msg in hits[:30]:
                st.code(f"파일: {os.path.basename(path)} | {line}줄 | {msg}", language="text")
            if len(hits) > 30:
                st.caption("표시 제한(30건). 추가는 파일을 열어 직접 확인하세요.")
        else:
            st.info("탐지 결과 없음(또는 아직 스캔 미실행).")

    # 검색/필터
    st.sidebar.markdown("---")
    st.session_state["keyword"] = st.sidebar.text_input("키워드 검색(분야/내용)", value=st.session_state["keyword"])
    st.session_state["filter_body"] = st.sidebar.text_input("특정 부위 찾기(선택)", value=st.session_state["filter_body"])

    db = st.session_state["db"]
    notes = db.get("notes", [])
    keyword = normalize_text(st.session_state["keyword"]).lower()
    fbody = normalize_text(st.session_state["filter_body"]).lower()

    def note_match(note: Dict[str, Any]) -> bool:
        hay = " ".join([
            str(note.get("body_part", "")),
            str(note.get("body_part_free", "")),
            str(note.get("S", "")),
            str(note.get("O", "")),
            str(note.get("A", "")),
            str(note.get("P", "")),
        ]).lower()
        if keyword and keyword not in hay:
            return False
        if fbody:
            bp = (str(note.get("body_part", "")) + " " + str(note.get("body_part_free", ""))).lower()
            if fbody not in bp:
                return False
        return True

    filtered = [n for n in notes if note_match(n)]
    filtered = sorted(filtered, key=lambda x: x.get("created_at", ""), reverse=True)

    # 최근 50개
    filtered = filtered[:50]

    options = ["(선택안함)"] + [f"{n.get('created_at','')} | {n.get('title','(무제)')}" for n in filtered]
    choice = st.sidebar.selectbox("기록을 기록 선택(최근 50개)", options, index=0)

    if choice != "(선택안함)":
        idx = options.index(choice) - 1
        picked = filtered[idx]
        st.session_state["selected_note_id"] = picked.get("id", "")

        if st.sidebar.button("불러오기", use_container_width=True):
            # 입력칸에 로드
            st.session_state["mode"] = picked.get("mode", "제출용")
            st.session_state["body_part"] = picked.get("body_part", "기타(직접입력)")
            st.session_state["body_part_free"] = picked.get("body_part_free", "")
            st.session_state["s_text"] = picked.get("S_in", "")
            st.session_state["o_text"] = picked.get("O_in", "")
            st.session_state["stimulus"] = picked.get("stimulus", "불명")
            st.session_state["treat_freq"] = picked.get("treat_freq", "주 2회")
            st.session_state["exer_freq"] = picked.get("exer_freq", "주 5-6회")
            st.session_state["follow_up"] = picked.get("follow_up", "2주")
            st.session_state["barriers"] = picked.get("barriers", [])
            st.session_state["soap_out"] = {
                "S": picked.get("S", ""),
                "O": picked.get("O", ""),
                "A": picked.get("A", ""),
                "P": picked.get("P", ""),
            }

    st.sidebar.markdown("---")
    # JSON 내보내기/가져오기
    st.sidebar.download_button(
        "전체 내용에 대해(JSON)",
        data=json.dumps(st.session_state["db"], ensure_ascii=False, indent=2),
        file_name="soap_notes_backup.json",
        mime="application/json",
        use_container_width=True,
    )

    up = st.sidebar.file_uploader("가져오기(JSON)", type=["json"])
    if up is not None:
        try:
            new_db = json.loads(up.getvalue().decode("utf-8"))
            if isinstance(new_db, dict) and isinstance(new_db.get("notes", []), list):
                st.session_state["db"] = new_db
                save_db(st.session_state["db_path"], st.session_state["db"])
                st.sidebar.success("가져오기 완료!")
            else:
                st.sidebar.error("JSON 형식이 올바르지 않아요.")
        except Exception as e:
            st.sidebar.error(f"가져오기 실패: {e}")


def main_ui() -> None:
    st.title("PT SOAP 도우미 (실습생용)")
    st.caption("입력은 사실입니다. AI가 S/O 재서술 + A/P 초안을 작성합니다. (최종 검토는 반드시 지도자/면허자 확인)")

    # 모드
    mode = st.radio(
        "출력 모드",
        ["제출용(깔끔/무난)", "상세 플랜(구체/전문)"],
        index=0 if st.session_state["mode"] == "제출용" else 1,
        horizontal=True,
    )
    st.session_state["mode"] = "제출용" if mode.startswith("제출용") else "상세"

    st.markdown("---")
    st.header("입력(사실만 작성)")

    c1, c2 = st.columns([1, 1])
    with c1:
        st.session_state["body_part"] = st.selectbox("부위(선택)", BODY_PARTS, index=BODY_PARTS.index(st.session_state["body_part"]) if st.session_state["body_part"] in BODY_PARTS else 0)
    with c2:
        st.session_state["body_part_free"] = st.text_input("부위(직접입력)", value=st.session_state["body_part_free"], placeholder="예) 어깨, 목, 무릎 등")

    # 입력 라벨(입주자/생활환경 같은 말 절대 안 씀)
    st.session_state["s_text"] = st.text_area(
        "환자 호소/상황(주관적 정보)",
        value=st.session_state["s_text"],
        height=90,
        placeholder="예) 2/13부터 어깨가 아프고, 팔을 위로 들면 더 아프고 밤에 불편해요.",
    )
    st.session_state["o_text"] = st.text_area(
        "관찰/평가(객관적 정보)",
        value=st.session_state["o_text"],
        height=90,
        placeholder="예) 어깨 외전 90° 부근에서 통증 증가, 가동범위 제한 및 특정 동작에서 통증 재현.",
    )

    st.markdown("---")
    st.subheader("상세 안내(선택)")
    c3, c4 = st.columns([1, 1])
    with c3:
        st.session_state["stimulus"] = st.selectbox("자극감도(대략)", STIMULUS_LEVELS, index=STIMULUS_LEVELS.index(st.session_state["stimulus"]) if st.session_state["stimulus"] in STIMULUS_LEVELS else 0)
    with c4:
        st.session_state["treat_freq"] = st.selectbox("치료/세션(권장)", TREAT_FREQ, index=TREAT_FREQ.index(st.session_state["treat_freq"]) if st.session_state["treat_freq"] in TREAT_FREQ else 1)

    c5, c6 = st.columns([1, 1])
    with c5:
        st.session_state["exer_freq"] = st.selectbox("운동 빈도(권장)", EXER_FREQ, index=EXER_FREQ.index(st.session_state["exer_freq"]) if st.session_state["exer_freq"] in EXER_FREQ else 2)
    with c6:
        st.session_state["follow_up"] = st.selectbox("재평가/팔로업", FOLLOW_UP, index=FOLLOW_UP.index(st.session_state["follow_up"]) if st.session_state["follow_up"] in FOLLOW_UP else 1)

    st.session_state["barriers"] = st.multiselect(
        "장애요인(선택한 항목으로 P를 더 많이 활용)",
        BARRIERS,
        default=[b for b in st.session_state["barriers"] if b in BARRIERS],
    )

    st.markdown("---")
    st.header("실행")

    colA, colB = st.columns([1, 1])
    with colA:
        gen = st.button("S/O 재작성 + A/P 생성", use_container_width=True)
    with colB:
        reset = st.button("초기화(캐시/선택 초기화)", use_container_width=True)

    if reset:
        st.session_state["body_part"] = "기타(직접입력)"
        st.session_state["body_part_free"] = ""
        st.session_state["s_text"] = ""
        st.session_state["o_text"] = ""
        st.session_state["stimulus"] = "불명"
        st.session_state["treat_freq"] = "주 2회"
        st.session_state["exer_freq"] = "주 5-6회"
        st.session_state["follow_up"] = "2주"
        st.session_state["barriers"] = []
        st.session_state["soap_out"] = {"S": "", "O": "", "A": "", "P": ""}
        st.success("초기화 완료")

    if gen:
        # 입력 정리
        inp = SoapInput(
            mode=st.session_state["mode"],
            body_part=normalize_text(st.session_state["body_part"]),
            body_part_free=normalize_text(st.session_state["body_part_free"]),
            s_text=normalize_text(st.session_state["s_text"]),
            o_text=normalize_text(st.session_state["o_text"]),
            stimulus=normalize_text(st.session_state["stimulus"]),
            treat_freq=normalize_text(st.session_state["treat_freq"]),
            exer_freq=normalize_text(st.session_state["exer_freq"]),
            follow_up=normalize_text(st.session_state["follow_up"]),
            barriers=[normalize_text(x) for x in st.session_state["barriers"]],
        )

        # 빈 입력 방지(최소한의 가드)
        if not inp.s_text.strip() or not inp.o_text.strip():
            st.warning("S(주관)와 O(객관)는 최소 1줄 이상 입력해 주세요.")
        else:
            prompt = build_prompt(inp)

            with st.spinner("AI가 SOAP을 생성 중..."):
                txt = call_openai(prompt)
                if txt is None:
                    # 폴백
                    txt = fallback_generate(inp)

                soap = parse_soap(txt)
                soap = ensure_p_not_empty(inp, soap)

                # 금칙어 최종 방지(출력 전 마지막 정리)
                soap = {k: normalize_text(v) for k, v in soap.items()}
                st.session_state["soap_out"] = soap
                st.session_state["last_generate_at"] = time.time()

            st.success("생성 완료! (반드시 지도자/면허자의 최종 검토를 거치세요.)")

    # 결과 표시
    st.markdown("---")
    st.subheader("AI 정리 결과(S/O/A/P)")

    out = st.session_state["soap_out"]
    if any((out.get("S", ""), out.get("O", ""), out.get("A", ""), out.get("P", ""))):
        st.markdown("**S:**")
        st.write(out.get("S", "").strip() or "—")

        st.markdown("**O:**")
        st.write(out.get("O", "").strip() or "—")

        st.markdown("**A:**")
        st.write(out.get("A", "").strip() or "—")

        st.markdown("**P:**")
        p = out.get("P", "").strip()
        if p:
            # 줄바꿈 유지
            st.code(p, language="text")
        else:
            st.error("P가 비어 있습니다(이 경우는 설계상 거의 없어야 합니다).")

        st.markdown("---")
        # 저장
        if st.button("이 결과를 기록으로 저장", use_container_width=True):
            save_current_note()
    else:
        st.info("아직 생성된 결과가 없습니다.")


def save_current_note() -> None:
    db = st.session_state["db"]
    notes = db.get("notes", [])
    soap = st.session_state["soap_out"]

    body = st.session_state["body_part_free"].strip() if st.session_state["body_part"] == "기타(직접입력)" else st.session_state["body_part"]
    body = normalize_text(body) or "부위 불명"

    title = f"{body} | {st.session_state['mode']}"

    note = {
        "id": hashlib.sha1(f"{time.time()}-{title}".encode("utf-8")).hexdigest()[:10],
        "title": title,
        "created_at": now_str(),
        "mode": st.session_state["mode"],
        "body_part": normalize_text(st.session_state["body_part"]),
        "body_part_free": normalize_text(st.session_state["body_part_free"]),
        "stimulus": normalize_text(st.session_state["stimulus"]),
        "treat_freq": normalize_text(st.session_state["treat_freq"]),
        "exer_freq": normalize_text(st.session_state["exer_freq"]),
        "follow_up": normalize_text(st.session_state["follow_up"]),
        "barriers": [normalize_text(x) for x in st.session_state["barriers"]],
        # 입력 원문
        "S_in": normalize_text(st.session_state["s_text"]),
        "O_in": normalize_text(st.session_state["o_text"]),
        # 출력
        "S": normalize_text(soap.get("S", "")),
        "O": normalize_text(soap.get("O", "")),
        "A": normalize_text(soap.get("A", "")),
        "P": normalize_text(soap.get("P", "")),
    }

    notes.append(note)
    db["notes"] = notes
    st.session_state["db"] = db
    save_db(st.session_state["db_path"], db)
    st.success("저장 완료!")


def harden_ui_strings() -> None:
    """앱 시작 시, 선택지/라벨에 오염이 남아있지 않도록 1차 점검(자동 치유)."""
    # 선택지 자체를 다시 정리(혹시 이전 캐시/세션 상태로 오염되었을 때 대비)
    st.session_state["body_part"] = normalize_text(st.session_state.get("body_part", "기타(직접입력)"))
    if st.session_state["body_part"] not in BODY_PARTS:
        st.session_state["body_part"] = "기타(직접입력)"

    st.session_state["stimulus"] = normalize_text(st.session_state.get("stimulus", "불명"))
    if st.session_state["stimulus"] not in STIMULUS_LEVELS:
        st.session_state["stimulus"] = "불명"

    # 멀티셀렉트 오염 제거
    current_barriers = st.session_state.get("barriers", [])
    if isinstance(current_barriers, list):
        st.session_state["barriers"] = [b for b in (normalize_text(x) for x in current_barriers) if b in BARRIERS]
    else:
        st.session_state["barriers"] = []

    # 입력 텍스트 정리
    for k in ["s_text", "o_text", "body_part_free"]:
        st.session_state[k] = normalize_text(st.session_state.get(k, ""))


def run() -> None:
    st.set_page_config(page_title="PT SOAP 도우미", page_icon="📝", layout="wide")

    init_state()
    harden_ui_strings()

    sidebar_notes()
    main_ui()


if __name__ == "__main__":
    run()
