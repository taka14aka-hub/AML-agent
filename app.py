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
        return None, f"Ошибка JSON в `{COURSES
