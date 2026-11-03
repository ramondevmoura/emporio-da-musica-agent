"""Customer chat UI: `streamlit run app.py`.

Designed for customers with little tech experience: big fonts, WhatsApp-like bubbles, big
shortcut buttons for common questions, a microphone for voice messages, and the store's real
contact options always one tap away.
"""

from __future__ import annotations

import json
import uuid

import streamlit as st

from emporio import config, store_info
from emporio.agent import Agent, visible_messages
from emporio.fallback import contact_block, status_line
from emporio.memory import ConversationStore
from emporio.prompts import ASSISTANT_NAME

st.set_page_config(page_title="Empório da Música - Atendimento", page_icon="🎸", layout="centered")

WELCOME = (
    f"Oi! Eu sou a {ASSISTANT_NAME}, assistente virtual da **Empório da Música** 🎸\n\n"
    "Posso te ajudar com preços, instrumentos disponíveis, seu pedido, horários e trocas.\n\n"
    "É só escrever ou tocar no microfone 🎤 e falar."
)
SHORTCUTS = [
    ("🕐 Horário e endereço", "Qual o horário de funcionamento e o endereço da loja?"),
    ("🎸 Ver instrumentos", "Quais instrumentos vocês têm? Quero ver algumas opções."),
    ("📦 Meu pedido", "Quero saber como está o meu pedido."),
    ("👤 Falar com atendente", "Quero falar com uma pessoa da equipe."),
]

st.markdown(
    """
    <style>
      html, body, [class*="st-"] { font-size: 19px; }
      .stChatMessage p, .stChatMessage li { font-size: 1.15rem; line-height: 1.55; }
      div.stButton > button { font-size: 1.05rem; padding: 0.7rem 0.9rem; width: 100%;
                              border-radius: 14px; }
      [data-testid="stChatInput"] textarea { font-size: 1.15rem; }
      .contact a { font-size: 1.05rem; margin-right: 1.2rem; text-decoration: none; }
      header[data-testid="stHeader"] { height: 0; }
    </style>
    """,
    unsafe_allow_html=True,
)


def as_markdown(text: str) -> str:
    """Escape '$' (Streamlit renders '$...$' as LaTeX) and keep single line breaks."""
    return text.replace("$", r"\$").replace("\n", "  \n")


def show(text: str) -> None:
    """Render chat text. '$' is escaped because Streamlit treats '$...$' as LaTeX math,
    which turned 'R$ 159,90 ... R$ 429,90' into a green formula and hid the prices."""
    st.markdown(as_markdown(text))


@st.cache_resource
def get_agent() -> Agent:
    return Agent()


@st.cache_resource
def get_store() -> ConversationStore:
    return ConversationStore()


def session_id() -> str:
    """Keep the conversation in the URL so a refresh or a saved link resumes it."""
    if "s" not in st.query_params:
        st.query_params["s"] = uuid.uuid4().hex[:12]
    return st.query_params["s"]


def send(message: str, sid: str, history: list[dict]) -> None:
    store = get_store()
    if (
        store.user_message_count(sid) >= config.MAX_MESSAGES_PER_SESSION
        or store.user_messages_today() >= config.MAX_MESSAGES_PER_DAY
    ):
        st.session_state.notice = (
            "O atendimento virtual atingiu o limite de mensagens por agora. Fale com a nossa "
            f"equipe:\n\n{contact_block()}\n\n{status_line()}"
        )
        return
    with st.chat_message("user", avatar="🙂"):
        show(message)
    with st.chat_message("assistant", avatar="🎸"):
        with st.spinner(f"{ASSISTANT_NAME} está digitando..."):
            result = get_agent().respond(history, message)
        show(result.reply)
    store.append(sid, result.new_items)
    st.session_state.last_tools = [
        {"tool": e.name, "args": e.arguments, "result": e.result} for e in result.tool_events
    ]
    st.session_state.last_usage = result.usage


def transcribe_audio(audio) -> str | None:
    from emporio.stt import transcribe

    try:
        with st.spinner("Ouvindo seu áudio..."):
            text = transcribe(audio.getvalue(), audio.name or "audio.wav")
    except Exception:
        st.warning("Não consegui entender o áudio. Pode tentar de novo ou escrever?")
        return None
    if not text:
        st.warning("Não consegui ouvir nada no áudio. Pode tentar de novo?")
        return None
    return f"🎤 {text}"


# ------------------------------------------------------------------------------ page

st.markdown("## 🎸 Empório da Música")
st.markdown(
    f'<div class="contact">📍 <a href="{store_info.MAPS_URL}" target="_blank">Ver no mapa</a>'
    f'💬 <a href="{store_info.WHATSAPP_URL}" target="_blank">WhatsApp</a>'
    f'📞 <a href="{store_info.PHONE_URL}">Ligar</a></div>',
    unsafe_allow_html=True,
)
st.divider()

if not config.OPENAI_API_KEY:
    st.error("OPENAI_API_KEY não configurada. Copie .env.example para .env e preencha a chave.")
    st.stop()

sid = session_id()
history = get_store().load(sid)

with st.chat_message("assistant", avatar="🎸"):
    show(WELCOME)
for role, text in visible_messages(history):
    with st.chat_message(role, avatar="🙂" if role == "user" else "🎸"):
        show(text)

pending = None
if not history:
    cols = st.columns(2)
    for i, (label, message) in enumerate(SHORTCUTS):
        if cols[i % 2].button(label, key=f"shortcut-{i}"):
            pending = message

prompt = st.chat_input("Escreva sua mensagem aqui...", accept_audio=True)
if prompt:
    if prompt.audio:
        pending = transcribe_audio(prompt.audio)
    elif prompt.text.strip():
        pending = prompt.text.strip()

if pending:
    send(pending, sid, history)
    if not history:
        st.rerun()  # hide the shortcut buttons after the first message

if notice := st.session_state.pop("notice", None):
    st.info(as_markdown(notice))

if history and st.button("🔄 Começar nova conversa"):
    st.query_params["s"] = uuid.uuid4().hex[:12]
    st.rerun()

if st.query_params.get("debug") == "1" and st.session_state.get("last_tools") is not None:
    with st.expander("Debug: tool calls of the last turn"):
        st.code(json.dumps(st.session_state.last_tools, ensure_ascii=False, indent=2), "json")
        st.write(st.session_state.get("last_usage"))
