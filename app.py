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
FONT_PATH = "fonts/Roboto-Regular.ttf"  # положите шрифт в репозиторий
COURSES_PATH = "courses.json"
MEMORY_PATH = "rules_and_memory.txt"
MIN_ANSWER_WORDS = 8          # защита от ответа в одно слово
HINT_AFTER_ATTEMPTS = 3       # термины показываем только после N неудач
MAX_HISTORY_MESSAGES = 12     # сколько последних реплик уходит в модель
DOCS_TTL_SECONDS = 40 * 3600  # файлы Gemini живут 48 ч, обновляем раньше


# ---------------------------------------------------------------------
# ДАННЫЕ
# ---------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_courses_db():
    """Возвращает (данные, текст_ошибки)."""
    try:
        with open(COURSES_PATH, "r", encoding="utf-8") as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, f"Файл `{COURSES_PATH}` не найден."
    except json.JSONDecodeError as e:
        return None, f"Ошибка JSON в `{COURSES_PATH}`: {e}"


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("ё", "е")).strip()


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


# ---------------------------------------------------------------------
# РЕЖИМ 1: ТРЕНАЖЕР (ОФЛАЙН)
# ---------------------------------------------------------------------
def check_answer(answer: str, keywords: list):
    """Возвращает (принято, найдено, нужно)."""
    if len(answer.split()) < MIN_ANSWER_WORDS:
        return False, 0, len(keywords)
    if not keywords:
        return True, 0, 0
    text = normalize(answer)
    matched = [kw for kw in keywords if normalize(kw) in text]
    required = max(1, math.ceil(len(keywords) / 2))
    return len(matched) >= required, len(matched), required


def render_trainer():
    st.title("🎓 Тренажер по комплаенсу")
    st.caption("⚡ Работает автономно. Не расходует лимиты API.")

    courses_db, error = load_courses_db()
    if error:
        st.error(error)
        st.stop()

    course_topic = st.selectbox("Выберите курс для изучения:", list(courses_db.keys()))

    # Сброс прогресса при смене курса
    if st.session_state.get("_course_seen") != course_topic:
        st.session_state["_course_seen"] = course_topic
        reset_progress()

    course_data = courses_db[course_topic]
    total = len(course_data)

    if st.session_state.course_passed:
        render_certificate(course_topic)
        return

    cur = st.session_state.current_module
    module = course_data.get(str(cur))
    if not module:
        st.error(f"Модуль {cur} не найден в JSON.")
        st.stop()

    st.progress((cur - 1) / total, text=f"Модуль {cur} из {total}")
    st.markdown(module.get("Теория", "Теория в разработке."))

    questions = module.get("Вопросы", [])
    if questions:
        st.markdown("### Проверочные вопросы")
        st.markdown("\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1)))

    # key привязан к модулю: ответ не «переезжает» в следующий модуль
    answer = st.text_area("Введите ваши ответы:", key=f"answer_{course_topic}_{cur}")

    if st.button("Отправить на проверку"):
        keywords = module.get("Ключевые_слова", [])
        ok, found, required = check_answer(answer, keywords)

        if ok:
            st.toast("✅ Принято!")
            if cur >= total:
                st.session_state.course_passed = True
            else:
                st.session_state.current_module += 1
            st.rerun()

        attempt_key = f"{course_topic}:{cur}"
        attempts = st.session_state.attempts.get(attempt_key, 0) + 1
        st.session_state.attempts[attempt_key] = attempts

        st.error("❌ Ответ неполный или неточный.")
        if len(answer.split()) < MIN_ANSWER_WORDS:
            st.warning(f"Дайте развёрнутый ответ (минимум {MIN_ANSWER_WORDS} слов).")
        else:
            st.warning(f"Раскрыто ключевых понятий: {found} из {required} необходимых.")
        if attempts >= HINT_AFTER_ATTEMPTS and keywords:
            st.info("💡 Подсказка, термины темы: " + ", ".join(keywords))


def render_certificate(course_topic: str):
    st.success("🎉 Вы успешно завершили все модули курса.")
    student_name = st.text_input(
        "Имя и фамилия для сертификата:", placeholder="Например: Азамат Сериков"
    ).strip()

    if student_name:
        try:
            pdf_bytes = build_certificate(
                course_topic, student_name, datetime.now().strftime("%d.%m.%Y")
            )
            safe_name = re.sub(r"[^\w\-]+", "_", student_name)
            st.download_button(
                "📥 Скачать сертификат (PDF)",
                data=pdf_bytes,
                file_name=f"Certificate_{safe_name}.pdf",
                mime="application/pdf",
            )
        except FileNotFoundError as e:
            st.error(f"Не удалось создать сертификат: {e}")
    else:
        st.info("👆 Введите имя, чтобы появилась кнопка скачивания.")

    st.divider()
    if st.button("Начать новый курс"):
        reset_progress()
        st.rerun()


# ---------------------------------------------------------------------
# РЕЖИМ 2: АУДИТ / АРРФР (GEMINI)
# ---------------------------------------------------------------------
@st.cache_resource(ttl=DOCS_TTL_SECONDS, show_spinner="Синхронизация документов...")
def upload_documents():
    """Один раз на всё приложение (а не на каждую сессию пользователя)."""
    files = []
    for path in sorted(glob.glob("*.pdf")):
        f = genai.upload_file(path=path)
        while f.state.name == "PROCESSING":
            time.sleep(2)
            f = genai.get_file(f.name)
        if f.state.name == "ACTIVE":
            files.append(f)
        else:
            st.warning(f"Файл {path} не обработан (статус {f.state.name}).")
    return files


def build_contents(doc_files, messages):
    """Документы + история диалога, чтобы модель помнила контекст."""
    contents = []
    if doc_files:
        contents.append({"role": "user", "parts": [*doc_files, "Это нормативная база. Опирайся на неё."]})
        contents.append({"role": "model", "parts": ["Принято."]})
    for m in messages[-MAX_HISTORY_MESSAGES:]:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [m["content"]]})
    return contents


def render_online(task_mode: str):
    st.title("🛡️ ИИ-Агент по AML Комплаенсу (РК)")

    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    except KeyError:
        st.error("API-ключ `GEMINI_API_KEY` не найден в secrets.")
        st.stop()

    model_name = st.secrets.get("GEMINI_MODEL", "gemini-3.1-pro-preview")
    st.sidebar.success("API ключ подключен 🟢")
    st.sidebar.caption(f"Модель: {model_name}")

    st.subheader("📂 Нормативная база")
    try:
        doc_files = upload_documents()
    except Exception as e:
        st.error(f"Ошибка загрузки документов: {e}")
        doc_files = []
    if doc_files:
        st.success(f"Документов в памяти ИИ: {len(doc_files)}")
    else:
        st.info("Нет PDF-файлов. Положите их в корень репозитория.")

    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            long_term_memory = f.read()
    except FileNotFoundError:
        long_term_memory = ""

    mode_instructions = (
        "Твоя задача — аудит ПВК. Ищи риски, уязвимости и несоответствия законам РК. "
        "Предлагай конкретные формулировки."
        if task_mode == "Аудит ПВК и регламентов"
        else "Твоя задача — подготовка ответа для АРРФР. Защищай интересы МФО, ссылайся на нормы права, "
             "пиши в строгом деловом стиле."
    )
    system_instruction = (
        "Ты — ведущий ИИ-методолог по AML в Казахстане.\n"
        f"{long_term_memory}\n"
        f"ТЕКУЩАЯ ЗАДАЧА: {mode_instructions}\n"
        "ПРАВИЛА: ссылайся на конкретные документы и статьи из загруженной базы. "
        "Если нормы нет в базе или ты не уверен в ней — прямо скажи об этом, не выдумывай номера статей и цитаты. "
        "В конце отмечай, что вывод требует проверки ответственным сотрудником."
    )

    st.divider()
    st.subheader(f"💬 Рабочий чат ({task_mode})")

    # История привязана к режиму, чтобы аудит и ответы АРРФР не смешивались
    if st.sidebar.button("🧹 Очистить чат"):
        st.session_state.messages = []
        st.rerun()

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if prompt := st.chat_input("Опишите задачу или вставьте выдержку из документа..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Анализирую..."):
                try:
                    model = genai.GenerativeModel(model_name=model_name, system_instruction=system_instruction)
                    response = model.generate_content(build_contents(doc_files, st.session_state.messages))
                    text = response.text
                except ValueError:
                    text = "⚠️ Модель не вернула текст (возможно, сработал фильтр). Переформулируйте запрос."
                except Exception as e:
                    text = f"⚠️ Ошибка API: {e}"
            st.markdown(text)
        st.session_state.messages.append({"role": "assistant", "content": text})


# ---------------------------------------------------------------------
# ТОЧКА ВХОДА
# ---------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Настройки и Статус")
    task_mode = st.selectbox(
        "Режим работы:",
        ("🎓 Обучающий тренажер (Офлайн)", "Аудит ПВК и регламентов", "Ответ на запрос/жалобу АРРФР"),
    )
    st.divider()

# при смене режима чат не тянем из другого режима
if st.session_state.get("_mode_seen") != task_mode:
    st.session_state["_mode_seen"] = task_mode
    st.session_state.messages = []

if task_mode.startswith("🎓"):
    render_trainer()
else:
    render_online(task_mode)
    
