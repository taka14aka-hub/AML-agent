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
    return pdf.output(dest="S").encode("latin-1")

# --- ИНИЦИАЛИЗАЦИЯ ПАМЯТИ ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "gemini_files" not in st.session_state:
    st.session_state.gemini_files = []
if "uploaded_file_names" not in st.session_state:
    st.session_state.uploaded_file_names = set()
if "current_module" not in st.session_state:
    st.session_state.current_module = 1
if "course_passed" not in st.session_state:
    st.session_state.course_passed = False
if "module_content" not in st.session_state:
    st.session_state.module_content = ""

# --- БОКОВАЯ ПАНЕЛЬ И ВЫБОР РЕЖИМА ---
with st.sidebar:
    st.header("⚙️ Настройки и Статус")
    task_mode = st.selectbox(
        "Выберите режим работы:",
        ("🎓 Обучающий тренажер (Офлайн)", "Аудит ПВК и регламентов", "Ответ на запрос/жалобу АРРФР")
    )
    st.divider()

# =====================================================================
# ЛОГИКА 1: ОБУЧАЮЩИЙ ТРЕНАЖЕР (СТРОГО ОФЛАЙН, 0 ТОКЕНОВ)
# =====================================================================
if task_mode == "🎓 Обучающий тренажер (Офлайн)":
    st.title("🎓 Тренажер по комплаенсу")
    st.markdown("⚡ *Работает автономно. Не расходует лимиты API.*")
    
    courses_db = load_courses_db()
    
    if courses_db is None:
        st.error("Файл `courses.json` не найден. Создайте его в корне проекта.")
        st.stop()
    elif courses_db == "error":
        st.error("Синтаксическая ошибка в `courses.json`. Проверьте файл через любой JSON Validator.")
        st.stop()
        
    course_list = list(courses_db.keys())
    
    if "selected_course" not in st.session_state:
        st.session_state.selected_course = course_list[0] if course_list else ""

    course_topic = st.selectbox("Выберите курс для изучения:", course_list)
    
    # Сброс прогресса при смене курса
    if course_topic != st.session_state.selected_course:
        st.session_state.selected_course = course_topic
        st.session_state.current_module = 1
        st.session_state.course_passed = False
        st.session_state.module_content = ""
        st.rerun() 
    
    if course_topic:
        course_data = courses_db.get(course_topic, {})
        total_modules = len(course_data.keys())
        
        if not st.session_state.course_passed:
            st.info(f"📚 Модуль {st.session_state.current_module} из {total_modules}.")
            current_mod_str = str(st.session_state.current_module)
            
            # Безопасное извлечение данных модуля
            module_data = course_data.get(current_mod_str, {})
            
            if not st.session_state.module_content:
                if module_data:
                    theory_text = module_data.get("Теория", "Теория в разработке.")
                    questions = module_data.get("Вопросы", [])
                    questions_formatted = "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])
                    st.session_state.module_content = f"{theory_text}\n\n### Проверочные вопросы:\n{questions_formatted}"
                    st.rerun()
                else:
                    st.error(f"Модуль {current_mod_str} пуст или не найден в JSON.")
                    st.stop()
            
            # Отрисовка теории
            st.markdown(st.session_state.module_content)
            
            # Локальная проверка ответов
            user_answer = st.text_area("Введите ваши ответы на вопросы:")
            
            if st.button("Отправить на проверку"):
                if user_answer.strip():
                    with st.spinner("Локальный анализ семантики..."):
                        keywords = module_data.get("Ключевые_слова", [])
                        user_text_lower = user_answer.lower()
                        
                        matched_words = [kw for kw in keywords if kw.lower() in user_text_lower]
                        required_matches = max(1, len(keywords) // 2) 
                        
                        st.markdown("### 📝 Отчет системы:")
                        
                        if not keywords or len(matched_words) >= required_matches:
                            st.success("✅ **ПРИНЯТО!** Суть раскрыта верно. Загружаем следующий этап...")
                            st.session_state.module_content = "" 
                            
                            if st.session_state.current_module >= total_modules:
                                st.session_state.course_passed = True
                            else:
                                st.session_state.current_module += 1
                            
                            time.sleep(1.5)
                            st.rerun()
                        else:
                            st.error("❌ Ответ неполный или неточный.")
                            st.warning(f"💡 **Подсказка:** Раскройте тему глубже. Ожидаемые термины: {', '.join(keywords)}")
                else:
                    st.warning("Напишите ответы перед отправкой.")
        
        else:
            st.success("🎉 Поздравляем! Вы успешно завершили все модули курса.")
            pdf_bytes = create_pdf_certificate(course_topic)
            st.download_button(
                label="📥 Скачать сертификат (PDF)",
                data=pdf_bytes,
                file_name="Compliance_Certificate.pdf",
                mime="application/pdf"
            )
            if st.button("Начать новый курс"):
                st.session_state.current_module = 1
                st.session_state.course_passed = False
                st.session_state.module_content = ""
                st.rerun()

# =====================================================================
# ЛОГИКА 2: АУДИТ И АРРФР (ОНЛАЙН С ИСПОЛЬЗОВАНИЕМ GEMINI API)
# =====================================================================
else:
    st.title("🛡️ ИИ-Агент по AML Комплаенсу (РК)")
    
    # Подключение API только если выбран онлайн-режим
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        st.sidebar.success("API ключ Google подключен 🟢")
        WORKING_MODEL = "gemini-3.1-pro-preview"
        st.sidebar.caption(f"Модель: {WORKING_MODEL}")
    except KeyError:
        st.error("API ключ не найден в настройках. Этот режим требует подключения к Google Gemini.")
        st.stop()

    st.subheader("📂 Нормативная база")
    if not st.session_state.gemini_files:
        with st.spinner("Синхронизация документов..."):
            pdf_files = glob.glob("*.pdf")
            if pdf_files:
                for file_path in pdf_files:
                    if file_path not in st.session_state.uploaded_file_names:
                        try:
                            gemini_file = genai.upload_file(path=file_path)
                            st.session_state.gemini_files.append(gemini_file)
                            st.session_state.uploaded_file_names.add(file_path)
                        except Exception as e:
                            st.error(f"Ошибка загрузки {file_path}: {e}")
                st.success(f"Документов в памяти ИИ: {len(st.session_state.gemini_files)}")
            else:
                st.info("Нет PDF-файлов. Загрузите их в репозиторий для анализа.")
    else:
        st.success(f"Документов в памяти ИИ: {len(st.session_state.gemini_files)}")

    # Загрузка инструкций
    try:
        with open("rules_and_memory.txt", "r", encoding="utf-8") as f:
            long_term_memory = f.read()
    except FileNotFoundError:
        long_term_memory = ""

    mode_instructions = (
        "Твоя задача — аудит ПВК. Ищи риски, уязвимости и несоответствия законам РК. Предлагай жесткие формулировки."
        if task_mode == "Аудит ПВК и регламентов"
        else "Твоя задача — подготовка ответа для АРРФР. Защищай интересы МФО, ссылайся на нормы права, пиши в строгом деловом стиле."
    )

    system_instruction = f"Ты — ведущий ИИ-методолог по AML в Казахстане.\n{long_term_memory}\nТЕКУЩАЯ ЗАДАЧА: {mode_instructions}"

    st.divider()
    st.subheader(f"💬 Рабочий чат ({task_mode})")
    
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Опишите задачу или загрузите выдержку из документа..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            model = genai.GenerativeModel(model_name=WORKING_MODEL, system_instruction=system_instruction)
            contents = st.session_state.gemini_files + [prompt]
            with st.spinner("Анализирую..."):
                try:
                    response = model.generate_content(contents)
                    st.markdown(response.text)
                    st.session_state.messages.append({"role": "assistant", "content": response.text})
                except Exception as e:
                    st.error(f"Ошибка API (возможно исчерпан лимит): {e}")
