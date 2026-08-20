# ------------------ IMPORTS ------------------
import streamlit as st
import pandas as pd
from langchain_core.messages import HumanMessage
from utils.web_search import perform_web_search
from models.llm import get_groq_model
from utils.rag_utils import load_and_split_pdf, embed_chunks, retrieve_relevant_chunks, load_pdf_text
from utils.lab_extraction import extract_lab_values, extract_collection_date, is_plausible
from utils.lab_history import (
    get_engine,
    init_db,
    get_session_factory,
    get_or_create_default_patient,
    save_lab_results,
    get_lab_history,
    format_history_for_prompt,
)
from utils.medication_timing import check_medication_timing, InteractionSeverity, DISCLAIMER
from utils.guardrails import check_input_safety, ensure_disclaimer
from utils.router import classify_intent
from utils.knowledge_base import load_knowledge_base, retrieve_with_population_filter, POPULATION_GENERAL
from utils.observability import new_trace_id, span
from utils.ui_theme import inject_custom_css, page_header, render_sidebar_brand, card
from config.config import DATABASE_URL


# ------------------ KNOWLEDGE BASE ------------------
@st.cache_resource
def get_clinical_knowledge_base():
    """Loaded once per process from the pre-built index on disk (see
    scripts/build_knowledge_base.py) — not rebuilt per session."""
    return load_knowledge_base()


# ------------------ DATABASE ------------------
@st.cache_resource
def get_db_session_factory():
    engine = get_engine(DATABASE_URL)
    init_db(engine)
    return get_session_factory(engine)


# ------------------ UTILS ------------------
def detect_thyroid_type(tsh, t3, t4):
    if tsh > 4.0 and (t3 < 2.3 or t4 < 0.8):
        return "Hypothyroidism"
    elif tsh < 0.4 and (t3 > 4.2 or t4 > 1.8):
        return "Hyperthyroidism"
    elif 0.4 <= tsh <= 4.0 and 2.3 <= t3 <= 4.2 and 0.8 <= t4 <= 1.8:
        return "Normal"
    else:
        return "Borderline / Consult Physician"


# ------------------ PAGE FUNCTIONS ------------------

def patient_profile_page():
    page_header("Profile", "Patient Profile", "Enter basic and thyroid health information.")

    with st.form("profile_form"):
        name = st.text_input("Full Name")
        age = st.number_input("Age", min_value=0, step=1)
        gender = st.selectbox("Gender", ["Female", "Male", "Other"])

        st.markdown("### Thyroid Lab Values")
        tsh = st.number_input("TSH (mIU/L)", step=0.1, format="%.2f")
        t3 = st.number_input("Free T3 (pg/mL)", step=0.1, format="%.2f")
        t4 = st.number_input("Free T4 (ng/dL)", step=0.1, format="%.2f")

        st.markdown("### Other Information (Optional)")
        weight = st.number_input("Weight (kg)", step=0.1)
        height = st.number_input("Height (cm)", step=0.1)
        symptoms = st.text_area("Symptoms", placeholder="Fatigue, hair loss, weight gain...")
        medication = st.text_area("Ongoing Medications")

        submitted = st.form_submit_button("Save Profile")

        if submitted:
            thyroid_type = detect_thyroid_type(tsh, t3, t4)
            st.session_state.patient_profile = {
                "name": name,
                "age": age,
                "gender": gender,
                "tsh": tsh,
                "t3": t3,
                "t4": t4,
                "thyroid_type": thyroid_type,
                "weight": weight,
                "height": height,
                "symptoms": symptoms,
                "medication": medication
            }
            st.success(f"✅ Profile Saved! Thyroid Type: **{thyroid_type}**")


def lab_reports_page():
    page_header("Lab Reports", "Track Your Thyroid Labs", "Upload a report to extract TSH/T3/T4 and track them over time.")

    Session = get_db_session_factory()
    db_session = Session()
    patient = get_or_create_default_patient(db_session)

    uploaded_file = st.file_uploader("Upload a lab report (PDF)", type=["pdf"], key="lab_report_upload")
    if uploaded_file:
        raw_text = load_pdf_text(uploaded_file)
        extracted = extract_lab_values(raw_text)
        detected_date = extract_collection_date(raw_text)

        if not extracted:
            st.warning(
                "No TSH/T3/T4 values recognized in this report. Formats vary a lot "
                "between labs — this parser was built against one real layout, not "
                "a general-purpose OCR system."
            )
        else:
            st.markdown("### Extracted values — review before saving")
            date_input = st.text_input(
                "Collection date (YYYY-MM-DD)",
                value=detected_date or "",
                help="Auto-detected from the report where possible.",
            )
            value_cols = st.columns(len(extracted))
            for col, result in zip(value_cols, extracted):
                flag = not is_plausible(result)
                with col:
                    card(
                        label=f"{result.test} ({result.variant})",
                        value=f"{result.value} {result.unit or ''}",
                        meta=(
                            f"ref [{result.reference_low}–{result.reference_high}] · {result.reported_status}"
                            + (" · ⚠️ unusual, double-check" if flag else "")
                        ),
                        flag=flag,
                    )

            if st.button("Save to lab history"):
                save_lab_results(db_session, patient.id, extracted, collection_date_str=date_input or None)
                st.success("Saved.")
                st.rerun()

    st.markdown("### History")
    history = get_lab_history(db_session, patient.id)
    if not history:
        st.info("No lab history yet — upload a report above.")
    else:
        history_df = pd.DataFrame(
            [{"date": h.collection_date, "test": h.test, "value": h.value} for h in history]
        )
        for test_name in history_df["test"].unique():
            test_df = history_df[history_df["test"] == test_name].dropna(subset=["date"]).set_index("date")
            if not test_df.empty:
                st.markdown(f"**{test_name} trend**")
                st.line_chart(test_df["value"])
        st.markdown("**All records**")
        st.dataframe(history_df, use_container_width=True)

    db_session.close()


def medications_page():
    page_header(
        "Medications",
        "Medication Timing",
        "Check known timing interactions between levothyroxine and other medications, supplements, or foods.",
    )
    st.caption(DISCLAIMER)

    if "med_items" not in st.session_state:
        st.session_state.med_items = []

    col1, col2 = st.columns([3, 1])
    with col1:
        new_item = st.text_input("Add a medication, supplement, or food")
    with col2:
        if st.button("Add") and new_item:
            st.session_state.med_items.append(new_item)

    for idx, item in enumerate(st.session_state.med_items):
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(f"- {item}")
        with col2:
            if st.button("Remove", key=f"remove_med_{idx}"):
                st.session_state.med_items.pop(idx)
                st.rerun()

    if st.button("Check Timing") and st.session_state.med_items:
        for result in check_medication_timing(st.session_state.med_items):
            if result.severity == InteractionSeverity.SEPARATE_STRICT:
                st.error(f"**{result.item}** — {result.guidance}")
            elif result.severity == InteractionSeverity.SEPARATE_CAUTION:
                st.warning(f"**{result.item}** — {result.guidance}")
            else:
                st.info(f"**{result.item}** — {result.guidance}")


def chat_page():
    chat_model = get_groq_model()

    if "response_mode" not in st.session_state:
        st.session_state.response_mode = "Concise"
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "patient_profile" not in st.session_state:
        st.session_state.patient_profile = {}

    page_header("Chat", "Ask ThyBot", "Ask anything about thyroid health — grounded in guidelines where possible, always disclosed when it isn't.")

    with st.sidebar:
        st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
        st.session_state.response_mode = st.radio(
            "Response Style",
            ["Concise", "Detailed"],
            index=0 if st.session_state.response_mode == "Concise" else 1
        )

    uploaded_file = st.file_uploader("Upload a PDF (lab report)", type=["pdf"])
    if uploaded_file:
        st.session_state["chunks"] = load_and_split_pdf(uploaded_file)
        st.session_state["faiss_index"] = embed_chunks(st.session_state["chunks"])
        st.success("Document embedded for retrieval!")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Type your question here..."):
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            trace_id = new_trace_id()

            # Input guardrail runs before any branching, LLM call, or DB
            # lookup below — emergency/dosage questions never reach the
            # model at all, they get a fixed safe response.
            with span(trace_id, "guardrail_check") as ctx:
                guardrail = check_input_safety(prompt)
                ctx["blocked"] = guardrail.blocked
                ctx["reason"] = guardrail.reason

            history_rows = []
            citation_sources = []

            if guardrail.blocked:
                reply = guardrail.response
            else:
                with st.spinner("Thinking..."):
                    profile = st.session_state.patient_profile
                    thyroid_type = profile.get("thyroid_type", "Not set")

                    system_prompt = (
                        f"You are a helpful medical assistant. The user has {thyroid_type}. Keep the answer brief and to the point."
                        if st.session_state.response_mode == "Concise"
                        else f"You are a helpful medical assistant. The user has {thyroid_type}. Provide a detailed explanation."
                    )

                    # Single classification step replaces the old dual
                    # keyword gates — one decision, trusted downstream,
                    # instead of two independent checks that could disagree
                    # (e.g. "What does TSH mean?" used to trip the trend
                    # check on the substring "tsh" alone).
                    with span(trace_id, "router") as ctx:
                        decision = classify_intent(
                            prompt, has_uploaded_document="faiss_index" in st.session_state
                        )
                        ctx["population"] = decision.population
                        ctx["intent_label"] = decision.intent_label
                        ctx["needs_lab_history"] = decision.needs_lab_history
                        ctx["needs_document_context"] = decision.needs_document_context
                    trend_context = ""
                    if decision.needs_lab_history:
                        Session = get_db_session_factory()
                        db_session = Session()
                        patient = get_or_create_default_patient(db_session)
                        history_rows = get_lab_history(db_session, patient.id)
                        db_session.close()
                        trend_context = format_history_for_prompt(history_rows)

                    if decision.needs_lab_history and not history_rows:
                        reply = (
                            "I don't have any lab history saved yet — upload a report "
                            "on the Lab Reports page first, and I'll be able to answer "
                            "questions like this."
                        )
                    elif trend_context:
                        full_prompt = (
                            f"{trend_context}\n\n"
                            "Only reference the values listed above — do not invent or "
                            "estimate any value not shown. This is educational "
                            "information, not a diagnosis; remind the user to discuss "
                            "any trend with their doctor.\n\n"
                            f"User: {prompt}\n\n"
                            f"Answer {('briefly' if st.session_state.response_mode == 'Concise' else 'in detail')}"
                        )
                        response = chat_model.invoke(full_prompt)
                        reply = response.content if hasattr(response, "content") else response
                    elif decision.needs_document_context and "faiss_index" in st.session_state:
                        docs = retrieve_relevant_chunks(prompt, st.session_state["faiss_index"])
                        context = "\n\n".join([doc.page_content for doc in docs])
                        full_prompt = f"Context: {context}\n\nUser: {prompt}\n\nAnswer {('briefly' if st.session_state.response_mode == 'Concise' else 'in detail')}"
                        response = chat_model.invoke(full_prompt)
                        reply = response.content if hasattr(response, "content") else response
                    else:
                        # Persistent clinical knowledge base — the 10
                        # bundled guideline PDFs, population-filtered so a
                        # pregnancy question surfaces maternal guidance
                        # instead of the general reference range.
                        with span(trace_id, "kb_retrieval", population=decision.population) as ctx:
                            try:
                                kb = get_clinical_knowledge_base()
                                kb_docs = retrieve_with_population_filter(kb, prompt, decision.population)
                            except Exception as exc:
                                kb_docs = []  # index not built yet — fall through to plain chat below
                                ctx["load_error"] = f"{type(exc).__name__}: {exc}"
                            ctx["hit_count"] = len(kb_docs)
                            ctx["sources"] = sorted({d.metadata["source"] for d in kb_docs})

                        if kb_docs:
                            citation_sources = sorted({d.metadata["source"] for d in kb_docs})
                            context = "\n\n".join(d.page_content for d in kb_docs)
                            full_prompt = (
                                f"Context from clinical guidelines: {context}\n\n"
                                "Base your answer on this context where relevant. "
                                f"User: {prompt}\n\n"
                                f"Answer {('briefly' if st.session_state.response_mode == 'Concise' else 'in detail')}"
                            )
                            response = chat_model.invoke(full_prompt)
                            reply = response.content if hasattr(response, "content") else response
                        else:
                            # Confidence-gated fallback: the clinical KB had
                            # nothing relevant, so try a web search before
                            # giving up and answering ungrounded. DuckDuckGo
                            # rate-limits aggressively with no official API —
                            # any failure here is expected, not exceptional,
                            # and just falls through to plain chat below.
                            web_results = []
                            with span(trace_id, "web_search_fallback") as ctx:
                                try:
                                    web_results = perform_web_search(prompt, max_results=3)
                                except Exception as exc:
                                    # Expected outcome, not exceptional — see
                                    # utils/web_search.py's docstring. Logged
                                    # as context, not re-raised.
                                    ctx["failed_as_expected"] = f"{type(exc).__name__}: {exc}"
                                ctx["result_count"] = len(web_results)

                            if web_results:
                                web_sources = [r.split(" (")[-1].rstrip(")") for r in web_results]
                                context = "\n\n".join(web_results)
                                full_prompt = (
                                    f"Context from a web search (not a verified clinical source — "
                                    f"note this to the user if relevant): {context}\n\n"
                                    f"User: {prompt}\n\n"
                                    f"Answer {('briefly' if st.session_state.response_mode == 'Concise' else 'in detail')}"
                                )
                                response = chat_model.invoke(full_prompt)
                                reply = response.content if hasattr(response, "content") else response
                                citation_sources = [f"(unverified web source) {s}" for s in web_sources]
                            else:
                                response = chat_model.invoke([
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": prompt}
                                ])
                                reply = response.content if hasattr(response, "content") else response

                    # Output guardrail — enforced in code rather than trusted
                    # to the model's memory of the system prompt.
                    reply = ensure_disclaimer(reply)

            st.markdown(reply)
            if history_rows:
                with st.expander("Lab values used for this answer"):
                    for record in history_rows:
                        st.write(
                            f"{record.test}: {record.value} {record.unit or ''} "
                            f"on {record.collection_date} ({record.reported_status})"
                        )
            if citation_sources:
                with st.expander("Sources"):
                    for source in citation_sources:
                        st.write(f"- {source}")
            st.session_state.messages.append({"role": "assistant", "content": reply})


def meal_analysis_page():
    page_header("Meal Analysis", "Is This Thyroid-Friendly?", "Add food items to check their thyroid impact and medication-timing relevance.")

    df = pd.read_csv("data/Indian_Food_Nutrition_Processed.csv")
    chat_model = get_groq_model()

    if "meal_items" not in st.session_state:
        st.session_state.meal_items = []

    col1, col2 = st.columns([3, 1])
    with col1:
        new_item = st.text_input("Enter food item")
    with col2:
        if st.button("Add") and new_item:
            st.session_state.meal_items.append(new_item)

    for idx, item in enumerate(st.session_state.meal_items):
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(f"- {item}")
        with col2:
            if st.button("Remove", key=f"remove_{idx}"):
                st.session_state.meal_items.pop(idx)
                st.rerun()

    if st.button("Analyze Meal"):
        profile = st.session_state.get("patient_profile", {})
        thyroid_type = profile.get("thyroid_type", "Not set")

        if thyroid_type == "Not set":
            st.error("Please fill in your thyroid profile first from the Patient Profile page.")
            return

        for item in st.session_state.meal_items:
            match = df[df['Dish Name'].str.lower() == item.lower()]
            if not match.empty:
                row = match.iloc[0]
                nutrients = f"Calories: {row['Calories (kcal)']:.0f} kcal | Protein: {row['Protein (g)']}g | Sugar: {row['Free Sugar (g)']}g"
                impact = row['Thyroid_Impact']
                timing_note = row.get('Medication_Timing_Note', 'No known timing concern')
                prompt = (
                    f"The user has {thyroid_type}. They are eating '{item}', which has the following nutritional values: {nutrients}. "
                    f"The dataset marks its thyroid impact as '{impact}'. Medication timing note: '{timing_note}'. "
                    f"Is this good or bad for the user and why? Also suggest what else could be added or avoided."
                )
            else:
                prompt = (
                    f"The user has {thyroid_type}. They are eating '{item}', but it is not found in the dataset. "
                    f"Based on general nutritional knowledge, is this good or bad for thyroid health? Give a brief reason and suggest improvements."
                )

            response = chat_model.invoke(prompt)
            reply = response.content if hasattr(response, "content") else response
            reply = ensure_disclaimer(reply)

            with st.container():
                st.markdown(f"#### 🍽️ **{item.title()}**")
                if not match.empty:
                    st.info(f"**Nutrients**: {nutrients}\n\n**Impact**: {impact}")
                    if timing_note != "No known timing concern":
                        st.warning(f"**Medication timing**: {timing_note}")
                st.success(reply)


# ------------------ MAIN ------------------

NAV_ITEMS = (
    ("Chat", "💬"),
    ("Patient Profile", "👤"),
    ("Lab Reports", "🧪"),
    ("Medications", "💊"),
    ("Meal Analysis", "🍽️"),
)


def main():
    st.set_page_config(page_title="ThyBot", page_icon="assets/logo.png", layout="wide")
    inject_custom_css()

    if "page" not in st.session_state:
        st.session_state.page = "Chat"

    with st.sidebar:
        st.image("assets/logo.png", width=64)
        render_sidebar_brand()
        for name, icon in NAV_ITEMS:
            is_active = st.session_state.page == name
            if st.button(
                f"{icon}  {name}",
                key=f"nav_{name}",
                type="primary" if is_active else "secondary",
            ):
                st.session_state.page = name
                st.rerun()

    page = st.session_state.page
    if page == "Chat":
        chat_page()
    elif page == "Patient Profile":
        patient_profile_page()
    elif page == "Lab Reports":
        lab_reports_page()
    elif page == "Medications":
        medications_page()
    elif page == "Meal Analysis":
        meal_analysis_page()


# ------------------ LAUNCH ------------------

if __name__ == "__main__":
    main()
