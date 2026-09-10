import logging
from pathlib import Path
import streamlit as st
from assistant import ask_question, is_ready
from chat_state import clear_chat, initialize_state, queue_question, submit_composer
from components import (apply_theme, render_header, render_intro, render_message,
                        render_suggestions, render_typing, DISCLAIMER)

LOGO = Path(__file__).with_name("assets") / "logo.png"

st.set_page_config(page_title="ThyBot", page_icon=str(LOGO), layout="wide")
initialize_state()
apply_theme(True)

pending = st.session_state.pending_submission
busy = pending is not None
render_header(is_ready(), busy, clear_chat)
if not st.session_state.messages:
    render_intro()
for index, message in enumerate(st.session_state.messages):
    render_message(message, index)

response_slot = st.container()
render_suggestions(bool(st.session_state.messages), busy, queue_question)

with st.container(key="composer_dock"):
    st.chat_input("What would you like to understand?", key="composer", height="content",
                  disabled=busy, submit_mode="disable", on_submit=submit_composer)
    st.markdown(f'<p class="conversation-note">{DISCLAIMER}</p>', unsafe_allow_html=True)

if pending:
    
    with response_slot:
        thinking = st.empty()
        with thinking.container():
            render_typing()
        try:
            data = ask_question(pending["question"])
        except Exception:
            logging.getLogger(__name__).exception("Chat request failed")
            data = {"answer": "Something went wrong just now. Please try again in a moment.",
                    "sources": [], "disclaimer": "", "guardrail": None, "request_error": True}
        finally:
            st.session_state.pending_submission = None
        thinking.empty()
    st.session_state.messages.append({"role": "assistant", **data})
    st.rerun()
