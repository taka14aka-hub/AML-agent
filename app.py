import streamlit as st
import google.generativeai as genai
import os
import tempfile

# Настройка страницы
st.set_page_config(page_title="AML Агент - РК", page_icon="🛡️", layout="wide")

st.title("🛡️ ИИ-Агент по AML Комплаенсу (Республика Казахстан)")
st.markdown("Рабочее пространство для аудита, актуализации и составления Правил внутреннего контроля (ПВК) на базе законодательства РК.")

# Автоматическое подключение ключа из секретов
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
except KeyError:
    st.error("API ключ не найден в секретах Streamlit!")
    st.stop()

# Боковая панель для статуса
with st.sidebar:
    st.header("⚙️ Статус агента")
    st.success("API ключ подключен автоматически! 🟢")
    st.divider()
    st.markdown("### 📚 Инструкция:")
    st.markdown("1. Загрузите файлы ПВК и нормативной базы (PDF).\n2. Напишите запрос в чат (например, 'Проверь раздел KYC на соответствие Закону о ПОД/ФТ').")
# Инициализация состояния сессии
if "messages" not in st.session_state:
    st.session_state.messages = []
if "gemini_files" not in st.session_state:
    st.session_state.gemini_files = []
if "uploaded_file_names" not in st.session_state:
    st.session_state.uploaded_file_names = set()

# Загрузчик файлов
st.subheader("📂 База знаний")
# Инициализация состояния сессии
if "messages" not in st.session_state:
    st.session_state.messages = []
if "gemini_files" not in st.session_state:
    st.session_state.gemini_files = []
if "uploaded_file_names" not in st.session_state:
    st.session_state.uploaded_file_names = set()

# Автоматическая загрузка всех PDF из репозитория
import glob

if not st.session_state.gemini_files:
    with st.spinner("Синхронизация нормативной базы с памятью агента..."):
        # Ищем все PDF-файлы, которые лежат рядом с кодом
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
            st.info("Пока нет базовых документов. Загрузите PDF-файлы в ваш репозиторий на GitHub.")
else:
    st.success(f"В базе знаний агента активных документов: {len(st.session_state.gemini_files)}")

st.divider()

# Загрузка долгосрочной памяти
try:
    with open("rules_and_memory.txt", "r", encoding="utf-8") as f:
        long_term_memory = f.read()
except FileNotFoundError:
    long_term_memory = "Дополнительные инструкции отсутствуют."

# Системный промпт агента (обновленный)
system_instruction = f'''
Ты — ведущий ИИ-методолог по комплаенсу и ПОД/ФТ.
Твоя задача — аудит, актуализация и составление Правил внутреннего контроля (ПВК), а также помощь в повседневных задачах MLRO.

ОЗНАКОМЬСЯ С ПРОФИЛЕМ КОМПАНИИ И ПРАВИЛАМИ РАБОТЫ:
{long_term_memory}

Правила ответа:
1. Базируйся строго на загруженных документах и своей памяти.
2. Если для ответа не хватает данных, прямо запрашивай уточнения.
'''

# Отображение истории чата
st.subheader("💬 Диалог с агентом")
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Ввод пользователя
if prompt := st.chat_input("Например: Проведи аудит раздела 'Идентификация клиента' (ПДЛ/PEP)..."):
    if not api_key:
        st.error("Пожалуйста, сначала введите API ключ в боковой панели.")
    else:
        # Добавляем сообщение пользователя в интерфейс
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Вызов модели
        with st.chat_message("assistant"):
            model = genai.GenerativeModel(
                model_name="gemini-3.7-flash",
                system_instruction=system_instruction
            )
            
            # Передаем загруженные файлы + текстовый запрос
            contents = st.session_state.gemini_files + [prompt]
            
            with st.spinner("Анализирую документы и нормативную базу..."):
                try:
                    response = model.generate_content(contents)
                    st.markdown(response.text)
                    st.session_state.messages.append({"role": "assistant", "content": response.text})
                except Exception as e:
                    st.error(f"Произошла ошибка при генерации ответа: {e}")
                    import streamlit as st
from fpdf import FPDF
import base64

# --- ГЕНЕРАТОР СЕРТИФИКАТОВ ---
def create_pdf_certificate(course_name, student_name="Талгат Омиржанов"):
    pdf = FPDF()
    pdf.add_page()
    # В реальном проекте сюда загружается шрифт с кириллицей, пока используем стандартный
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 20, "CERTIFICATE OF COMPLETION", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 14)
    pdf.cell(0, 10, f"Awarded to: {student_name}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 10, f"Course: {course_name}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 10, "Status: Successfully completed all modules and tests.", align="C")
    return pdf.output(dest="S").encode("latin-1")

# --- ИНИЦИАЛИЗАЦИЯ ПАМЯТИ ОБУЧЕНИЯ ---
if "current_module" not in st.session_state:
    st.session_state.current_module = 1
if "course_passed" not in st.session_state:
    st.session_state.course_passed = False
# Добавляем ячейку памяти для текста текущего урока
if "module_content" not in st.session_state:
    st.session_state.module_content = ""

# --- БОКОВАЯ ПАНЕЛЬ ---
with st.sidebar:
    st.header("⚙️ Режим работы")
    task_mode = st.selectbox(
        "Выберите задачу:",
        ("Аудит ПВК и регламентов", "Ответ на запрос/жалобу АРРФР", "🎓 Обучающий тренажер (Крипто)")
    )
    st.divider()

# --- ЛОГИКА РЕЖИМОВ ---
if task_mode != "🎓 Обучающий тренажер (Крипто)":
    st.write(f"Активен режим: {task_mode}")
    # ... здесь остается ваш старый код для аудита ...

else:
    # НОВЫЙ РЕЖИМ: ТРЕНАЖЕР
    st.title("🎓 Тренажер по комплаенсу")
    
    course_topic = st.text_input("Введите тему (например, 'Travel Rule для криптобирж'):")
    
    if course_topic:
        if not st.session_state.course_passed:
            st.info(f"📚 Модуль {st.session_state.current_module} из 3.")
            
            # 1. ГЕНЕРАЦИЯ ТЕОРИИ И ВОПРОСОВ (если они еще не созданы)
            if not st.session_state.module_content:
                with st.spinner("Агент генерирует материалы курса..."):
                    prompt_generate = f"""
                    Ты — строгий преподаватель по AML и комплаенсу. 
                    Разработай Модуль {st.session_state.current_module} для курса "{course_topic}".
                    Выдай структурированный ответ:
                    1. Короткую, но емкую теорию (3-4 абзаца).
                    2. В конце напиши заголовок "Проверочные вопросы" и задай 3 вопроса по тексту.
                    """
                    # Вызываем ИИ для создания модуля
                    response = model.generate_content(prompt_generate)
                    st.session_state.module_content = response.text
                    st.rerun() # Перезагружаем интерфейс, чтобы показать текст
            
            # Выводим сгенерированную теорию на экран
            st.markdown(st.session_state.module_content)
            
            # 2. ПРОВЕРКА ОТВЕТОВ
            user_answer = st.text_area("Введите ваши ответы на 3 вопроса здесь (можно своими словами):")
            
            if st.button("Отправить на проверку"):
                if user_answer:
                    with st.spinner("Преподаватель проверяет ответы..."):
                        prompt_check = f"""
                        Студент отвечает на вопросы Модуля {st.session_state.current_module} по теме "{course_topic}".
                        Теория и вопросы были такие: {st.session_state.module_content}
                        Ответы студента: {user_answer}
                        
                        Оцени ответы. Если ВСЕ 3 ответа по смыслу правильные, обязательно напиши в самом начале ответа слово: ПРИНЯТО.
                        Если есть ошибки, укажи на них, объясни правильный вариант. Слово ПРИНЯТО не пиши!
                        """
                        eval_response = model.generate_content(prompt_check)
                        
                        st.markdown("### 📝 Комментарий преподавателя:")
                        st.info(eval_response.text)
                        
                        # Если ИИ одобрил ответы
                        if "ПРИНЯТО" in eval_response.text.upper():
                            st.success("Отлично! Модуль пройден.")
                            st.session_state.module_content = "" # Очищаем теорию для нового модуля
                            
                            if st.session_state.current_module >= 3:
                                st.session_state.course_passed = True
                            else:
                                st.session_state.current_module += 1
                                
                            # Кнопка для перезагрузки страницы и перехода на следующий этап
                            if st.button("Продолжить обучение"):
                                st.rerun()
                        else:
                            st.error("В ответах есть неточности. Изучите комментарии выше, исправьте ошибки и отправьте заново.")
                else:
                    st.warning("Пожалуйста, напишите ответы перед проверкой.")
        
        else:
            # 3. ФИНАЛ КУРСА
            st.success("🎉 Поздравляем! Вы успешно завершили все модули курса.")
            
            # Генерация и скачивание PDF
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
