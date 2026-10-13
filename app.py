import streamlit as st
import json
import time
import glob
from fpdf import FPDF
import google.generativeai as genai

# --- НАСТРОЙКА СТРАНИЦЫ ---
st.set_page_config(page_title="AML Агент - РК", page_icon="🛡️", layout="wide")

# --- КЭШИРОВАНИЕ БАЗЫ ДАННЫХ (УСКОРЕНИЕ РАБОТЫ) ---
@st.cache_data(show_spinner=False)
def load_courses_db():
    """Загружает JSON один раз и держит в памяти, чтобы не тормозить приложение."""
    try:
        with open("courses.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return "error"

# --- ФУНКЦИЯ ГЕНЕРАЦИИ СЕРТИФИКАТА ---
def create_pdf_certificate(course_name, student_name="Talgat Omirzhanov"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 20, "CERTIFICATE OF COMPLETION", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 14)
    pdf.cell(0, 10, f"Awarded to: {student_name}", align="C", new_x="LMARGIN", new_y="NEXT")
    
    safe_course_name = course_name.encode('ascii', 'ignore').decode('ascii')
    if not safe_course_name.strip():
        safe_course_name = "AML & Compliance Training"
        
    pdf.cell(0, 10, f"Course: {safe_course_name}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 10, "Status: Successfully completed all modules and tests.", align="C")
    
    # ИСПРАВЛЕНИЕ: Вызываем output() без устаревшего dest="S" и конвертируем напрямую в bytes
    return bytes(pdf.output())

# --- ИНИЦИАЛИЗАЦИЯ ПАМЯТИ ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "gemini_files" not in st.session_state:
    st.session_state.gemini_files = []
if "uploaded_file_names" not in st.session_state:
    st.session_state.uploaded_file_names = set()
if "current_module" not in st.session_state:
    st.session_state.current_module = 1
if "course_passed" not in st.session_
