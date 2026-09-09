import streamlit as st


def initialize_state():
    for key, default in (("messages", []),
                         ("pending_submission", None), ("submission_sequence", 0)):
        if key not in st.session_state:
            st.session_state[key] = default


def queue_question(question):
    question = question.strip()
    if not question or st.session_state.pending_submission is not None:
        return
    st.session_state.submission_sequence += 1
    st.session_state.pending_submission = {
        "id": st.session_state.submission_sequence, "question": question,
    }
    st.session_state.messages.append({"role": "user", "content": question})


def submit_composer():
    queue_question(st.session_state.get("composer", ""))


def clear_chat():
    st.session_state.messages = []
    st.session_state.pending_submission = None
    st.session_state.pop("pending_question", None)
