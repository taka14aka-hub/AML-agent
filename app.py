import glob
import hashlib
import json
import math
import os
import re
import time
from datetime import datetime

import google.generativeai as genai
import streamlit as st
from fpdf import FPDF

st.set_page_config(page_title="AML Агент - РК", page_icon="🛡️", layout="wide")

# Принудительный перенос текста для длинных ответов
st.markdown(
    """<style>
    .stCheckbox label span { 
        white-space: normal !important; 
        word-break: break-word; 
    }
    </style>""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------
# КОНСТАНТЫ
# ---------------------------------------------------------------------
FONT_CANDIDATES = ["Roboto_Condensed-Regular.ttf"]
FONT_PATH = next((p for p in FONT_CANDIDATES if os.path.exists(p)), FONT_CANDIDATES[0])
COURSES_PATH = "courses.json"
MEMORY_PATH = "rules_and_memory.txt"

PASS_RATIO = 1.0                # доля верных ответов для зачёта модуля (1.0 = все, 0.67 = 2 из 3)
SHOW_ANSWER_AFTER_ATTEMPTS = 2  # после скольких неудач показывать правильный ответ

MAX_HISTORY_MESSAGES = 12       # сколько последних реплик уходит в модель
DOCS_TTL_SECONDS = 40 * 3600    # файлы Gemini живут 48 ч, обновляем раньше


# ---------------------------------------------------------------------
# ДАННЫЕ КУРСОВ
# ---------------------------------------------------------------------
def validate_courses(data) -> list:
    """Проверяет структуру courses.json и возвращает список проблем."""
    if not isinstance(data, dict) or not data:
        return ["Файл должен содержать объект с курсами."]

    problems = []
    for course, modules in data.items():
        if not isinstance(modules, dict) or not modules:
            problems.append(f"Курс «{course}»: нет модулей.")
            continue

        for num in range(1, len(modules) + 1):
            where = f"«{course}», модуль {num}"
            module = modules.get(str(num))
            if not isinstance(module, dict):
                problems.append(f"{where}: нет модуля (номера должны идти подряд: 1, 2, 3...).")
                continue
            if not module.get("Теория"):
                problems.append(f"{where}: пустая «Теория».")

            questions = module.get("Вопросы")
            if not isinstance(questions, list) or not questions:
                problems.append(f"{where}: нет списка «Вопросы».")
                continue

            for i, q in enumerate(questions, 1):
                w = f"{where}, вопрос {i}"
                if not isinstance(q, dict):
                    problems.append(f"{w}: вопрос должен быть объектом.")
                    continue
                if not q.get("Вопрос"):
                    problems.append(f"{w}: пустой текст «Вопрос».")
                options = q.get("Варианты")
                if not isinstance(options, list) or len(options) < 2:
                    problems.append(f"{w}: в «Варианты» должно быть минимум 2 варианта.")
                    continue
                if len(set(options)) != len(options):
                    problems.append(f"{w}: варианты ответов повторяются.")
                
                corrects = q.get("Правильные_варианты")
                if not isinstance(corrects, list) or not corrects or not all(isinstance(c, int) and 1 <= c <= len(options) for c in corrects):
                    problems.append(
                        f"{w}: «Правильные_варианты» должен быть списком чисел от 1 до {len(options)}."
                    )
    return problems


@st.cache_data(show_spinner=False)
def load_courses_db():
    """Возвращает (данные, текст_ошибки)."""
    try:
        with open(COURSES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None, f"Файл `{COURSES_PATH}` не найден."
    except json.JSONDecodeError as e:
        return None, f"Ошибка JSON в `{COURSES_PATH}`: {e}"

    problems = validate_courses(data)
    if problems:
        shown = "\n".join(f"- {p}" for p in problems[:15])
        return None, f"Ошибки в `{COURSES_PATH}`:\n\n{shown}"
    return data, None


# ---------------------------------------------------------------------
# СЕРТИФИКАТ
# ---------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def build_certificate(course_name: str, student_name: str, date_str: str) -> bytes:
    """Кэшируется: не пересобирается при каждом rerun Streamlit."""
    if not os.path.exists(FONT_PATH):
        raise FileNotFoundError(f"Нет шрифта {FONT_PATH}")

    cert_id = hashlib.sha256(
        f"{student_name}|{course_name}|{date_str}".encode("utf-8")
    ).hexdigest()[:12].upper()

    pdf = FPDF(orientation="L", format="A4")
    pdf.add_font("Roboto", "", FONT_PATH)
    pdf.add_page()
    pdf.set_line_width(0.8)
    pdf.rect(10, 10, pdf.w - 20, pdf.h - 20)

    pdf.set_y(35)
    pdf.set_font("Roboto", "", 26)
    pdf.cell(0, 14, "СЕРТИФИКАТ О ПРОХОЖДЕНИИ", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 14, "ОҚУДЫ АЯҚТАҒАНЫ ТУРАЛЫ СЕРТИФИКАТ", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)

    pdf.set_font("Roboto", "", 16)
    pdf.cell(0, 10, "Выдан / Берілді:", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Roboto", "", 22)
    pdf.cell(0, 14, student_name, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Roboto", "", 16)
    pdf.multi_cell(0, 9, f"Курс: {course_name}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Roboto", "", 13)
    pdf.multi_cell(
        0, 8,
        "Успешно завершил(а) все модули и тесты.\n"
        "Барлық модульдер мен тесттерді сәтті аяқтады.",
        align="C", new_x="LMARGIN", new_y="NEXT",
    )

    pdf.set_y(-35)
    pdf.set_font("Roboto", "", 11)
    pdf.cell(0, 8, f"Дата / Күні: {date_str}   |   № {cert_id}", align="C")
    return bytes(pdf.output())


# ---------------------------------------------------------------------
# СОСТОЯНИЕ
# ---------------------------------------------------------------------
DEFAULTS = {
    "messages": [],
    "current_module": 1,
    "course_passed": False,
    "attempts": {},
}
for key, value in DEFAULTS.items():
    st.session_state.setdefault(key, value)


def reset_progress():
    st.session_state.current_module = 1
    st.session_state.course_passed = False
    st.session_state.attempts = {}
    st.session_state.pop("flash", None)
    for k in [k for k in st.session_state if str(k).startswith("q_")]:
        del st.session_state[k]


# ---------------------------------------------------------------------
# РЕЖИМ 1: ТРЕНАЖЕР-ТЕСТ (ОФЛАЙН)
# ---------------------------------------------------------------------
def render_trainer():
    st.title("🎓 Тренажер по комплаенсу")
    st.caption("⚡ Работает автономно. Не расходует лимиты API.")

    courses_db, error = load_courses_db()
    if error:
        st.error(error)
        st.stop()

    course_topic = st.selectbox("Выберите курс для изучения:", list(courses_db.keys()))

    if st.session_state.get("_course_seen") != course_topic:
        st.session_state["_course_seen"] = course_topic
        reset_progress()

    course_data = courses_db[course_topic]
    total = len(course_data)

    if st.session_state.course_passed:
        render_certificate(course_topic)
        return

    cur = st.session_state.current_module
    module = course_data[str(cur)]
    questions = module["Вопросы"]

    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)

    st.progress((cur - 1) / total, text=f"Модуль {cur} из {total}")
    st.markdown(module["Теория"])
    
    if "Кейсы" in module:
        st.markdown("### Практические кейсы")
        for idx, case in enumerate(module["Кейсы"], 1):
            with st.expander(f"Кейс {idx}: {case.get('Название', 'Без названия')}"):
                st.markdown(f"**Что произошло:** {case.get('Что произошло', '')}")
                if "Что можно было заметить" in case:
                    st.markdown(f"**Что можно было заметить:** {case.get('Что можно было заметить', '')}")
                st.markdown(f"**Урок для комплаенса:** {case.get('Урок для комплаенса', '')}")
                if "Источник" in case:
                    st.caption(f"Источник: {case.get('Источник', '')}")

    st.markdown("### Проверочный тест")
    st.caption(f"Отметьте **все верные варианты** в каждом вопросе. Для зачёта нужно верно ответить "
               f"минимум на {math.ceil(len(questions) * PASS_RATIO)} из {len(questions)}.")

    def qkey(i: int) -> str:
        return f"q_{course_topic}_{cur}_{i}"

    with st.form(f"form_{course_topic}_{cur}"):
        for i, q in enumerate(questions, 1):
            st.markdown(f"**{i}. {q['Вопрос']}**")
            # Используем чекбоксы вместо выпадающего списка
            for j, option in enumerate(q["Варианты"]):
                st.checkbox(option, key=f"{qkey(i)}_{j}")
            st.write("") # Небольшой отступ между вопросами

        submitted = st.form_submit_button("Проверить ответы")

    if submitted:
        check_quiz(course_topic, cur, total, questions, qkey)


def check_quiz(course_topic, cur, total, questions, qkey):
    # Сбор выбранных чекбоксов для каждого вопроса
    answers = []
    for i, q in enumerate(questions, 1):
        selected_options = []
        for j, option in enumerate(q["Варианты"]):
            if st.session_state.get(f"{qkey(i)}_{j}"):
                selected_options.append(option)
        answers.append(selected_options)

    # Проверка, что на каждый вопрос дан хотя бы один ответ
    missing = [str(i) for i, a in enumerate(answers, 1) if not a]
    if missing:
        st.warning("Ответьте на все вопросы. Нет ответа на: " + ", ".join(missing))
        return

    attempt_key = f"{course_topic}:{cur}"
    attempts = st.session_state.attempts.get(attempt_key, 0) + 1
    st.session_state.attempts[attempt_key] = attempts

    results = []
    for q, answer_list in zip(questions, answers):
        correct_indices = q["Правильные_варианты"]
        correct_texts = [q["Варианты"][idx - 1] for idx in correct_indices]
        
        is_correct = set(answer_list) == set(correct_texts)
        results.append((is_correct, "\n- ".join([""] + correct_texts), q.get("Пояснение", "")))

    score = sum(ok for ok, _, _ in results)
    required = math.ceil(len(questions) * PASS_RATIO)

    if score >= required:
        st.session_state.flash = f"✅ Модуль {cur} пройден: {score} из {len(questions)}."
        if cur >= total:
            st.session_state.course_passed = True
        else:
            st.session_state.current_module += 1
        st.rerun()

    st.markdown(f"### Результат: {score} из {len(questions)}")
    for i, (ok, correct_texts_str, explanation) in enumerate(results, 1):
        if ok:
            st.success(f"Вопрос {i}: верно.")
        else:
            text = f"Вопрос {i}: неверно. Перечитайте теорию и попробуйте снова."
            if attempts >= SHOW_ANSWER_AFTER_ATTEMPTS:
                text += f"\n\n**Правильные ответы:** {correct_texts_str}"
