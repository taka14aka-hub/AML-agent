import streamlit as st
import google.generativeai as genai
import os
import tempfile

# Настройка страницы
st.set_page_config(page_title="AML Агент - РК", page_icon="🛡️", layout="wide")

st.title("🛡️ Диагностика ИИ-Агента")
st.markdown("Проверка доступности моделей Gemini для вашего API-ключа.")

# Боковая панель для настроек
with st.sidebar:
    st.header("⚙️ Настройки API")
    api_key = st.text_input("Введите ваш Gemini API Key", type="password")
    if api_key:
        api_key = api_key.strip()
        genai.configure(api_key=api_key)
        st.success("API ключ установлен!")
    else:
        st.warning("Для работы агента требуется API ключ.")

# Инициализация состояния сессии
if "uploaded_file_names" not in st.session_state:
    st.session_state.uploaded_file_names = set()

st.divider()

# Ввод пользователя (ДИАГНОСТИКА)
if prompt := st.chat_input("Напишите любой текст и нажмите Enter..."):
    if not api_key:
        st.error("Пожалуйста, сначала введите API ключ.")
    else:
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant"):
            st.markdown("🔍 **Запрашиваю список разрешенных моделей у Google...**")
            try:
                available_models = []
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        available_models.append(m.name)
                
                if available_models:
                    st.success("Ответ получен! Вот список моделей, к которым у вашего ключа есть доступ:")
                    for mod in available_models:
                        st.code(mod)
                else:
                    st.error("Google ответил, но список моделей пуст. Ваш аккаунт не имеет доступа к генеративным моделям.")
                    
            except Exception as e:
                st.error(f"Ошибка запроса к серверу Google: {e}")
