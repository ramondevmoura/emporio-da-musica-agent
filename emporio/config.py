import os

from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str = "") -> str:
    """Read from the environment, falling back to Streamlit secrets when deployed."""
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st

        return str(st.secrets.get(name, default))
    except Exception:
        return default


OPENAI_API_KEY = _get("OPENAI_API_KEY")
OPENAI_MODEL = _get("OPENAI_MODEL", "gpt-5.4-mini")
OPENAI_REASONING_EFFORT = _get("OPENAI_REASONING_EFFORT", "low")
OPENAI_TRANSCRIBE_MODEL = _get("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
MAX_MESSAGES_PER_SESSION = int(_get("MAX_MESSAGES_PER_SESSION", "40"))
