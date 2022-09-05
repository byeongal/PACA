import os
import uuid
from datetime import datetime

import firebase_admin
import openai
import streamlit as st
from firebase_admin import credentials, db
from streamlit_chat import message as st_message


@st.experimental_singleton
def load_initial_data():
    print("Load Data")
    task_description = "The following is a conversation with an AI assistant."
    brooklyn_data = db.reference("/apps/brooklyn").get()
    print(brooklyn_data)
    core_beliefs = " ".join(
        [value for _, value in sorted(brooklyn_data["core_beliefs"].items(), key=lambda x: int(x[0]))]
    )
    base_context = [
        {"AI": value["AI"], "Human": value["Human"], "context_id": key}
        for key, value in sorted(brooklyn_data["context"].items(), key=lambda x: int(x[0]))
    ]
    return task_description, core_beliefs, base_context


openai.api_key = os.getenv("OPENAI_API_KEY")
firebase_app_name = os.getenv("FIREBASE_APP_NAME", firebase_admin._DEFAULT_APP_NAME)

try:
    firebase_admin.get_app(firebase_app_name)
except ValueError:
    print("Initialize Firebase")
    firebase_cred_path = os.getenv("FIREBASE_CRED_PATH")
    firebase_database_url = os.getenv("FIREBASE_DATABASE_URL")
    cred = credentials.Certificate(firebase_cred_path)
    firebase_admin.initialize_app(cred, {"databaseURL": firebase_database_url}, name=firebase_app_name)

if "history" not in st.session_state:
    st.session_state.history = []

if (
    "task_description" not in st.session_state
    or "core_beliefs" not in st.session_state
    or "base_context" not in st.session_state
):
    (
        st.session_state.task_description,
        st.session_state.core_beliefs,
        st.session_state.base_context,
    ) = load_initial_data()


st.title("PACA")


def generate_answer():
    now = int(datetime.utcnow().timestamp() * 1000)
    if "prompt_history" not in st.session_state:
        st.session_state.prompt_history = st.session_state.base_context
    user_message = st.session_state.input_text
    if user_message.startswith("No way! You should say"):
        fixed_bot_start_idx = len("No way! You should say")
        fixed_bot_response = user_message[fixed_bot_start_idx:].strip()
        prev = st.session_state.prompt_history.pop()
        st.session_state.prompt_history.append(
            {"Human": prev["Human"], "AI": fixed_bot_response, "context_id": str(now)}
        )
        # History 에서 잘못된 말 삭제 + 새로운 말 추가
        db.reference("/apps/brooklyn/history").update(
            {
                prev["context_id"]: None,
                str(now): {"Human": prev["Human"], "AI": fixed_bot_response},
            }
        )
        # Context 에 새로운 데이터 추가
        db.reference("/apps/brooklyn/context").update(
            {
                str(now): {"Human": prev["Human"], "AI": fixed_bot_response, "is_fixed": True},
            }
        )
        message_bot = f"Right, {fixed_bot_response}"
    else:
        context = "\n".join([f"Human: {each['Human']}\nAI: {each['AI']}" for each in st.session_state.prompt_history])
        context += f"\nHuman: {user_message}\nAI:"
        response = openai.Completion.create(
            model="text-davinci-002",
            prompt=f"{st.session_state.task_description} {st.session_state.core_beliefs}\n\n{context}",
            temperature=0.9,
            max_tokens=150,
            top_p=1,
            frequency_penalty=0.0,
            presence_penalty=0.6,
            stop=[" Human:", " AI:"],
        )
        message_bot = response["choices"][0]["text"].strip()
        st.session_state.prompt_history.append({"Human": user_message, "AI": message_bot, "context_id": str(now)})
        # History 새로운 말 추가
        db.reference("/apps/brooklyn/history").update(
            {
                str(now): {"Human": user_message, "AI": message_bot},
            }
        )
    user_id = str(uuid.uuid5(uuid.NAMESPACE_OID, str(now) + "user"))
    bot_id = str(uuid.uuid5(uuid.NAMESPACE_OID, str(now) + "bot"))
    st.session_state.history.append({"message": user_message, "is_user": True, "key": user_id})
    st.session_state.history.append({"message": message_bot, "is_user": False, "key": bot_id})


for chat in st.session_state.history:
    st_message(**chat)  # unpacking

st.text_input("Talk to the bot", key="input_text", on_change=generate_answer)
