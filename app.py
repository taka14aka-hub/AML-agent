import streamlit as st
import google.generativeai as genai
import glob
from fpdf import FPDF
import base64
import json

# --- НАСТРОЙКА СТРАНИЦЫ И API ---
st.set_page_config(page_title="AML Агент - РК", page_icon="🛡️", layout="wide")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
except KeyError:
    st.error("API ключ не найден в секретах Streamlit!")
    st.stop()

# --- ФУНКЦИЯ ГЕНЕРАЦИИ СЕРТИФИКАТА ---
def create_pdf_certificate(course_name, student_name="Талгат Омиржанов"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 20, "CERTIFICATE OF COMPLETION", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 14)
    pdf.cell(0, 10, f"Awarded to: {student_name}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 10, f"Course: {course_name}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 10, "Status: Successfully completed all modules and tests.", align="C")
    return pdf.output(dest="S").encode("latin-1")

# --- ИНИЦИАЛИЗАЦИЯ ПАМЯТИ (ДЛЯ ВСЕХ РЕЖИМОВ) ---
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
    st.success("API ключ подключен автоматически! 🟢")
    st.divider()

# --- ЛОГИКА 1: АУДИТ И АРРФР (СТАНДАРТНЫЙ ЧАТ) ---
if task_mode in ["Аудит ПВК и регламентов", "Ответ на запрос/жалобу АРРФР"]:
    st.title("🛡️ ИИ-Агент по AML Комплаенсу (РК)")
    
    # 1. Загрузка базы знаний (PDF)
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

    # 2. Загрузка установок из файла
    try:
        with open("rules_and_memory.txt", "r", encoding="utf-8") as f:
            long_term_memory = f.read()
    except FileNotFoundError:
        long_term_memory = "Дополнительные инструкции отсутствуют."

    # 3. Настройка логики агента в зависимости от выбранного режима
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
    
    # 4. Отрисовка чата
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 5. Ввод пользователя и ответ ИИ
    if prompt := st.chat_input("Введите ваш запрос..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            model = genai.GenerativeModel(model_name="gemini-3.7-flash", system_instruction=system_instruction)
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
    
    # 1. Загрузка базы курсов из файла
    try:
        with open("courses.json", "r", encoding="utf-8") as f:
            courses_db = json.load(f)
    except FileNotFoundError:
        st.error("Файл courses.json не найден. Пожалуйста, создайте его в репозитории.")
        st.stop()
        
   # Динамический список курсов из базы
    course_list = list(courses_db.keys())
    
    # --- НОВЫЙ БЛОК: ОТСЛЕЖИВАНИЕ СМЕНЫ КУРСА ---
    if "selected_course" not in st.session_state:
        st.session_state.selected_course = course_list[0] if course_list else ""

    course_topic = st.selectbox("Выберите курс для изучения:", course_list)
    
    # Если пользователь выбрал другую тему в списке — сбрасываем прогресс
    if course_topic != st.session_state.selected_course:
        st.session_state.selected_course = course_topic
        st.session_state.current_module = 1
        st.session_state.course_passed = False
        st.session_state.module_content = ""
        st.rerun() 
    # ---------------------------------------------
    
    if course_topic:
        if not st.session_state.course_passed:
            
            # 2. МГНОВЕННАЯ ЗАГРУЗКА ТЕОРИИ (БЕЗ ЛИМИТОВ API)
            current_mod_str = str(st.session_state.current_module)
            
            if not st.session_state.module_content:
                # Достаем данные именно для этого модуля
                module_data = courses_db[course_topic][current_mod_str]
                theory_text = module_data["Теория"]
                
                # Собираем вопросы в красивый список
                questions_formatted = "\n".join([f"{i+1}. {q}" for i, q in enumerate(module_data["Вопросы"])])
                
                # Формируем итоговый текст и сохраняем в память
                st.session_state.module_content = f"{theory_text}\n\n### Проверочные вопросы:\n{questions_formatted}"
                st.rerun()
            
            # Выводим готовую лекцию на экран
            st.markdown(st.session_state.module_content)
            
            # 3. ПРОВЕРКА ОТВЕТОВ (ЗДЕСЬ РАБОТАЕТ ИИ)
            user_answer = st.text_area("Введите ваши ответы на 3 вопроса:")
            
            if st.button("Отправить на проверку"):
                if user_answer:
                    with st.spinner("Агент проверяет ваши ответы..."):
                        try:
                            trainer_model = genai.GenerativeModel("gemini-1.5-flash")
                            prompt_check = f"""
                            Студент отвечает на вопросы Модуля {st.session_state.current_module} по теме "{course_topic}".
                            Материал модуля: {st.session_state.module_content}
                            Ответы студента: {user_answer}
                            
                            Если ВСЕ 3 ответа правильные по смыслу, начни ответ со слова ПРИНЯТО.
                            Если есть ошибки, объясни их. Слово ПРИНЯТО не пиши!
                            """
                            eval_response = trainer_model.generate_content(prompt_check)
                            
                            st.markdown("### 📝 Комментарий преподавателя:")
                            st.info(eval_response.text)
                            
                            if "ПРИНЯТО" in eval_response.text.upper():
                                st.success("Отлично! Модуль пройден.")
                                st.session_state.module_content = "" 
                                
                                if st.session_state.current_module >= 3:
                                    st.session_state.course_passed = True
                                else:
                                    st.session_state.current_module += 1
                                
                                # Короткая пауза для безопасности и автоматический переход
                                import time
                                time.sleep(4)
                                st.rerun()
                            else:
                                st.error("Есть ошибки. Изучите комментарии и отправьте заново.")
                                
                        except Exception as e:
                            st.error(f"Сервер Google перегружен. Подождите 15-30 секунд и нажмите кнопку снова. (Ошибка: {e})")
                else:
                    st.warning("Напишите ответы перед отправкой.")
        
        else:
            # 4. ФИНАЛ И СЕРТИФИКАТ
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
