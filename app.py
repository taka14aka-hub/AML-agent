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
# СОСТОЯНИЕ И СОХРАНЕНИЕ ПРОГРЕССА
# ---------------------------------------------------------------------
DEFAULTS = {
    "messages": [],
    "current_module": 1,
    "module_phase": "theory", 
    "course_passed": False,
    "attempts": {},
    "student_name": None,
    "_course_seen": None
}
for key, value in DEFAULTS.items():
    st.session_state.setdefault(key, value)

def get_all_progress():
    if os.path.exists(PROGRESS_PATH):
        try:
            with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_user_progress():
    """Сохраняет текущий прогресс пользователя в JSON файл."""
    if not st.session_state.student_name:
        return
    
    os.makedirs(os.path.dirname(PROGRESS_PATH), exist_ok=True)
    prog = get_all_progress()
    prog[st.session_state.student_name] = {
        "course_topic": st.session_state._course_seen,
        "current_module": st.session_state.current_module,
        "module_phase": st.session_state.module_phase,
        "course_passed": st.session_state.course_passed,
        "timestamp": time.time()
    }
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(prog, f, ensure_ascii=False, indent=2)

def load_user_progress(student_name: str) -> bool:
    """Загружает прогресс. Возвращает True, если есть свежий прогресс."""
    prog = get_all_progress()
    user_data = prog.get(student_name)
    if user_data:
        # Проверяем не истек ли срок (24 часа)
        if time.time() - user_data.get("timestamp", 0) > PROGRESS_TTL_SECONDS:
            return False 
        
        st.session_state._course_seen = user_data.get("course_topic")
        st.session_state.current_module = user_data.get("current_module", 1)
        st.session_state.module_phase = user_data.get("module_phase", "theory")
        st.session_state.course_passed = user_data.get("course_passed", False)
        return True
    return False

def reset_progress(clear_user=False):
    st.session_state.current_module = 1
    st.session_state.module_phase = "theory"
    st.session_state.course_passed = False
    st.session_state.attempts = {}
    st.session_state.pop("flash", None)
    for k in [k for k in st.session_state if str(k).startswith("q_") or str(k).startswith("mini_")]:
        del st.session_state[k]
    if clear_user:
        st.session_state.student_name = None
        st.session_state._course_seen = None
    else:
        save_user_progress() # Перезаписываем сброшенный прогресс в файл

# ---------------------------------------------------------------------
# АВТОРИЗАЦИЯ
# ---------------------------------------------------------------------
def render_login():
    st.title("🎓 Вход в Тренажер по комплаенсу")
    st.info("ℹ️ Пожалуйста, введите ваше ФИО. Если вы случайно закроете вкладку или отключится интернет, ваш прогресс сохранится на 24 часа.")
    
    with st.form("login_form"):
        name_input = st.text_input("Ваше ФИО (Имя и Фамилия):", placeholder="Например: Азамат Сериков")
        submitted = st.form_submit_button("Начать обучение")
        
        if submitted:
            if len(name_input.strip()) > 3:
                st.session_state.student_name = name_input.strip()
                if load_user_progress(st.session_state.student_name):
                    st.success(f"С возвращением, {st.session_state.student_name}! Прогресс восстановлен.")
                    time.sleep(1)
                else:
                    reset_progress(clear_user=False)
                st.rerun()
            else:
                st.error("Пожалуйста, введите корректное имя.")

# ---------------------------------------------------------------------
# РЕЖИМ 1: ТРЕНАЖЕР-ТЕСТ (ОФЛАЙН)
# ---------------------------------------------------------------------
def render_trainer():
    st.title("🎓 Тренажер по комплаенсу")
    
    # Кнопка выхода из профиля
    col1, col2 = st.columns([8, 2])
    with col1:
        st.caption(f"👤 Ученик: **{st.session_state.student_name}** | ⚡ Автоматическое сохранение прогресса")
    with col2:
        if st.button("Выйти из профиля", use_container_width=True):
            reset_progress(clear_user=True)
            st.rerun()

    courses_db, error = load_courses_db()
    if error:
        st.error(error)
        st.stop()

    course_topic = st.selectbox("Выберите курс для изучения:", list(courses_db.keys()), index=list(courses_db.keys()).index(st.session_state._course_seen) if st.session_state._course_seen in courses_db else 0)

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
    
    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)

    st.progress((cur - 1) / total, text=f"Модуль {cur} из {total}")

    # ФАЗА 1: Обучение и мини-тест
    if st.session_state.module_phase == "theory":
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

        st.divider()
        st.warning("⚠️ **Внимание!** После перехода к основному тесту вернуться к теории будет нельзя. Рекомендуем внимательно ознакомиться с материалом.")
        st.markdown("### Мини-тест для допуска к экзамену")
        
        minitest = module["Мини_тест"]
        def mkey(i: int) -> str:
            return f"mini_{course_topic}_{cur}_{i}"

        with st.form(f"mini_form_{course_topic}_{cur}"):
            for i, mq in enumerate(minitest, 1):
                st.markdown(f"**{i}. {mq['Вопрос']}**")
                st.radio(
                    f"Ответ на мини-вопрос {i}",
                    mq["Варианты"],
                    index=None,
                    key=mkey(i),
                    label_visibility="collapsed"
                )
                st.write("")
            mini_submitted = st.form_submit_button("Пройти мини-тест и начать экзамен")

        if mini_submitted:
            mini_answers = [st.session_state.get(mkey(i)) for i in range(1, 4)]
            if None in mini_answers:
                st.error("Пожалуйста, ответьте на все 3 вопроса мини-теста.")
            else:
                correct_count = 0
                for i, (mq, ans) in enumerate(zip(minitest, mini_answers)):
                    correct_idx = mq["Правильные_варианты"][0] - 1
                    if ans == mq["Варианты"][correct_idx]:
                        correct_count += 1
                
                if correct_count == 3:
                    st.session_state.module_phase = "test"
                    st.session_state.flash = "Допуск получен! Успешной сдачи основного экзамена."
                    save_user_progress() # Автосохранение
                    st.rerun()
                else:
                    st.error(f"Мини-тест не пройден ({correct_count} из 3). Внимательно перечитайте теорию и попробуйте снова.")

    # ФАЗА 2: Основной тест
    elif st.session_state.module_phase == "test":
        st.info("📚 Режим тестирования. Возврат к теории закрыт.")
        st.markdown(f"### Экзамен: Модуль {cur}")
        
        questions = module["Вопросы"]
        st.caption(f"Отметьте **все верные варианты** в каждом вопросе. Для зачёта нужно верно ответить "
                   f"минимум на {math.ceil(len(questions) * PASS_RATIO)} из {len(questions)}.")

        def qkey(i: int) -> str:
            return f"q_{course_topic}_{cur}_{i}"

        with st.form(f"form_{course_topic}_{cur}"):
            for i, q in enumerate(questions, 1):
                st.markdown(f"**{i}. {q['Вопрос']}**")
                for j, option in enumerate(q["Варианты"]):
                    st.checkbox(option, key=f"{qkey(i)}_{j}")
                st.write("") 

            submitted = st.form_submit_button("Проверить ответы")

        if submitted:
            check_quiz(course_topic, cur, total, questions, qkey)

def check_quiz(course_topic, cur, total, questions, qkey):
    answers = []
    for i, q in enumerate(questions, 1):
        selected_options = []
        for j, option in enumerate(q["Варианты"]):
            if st.session_state.get(f"{qkey(i)}_{j}"):
                selected_options.append(option)
        answers.append(selected_options)

    missing = [str(i) for i, a in enumerate(answers, 1) if not a]
    if missing:
        st.warning("Ответьте на все вопросы. Нет ответа на: " + ", ".join(missing))
        return

    attempt_key = f"{course_topic}:{cur}:main"
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
            st.session_state.module_phase = "theory" 
        save_user_progress() # Автосохранение прогресса
        st.rerun()

    st.markdown(f"### Результат: {score} из {len(questions)}")
    for i, (ok, correct_texts_str, explanation) in enumerate(results, 1):
        if ok:
            st.success(f"Вопрос {i}: верно.")
        else:
            text = f"Вопрос {i}: неверно."
            if attempts >= SHOW_ANSWER_AFTER_ATTEMPTS:
                text += f"\n\n**Правильные ответы:** {correct_texts_str}"
                if explanation:
                    text += f"\n\n{explanation}"
            st.error(text)
    st.info("Исправьте неверные ответы и нажмите «Проверить ответы» ещё раз.")

def render_certificate(course_topic: str):
    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)
    
    st.success("🎉 Вы успешно завершили все модули курса.")
    
    # Автоматически берем имя из сессии, так как пользователь уже авторизовался
    student_name = st.session_state.student_name

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

    st.divider()
    if st.button("Начать новый курс"):
        reset_progress(clear_user=False)
        st.rerun()

# ---------------------------------------------------------------------
# РЕЖИМ 2: АУДИТ / АРРФР (GEMINI)
# ---------------------------------------------------------------------
@st.cache_resource(ttl=DOCS_TTL_SECONDS, show_spinner="Синхронизация документов...")
def upload_documents():
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

    model_name = st.secrets.get("GEMINI_MODEL", "gemini-1.5-pro")
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

if st.session_state.get("_mode_seen") != task_mode:
    st.session_state["_mode_seen"] = task_mode
    st.session_state.messages = []

# Маршрутизация с учетом авторизации
if task_mode.startswith("🎓"):
    if not st.session_state.student_name:
        render_login()
    else:
        render_trainer()
else:
    render_online(task_mode)
