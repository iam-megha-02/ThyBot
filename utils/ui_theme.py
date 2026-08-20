"""
Shared visual theme for the Streamlit UI.

Reuses the design language already established in this project's
planning documents (deep clinical teal accent, Spectral serif for
display type, Public Sans for body text, IBM Plex Mono for data/
labels) — carried into the actual running app for continuity, rather
than leaving it on Streamlit's unstyled default look.
"""

import streamlit as st

_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,500;0,600;1,400&family=Public+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">

<style>
:root {
  --bg: #faf9f5;
  --surface: #ffffff;
  --surface-2: #f1efe7;
  --text: #1b1f1c;
  --text-dim: #454e49;
  --muted: #6b726c;
  --border: #e2ded2;
  --accent: #0e6b5c;
  --accent-ink: #0a4d43;
  --accent-soft: #e4f1ec;
}

html, body, [class*="css"] {
  font-family: 'Public Sans', -apple-system, sans-serif;
}

h1, h2, h3, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
  font-family: 'Spectral', Georgia, serif !important;
  letter-spacing: -0.01em;
  color: var(--text);
}

[data-testid="stAppViewContainer"] { background-color: var(--bg); }
[data-testid="stHeader"] { background-color: transparent; }

[data-testid="stMain"] .block-container {
  max-width: 900px !important;
  margin-left: auto !important;
  margin-right: auto !important;
  padding-top: 2.2rem;
}

/* Streamlit's own Deploy/menu chrome — not relevant once this is a
   finished piece rather than an in-progress dev session. */
[data-testid="stToolbar"] { visibility: hidden; }

/* ---- Sidebar ---- */
[data-testid="stSidebar"] {
  background-color: var(--surface-2);
  border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }

.sidebar-brand {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-bottom: 14px;
  margin-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.sidebar-brand .wordmark {
  font-family: 'Spectral', serif;
  font-weight: 600;
  font-size: 1.4rem;
  color: var(--text);
  line-height: 1.1;
}
.sidebar-brand .tagline {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.68rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
}

/* Nav buttons — full-width, left-aligned, active page uses Streamlit's
   own primary/secondary button distinction rather than fragile custom
   state-tracking against internal widget DOM. */
[data-testid="stSidebar"] .stButton > button {
  width: 100%;
  text-align: left;
  justify-content: flex-start;
  border-radius: 8px;
  font-family: 'Public Sans', sans-serif;
  font-weight: 500;
  font-size: 0.92rem;
  padding: 0.5rem 0.85rem;
  margin-bottom: 3px;
}
[data-testid="stSidebar"] .stButton > button[kind="secondary"] {
  background-color: transparent;
  border-color: transparent;
  color: var(--text-dim);
}
[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
  background-color: var(--surface);
  border-color: var(--border);
  color: var(--text);
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
  background-color: var(--accent);
  border-color: var(--accent);
  box-shadow: 0 1px 2px rgba(14,107,92,0.25);
}

/* ---- Page header block ---- */
.page-kicker {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.72rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--accent-ink);
  margin-bottom: 6px;
}
.page-title {
  font-family: 'Spectral', serif;
  font-weight: 600;
  font-size: 2.1rem;
  color: var(--text);
  margin-bottom: 4px;
  line-height: 1.15;
}
.page-desc {
  color: var(--text-dim);
  font-size: 1.02rem;
  max-width: 62ch;
  margin-bottom: 1.6rem;
}

/* ---- Alerts ---- */
[data-testid="stAlert"] {
  border-radius: 10px;
  border: 1px solid var(--border);
  font-family: 'Public Sans', sans-serif;
}

/* ---- Buttons (main content) ---- */
.stButton > button, [data-testid="stFormSubmitButton"] > button {
  border-radius: 8px;
  font-family: 'Public Sans', sans-serif;
  font-weight: 600;
}
.stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] > button[kind="primary"] {
  background-color: var(--accent);
  border-color: var(--accent);
}
.stButton > button[kind="primary"]:hover, [data-testid="stFormSubmitButton"] > button[kind="primary"]:hover {
  background-color: var(--accent-ink);
  border-color: var(--accent-ink);
}

/* ---- Chat ---- */
[data-testid="stChatMessage"] {
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: 0 1px 2px rgba(20,20,15,0.05);
}

/* ---- Cards ---- */
.thy-card {
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
  box-shadow: 0 1px 2px rgba(20,20,15,0.04);
  margin-bottom: 10px;
}
.thy-card .label {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}
.thy-card .value {
  font-family: 'Spectral', serif;
  font-weight: 600;
  font-size: 1.25rem;
  color: var(--text);
  margin-top: 2px;
}
.thy-card .meta {
  font-size: 0.82rem;
  color: var(--text-dim);
  margin-top: 4px;
}
.thy-card.flag { border-left: 3px solid var(--warning, #9a6413); }

[data-testid="stDataFrame"] {
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--border);
}
</style>
"""


def inject_custom_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(kicker: str, title: str, description: str) -> None:
    st.markdown(
        f'<div class="page-kicker">{kicker}</div>'
        f'<div class="page-title">{title}</div>'
        f'<div class="page-desc">{description}</div>',
        unsafe_allow_html=True,
    )


def render_sidebar_brand() -> None:
    st.markdown(
        '<div class="sidebar-brand">'
        '<div class="wordmark">ThyBot</div>'
        '<div class="tagline">Thyroid Care Copilot</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def card(label: str, value: str, meta: str = "", flag: bool = False) -> None:
    meta_html = f'<div class="meta">{meta}</div>' if meta else ""
    flag_class = " flag" if flag else ""
    st.markdown(
        f'<div class="thy-card{flag_class}"><div class="label">{label}</div>'
        f'<div class="value">{value}</div>{meta_html}</div>',
        unsafe_allow_html=True,
    )
