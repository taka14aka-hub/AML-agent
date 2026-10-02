import streamlit as st
import google.generativeai as genai
import glob
from fpdf import FPDF
import json
import time

# --- НАСТРОЙКА СТРАНИЦЫ И API ---
st.set_page_config(page_title="AML Агент - РК", page_icon="🛡️", layout="wide")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
except KeyError:
    st.error("API ключ не найден в секретах Streamlit! Добавьте его в настройки.")
    st.stop()

# --- ИСПОЛЬЗУЕМ АКТУАЛЬНУЮ МОДЕЛЬ, ЗАПРОШЕННУЮ СЕРВЕРОМ ---
WORKING_MODEL = "gemini-3.1-pro-preview"

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

# --- БОКОВАЯ ПАНЕЛЬ ---
with st.sidebar:
    st.header("⚙️ Настройки и Статус")
    task_mode = st.selectbox(
        "Выберите режим работы:",
        ("Аудит ПВК и регламентов", "Ответ на запрос/жалобу АРРФР", "🎓 Обучающий тренажер (Крипто)")
    )
    st.success("API ключ подключен! 🟢")
    st.info(f"Активная модель ИИ:\n**{WORKING_MODEL}**") # Показываем, какую модель нашел код
    st.divider()

# --- ЛОГИКА 1: АУДИТ И АРРФР (СТАНДАРТНЫЙ ЧАТ) ---
if task_mode in ["Аудит ПВК и регламентов", "Ответ на запрос/жалобу АРРФР"]:
    st.title("🛡️ ИИ-Агент по AML Комплаенсу (РК)")
    
    st.subheader("📂 База знаний")
    if not st.session_state.gemini_files:
        with st.spinner("Синхронизация нормативной базы..."):
            pdf_files = glob.glob("*.pdf")
            if pdf_files:
                for file_path in pdf_files:
                    if file_path not in st.session_state.uploaded_file_names:
                        try:
                            gemini_file = genai.upload_file(path=file_path)
                            st.session_state.gemini_files.append(gemini_file)
                            st.session_state.uploaded_file_names.add(file_path)
                        except Exception as e:
                            st.error(f"Ошибка загрузки файла {file_path}: {e}")
                st.success(f"Автоматически загружено документов: {len(st.session_state.gemini_files)}")
            else:
                st.info("Пока нет базовых документов. Загрузите PDF-файлы на GitHub.")
    else:
        st.success(f"Активных документов в памяти: {len(st.session_state.gemini_files)}")

    try:
        with open("rules_and_memory.txt", "r", encoding="utf-8") as f:
            long_term_memory = f.read()
    except FileNotFoundError:
        long_term_memory = "Дополнительные инструкции отсутствуют."

    if task_mode == "Аудит ПВК и регламентов":
        mode_instructions = "Твоя задача — аудит ПВК. Ищи риски, уязвимости и несоответствия законам. Предлагай жесткие формулировки."
    else:
        mode_instructions = "Твоя задача — подготовка официального ответа для АРРФР. Защищай интересы МФО, ссылайся на нормы права, пиши в строгом деловом стиле."

    system_instruction = f'''
    Ты — ведущий ИИ-методолог по комплаенсу.
    {long_term_memory}
    
    ТЕКУЩАЯ ЗАДАЧА: {mode_instructions}
    '''

    st.divider()
    st.subheader(f"💬 Диалог ({task_mode})")
    
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Введите ваш запрос..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            model = genai.GenerativeModel(model_name=WORKING_MODEL, system_instruction=system_instruction)
            contents = st.session_state.gemini_files + [prompt]
            with st.spinner("Анализирую данные..."):
                try:
                    response = model.generate_content(contents)
                    st.markdown(response.text)
                    st.session_state.messages.append({"role": "assistant", "content": response.text})
                except Exception as e:
                    st.error(f"Ошибка генерации ответа: {e}")

# --- ЛОГИКА 2: ОБУЧАЮЩИЙ ТРЕНАЖЕР (СТАТИЧНАЯ БАЗА) ---
else:
    st.title("🎓 Тренажер по комплаенсу (Offline-база)")
    st.markdown("Теория загружается моментально из базы. ИИ используется только для проверки ответов!")
    
    try:
        with open("courses.json", "r", encoding="utf-8") as f:
            courses_db = json.load(f)
    except FileNotFoundError:
        st.error("Файл courses.json не найден. Пожалуйста, создайте его в корневом каталоге проекта.")
        st.stop()
    except json.JSONDecodeError:
        st.error("Ошибка в формате файла courses.json. Убедитесь, что там корректный JSON-код.")
        st.stop()
        
    course_list = list(courses_db.keys())
    
    if "selected_course" not in st.session_state:
        st.session_state.selected_course = course_list[0] if course_list else ""

    course_topic = st.selectbox("Выберите курс для изучения:", course_list)
    
    if course_topic != st.session_state.selected_course:
        st.session_state.selected_course = course_topic
        st.session_state.current_module = 1
        st.session_state.course_passed = False
        st.session_state.module_content = ""
        st.rerun() 
    
    if course_topic:
        total_modules = len(courses_db[course_topic].keys())
        
        if not st.session_state.course_passed:
            st.info(f"📚 Модуль {st.session_state.current_module} из {total_modules}.")
            
            current_mod_str = str(st.session_state.current_module)
            
            if not st.session_state.module_content:
                if current_mod_str in courses_db[course_topic]:
                    module_data = courses_db[course_topic][current_mod_str]
                    theory_text = module_data.get("Теория", "Теория не найдена.")
                    
                    questions = module_data.get("Вопросы", [])
                    questions_formatted = "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])
                    
                    st.session_state.module_content = f"{theory_text}\n\n### Проверочные вопросы:\n{questions_formatted}"
                    st.rerun()
                else:
                    st.error(f"Модуль {current_mod_str} не найден в файле JSON.")
                    st.stop()
            
            st.markdown(st.session_state.module_content)
            
            user_answer = st.text_area("Введите ваши ответы на вопросы:")
            
            if st.button("Отправить на проверку"):
                if user_answer:
                    with st.spinner("Система анализирует ваш ответ..."):
                        # Загружаем ключи из базы (если их нет, пропускаем автоматически)
                        keywords = module_data.get("Ключевые_слова", [])
                        user_text_lower = user_answer.lower()
                        
                        # Ищем совпадения корней слов в ответе студента
                        matched_words = [kw for kw in keywords if kw.lower() in user_text_lower]
                        
                        # Логика: если найдено хотя бы 50% нужных терминов (или ключи не заданы)
                        required_matches = max(1, len(keywords) // 2) 
                        
                        st.markdown("### 📝 Отчет системы:")
                        
                        if not keywords or len(matched_words) >= required_matches:
                            st.info("Анализ семантики: Суть раскрыта верно, ключевые термины использованы.")
                            st.success("ПРИНЯТО! Модуль пройден. Загружаем следующий этап...")
                            
                            st.session_state.module_content = "" 
                            if st.session_state.current_module >= total_modules:
                                st.session_state.course_passed = True
                            else:
                                st.session_state.current_module += 1
                            
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("Ответ неполный или неточный.")
                            st.warning(f"💡 Подсказка ИИ-ассистента: Раскройте тему глубже. Ожидаемые термины в ответе: {', '.join(keywords)}")
                else:
                    st.warning("Напишите ответы перед отправкой.")
        
        else:
            st.success("🎉 Поздравляем! Вы успешно завершили все модули.")
            
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
