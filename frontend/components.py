from html import escape
from pathlib import Path
import streamlit as st

DISCLAIMER = "For learning, not personal medical advice. A healthcare professional can guide your care."
PROMPTS = (
    ("tsh", "What is TSH and where is it made?"),
    ("goiter", "What is a goiter?"),
    ("treatment", "How is hypothyroidism usually treated?"),
)
GUARDRAILS = {
    "emergency": ("Please seek urgent help", "emergency"),
    "dosage_refusal": ("A question for your care team", "dosage"),
    "out_of_scope": ("Let’s keep it about thyroid health", "scope"),
}


def apply_theme(dark):
    css = Path(__file__).with_name("styles.css").read_text(encoding="utf-8")
    theme = "dark" if dark else "light"
    st.html(f'<span class="theme-marker" data-theme="{theme}"></span>')
    st.html(f'<style>{css}</style>')


def render_header(online, busy, on_clear):
    with st.container(key="chat_header", horizontal=True, vertical_alignment="center"):
        st.markdown('<div class="brand"><span class="brand-mark" aria-hidden="true">t.</span>'
                    '<div><span class="brand-name">ThyBot</span>'
                    '<span class="brand-description">A little clarity, one question at a time.</span></div></div>',
                    unsafe_allow_html=True)
        with st.container(key="header_actions", horizontal=True, width="content",
                          vertical_alignment="center"):
            st.button("New chat", key="new_chat", icon=":material/edit_square:",
                      on_click=on_clear, disabled=busy or not st.session_state.messages,
                      type="tertiary", help="Clear this conversation")
            with st.popover("About", icon=":material/info:", type="tertiary"):
                st.markdown("**A clearer understanding of thyroid health.**")
                st.write("Explore explanations grounded in nine thyroid-health documents. "
                         "Sources appear below answers so you can see where the information comes from.")
                st.caption("ThyBot cannot diagnose conditions, recommend personal medication changes, "
                           "or provide emergency care.")
                st.markdown("**Privacy**")
                st.caption("Questions are sent to the application backend and its AI provider. "
                           "Avoid sharing identifying information. New chat clears the on-screen conversation.")
                st.caption("Service connected" if online else "Service unavailable — please try again shortly.")
    if not online:
        st.markdown('<div class="connection-notice" role="status">'
                    '<span aria-hidden="true">○</span> The service is unavailable right now. '
                    'You can still read your conversation.</div>', unsafe_allow_html=True)


def render_intro():
    st.markdown('''<section class="intro">
        <p class="eyebrow">THYROID HEALTH, IN PLAIN WORDS</p>
        <h1>Make room for<br><em>a little clarity.</em></h1>
        <p class="intro-description">Tests, unfamiliar terms, the questions in between.<br>
        Let’s make thyroid health easier to understand.</p>
        <span class="evidence-note">Grounded in thyroid-health references</span>
        </section>''', unsafe_allow_html=True)


def render_suggestions(has_messages, busy, on_select):
    with st.container(key="suggestions"):
        if has_messages:
            with st.expander("Explore a question", expanded=False):
                _prompt_chips(busy, on_select)
        else:
            st.markdown('<p class="suggestion-label">A place to start</p>', unsafe_allow_html=True)
            _prompt_chips(busy, on_select)


def _prompt_chips(busy, on_select):
    with st.container(horizontal=True, wrap=True, gap="small"):
        for prompt_id, question in PROMPTS:
            st.button(question, key=f"suggestion_{prompt_id}", on_click=on_select,
                      args=(question,), disabled=busy, width="content")


def render_message(message, index):
    user = message["role"] == "user"
    with st.container(key=f"{'user' if user else 'assistant'}_message_{index}"):
        if user:
            st.markdown(f'<div class="user-message" aria-label="Your message">'
                        f'{escape(message["content"])}</div>', unsafe_allow_html=True)
            return
        st.markdown('<div class="assistant-author"><span class="mini-mark" aria-hidden="true">t.</span>'
                    '<span>ThyBot</span></div>', unsafe_allow_html=True)
        guardrail = message.get("guardrail")
        if guardrail:
            label, kind = GUARDRAILS.get(guardrail, ("A quick note", "scope"))
            st.markdown(f'<div class="guardrail-label {kind}">{escape(label)}</div>', unsafe_allow_html=True)
        if message.get("request_error"):
            st.markdown('<div class="guardrail-label dosage" role="alert">Connection interrupted</div>',
                        unsafe_allow_html=True)
        # Native Markdown keeps headings, tables, links and code-copy controls.
        st.markdown(message["answer"])
        sources = message.get("sources", [])
        if sources:
            pills = ''.join(f'<span class="source-pill" title="{escape(source, quote=True)}">'
                            f'{escape(source.removesuffix(".pdf").replace("_", " "))}</span>'
                            for source in dict.fromkeys(sources))
            st.markdown(f'<div class="sources"><span class="source-label">SOURCES</span>{pills}</div>',
                        unsafe_allow_html=True)
        if message.get("disclaimer"):
            st.caption(message["disclaimer"])


def render_typing():
    st.markdown('<div class="thinking" role="status" aria-live="polite">'
                '<span class="mini-mark" aria-hidden="true">t.</span>'
                '<span>Finding a little clarity</span>'
                '<span class="thinking-dots" aria-hidden="true"><i></i><i></i><i></i></span></div>',
                unsafe_allow_html=True)
