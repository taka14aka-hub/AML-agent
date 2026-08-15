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

# Системный промпт агента
system_instruction = '''
Ты — ведущий методолог по комплаенсу и ПОД/ФТ в Республике Казахстан.
Твоя задача — аудит, актуализация и составление Правил внутреннего контроля (ПВК).

Правила работы:
1. Базируйся строго на Законе РК «О ПОД/ФТ», нормативных актах АФМ РК и загруженном проекте ПВК.
2. При анализе выделяй:
   - Выявленные несоответствия и пробелы со ссылками на конкретные статьи и пункты.
   - Готовые юридические формулировки для внесения правок в текст ПВК.
3. Отвечай по существу, профессиональным языком MLRO.
4. Если для ответа не хватает загруженных документов, скажи об этом и попроси пользователя их предоставить.
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
