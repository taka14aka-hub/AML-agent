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

st.markdown(
    """<style>
    .stCheckbox label span, .stRadio label span { 
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
COURSES_PATH = os.path.join("data", "courses.json")
PROGRESS_PATH = os.path.join("data", "progress.json")
MEMORY_PATH = "rules_and_memory.txt"

PASS_RATIO = 1.0                
SHOW_ANSWER_AFTER_ATTEMPTS = 2  
MAX_HISTORY_MESSAGES = 12       
DOCS_TTL_SECONDS = 40 * 3600    
PROGRESS_TTL_SECONDS = 24 * 3600 # 24 часа для сохранения прогресса

# ---------------------------------------------------------------------
# ДАННЫЕ КУРСОВ
# ---------------------------------------------------------------------
def validate_courses(data) -> list:
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

            minitest = module.get("Мини_тест")
            if not isinstance(minitest, list) or len(minitest) != 3:
                problems.append(f"{where}: массив «Мини_тест» должен содержать ровно 3 вопроса.")
            else:
                for i, mq in enumerate(minitest, 1):
                    w_mini = f"{where}, мини-тест {i}"
                    m_options = mq.get("Варианты", [])
                    if len(m_options) != 3:
                        problems.append(f"{w_mini}: должно быть ровно 3 варианта ответа.")

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
                
                corrects = q.get("Правильные_варианты")
                if not isinstance(corrects, list) or not corrects or not all(isinstance(c, int) and 1 <= c <= len(options) for c in corrects):
                    problems.append(f"{w}: «Правильные_варианты» должен быть списком чисел от 1 до {len(options)}.")
    return problems

@st.cache_data(show_spinner=False)
def load_courses_db():
    try:
        with open(COURSES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None, f"Файл `{COURSES_PATH}` не найден. Убедитесь, что он лежит в папке data."
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
    pdf.cell(0, 14, "СЕРТИФИКАТ О ПРОХОЖДЕНИИ", align="C", new_x="
