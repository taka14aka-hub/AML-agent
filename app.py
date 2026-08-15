
import streamlit as st
import google.generativeai as genai
import os
import tempfile

# Настройка страницы
st.set_page_config(page_title="AML Агент - РК", page_icon="🛡️", layout="wide")

st.title("🛡️ ИИ-Агент по AML Комплаенсу (Республика Казахстан)")
st.markdown("Рабочее пространство для аудита, актуализации и составления Правил внутреннего контроля (ПВК) на базе законодательства РК.")

# Боковая панель для настроек
with st.sidebar:
    st.header("⚙️ Настройки API")
    api_key = st.text_input("Введите ваш Gemini API Key", type="password")
    if api_key:
        api_key = api_key.strip()
        genai.configure(api_key=api_key)
        st.success("API ключ установлен!")
    else:
        st.warning("Для работы агента требуется API ключ от Google AI Studio.")
    
    st.divider()
    st.markdown("### 📚 Инструкция:")
    st.markdown("1. Вставьте API ключ.\n2. Загрузите файлы ПВК и нормативной базы (PDF, DOCX).\n3. Напишите запрос в чат (например, 'Проверь раздел KYC на соответствие Закону о ПОД/ФТ').")

# Инициализация состояния сессии
if "messages" not in st.session_state:
    st.session_state.messages = []
if "gemini_files" not in st.session_state:
    st.session_state.gemini_files = []
if "uploaded_file_names" not in st.session_state:
    st.session_state.uploaded_file_names = set()

# Загрузчик файлов
st.subheader("📂 База знаний")
uploaded_files = st.file_uploader("Загрузите исторические ПВК и нормативные акты", accept_multiple_files=True)

if api_key and uploaded_files:
    with st.spinner("Загрузка и индексация документов в защищенное хранилище..."):
        for uploaded_file in uploaded_files:
            if uploaded_file.name not in st.session_state.uploaded_file_names:
                # Сохраняем во временный файл для передачи в Gemini API
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_file_path = tmp_file.name
                
                # Загружаем файл в Gemini
                try:
                    gemini_file = genai.upload_file(path=tmp_file_path, display_name=uploaded_file.name)
                    st.session_state.gemini_files.append(gemini_file)
                    st.session_state.uploaded_file_names.add(uploaded_file.name)
                except Exception as e:
                    st.error(f"Ошибка загрузки файла {uploaded_file.name}: {e}")
                finally:
                    os.remove(tmp_file_path)
        
        if st.session_state.gemini_files:
            st.success(f"В базе знаний агента файлов: {len(st.session_state.gemini_files)}")

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
                model_name="gemini-1.5-flash-latest",
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
