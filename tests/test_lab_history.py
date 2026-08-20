import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.db_models import Base
from utils.lab_extraction import extract_lab_values
from utils.lab_history import (
    format_history_for_prompt,
    get_lab_history,
    get_or_create_default_patient,
    looks_like_lab_trend_question,
    save_lab_results,
)

# Tests run against in-memory SQLite, not the Docker Postgres container —
# same SQLAlchemy code path, no Docker dependency, runs in milliseconds.
# See docker-compose.yml / .env for the real Postgres connection.


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db_session = session_factory()
    yield db_session
    db_session.close()


def test_save_and_retrieve_a_single_result(session):
    patient = get_or_create_default_patient(session)
    results = extract_lab_values("TSH 5.2 0.4 - 4.0 High mIU/L")

    save_lab_results(session, patient.id, results, collection_date_str="2024-01-15")
    history = get_lab_history(session, patient.id, test="TSH")

    assert len(history) == 1
    assert history[0].value == 5.2
    assert history[0].reported_status == "High"


def test_history_accumulates_across_multiple_uploads_in_date_order(session):
    patient = get_or_create_default_patient(session)

    # Uploaded out of chronological order — the later report first —
    # to make sure retrieval sorts by collection_date, not insert order.
    save_lab_results(
        session, patient.id, extract_lab_values("TSH 2.1 0.4 - 4.0 Normal mIU/L"),
        collection_date_str="2024-06-15",
    )
    save_lab_results(
        session, patient.id, extract_lab_values("TSH 5.2 0.4 - 4.0 High mIU/L"),
        collection_date_str="2024-01-15",
    )

    history = get_lab_history(session, patient.id, test="TSH")
    assert [h.value for h in history] == [5.2, 2.1]
    assert [str(h.collection_date) for h in history] == ["2024-01-15", "2024-06-15"]


def test_get_or_create_default_patient_is_idempotent(session):
    first = get_or_create_default_patient(session)
    second = get_or_create_default_patient(session)
    assert first.id == second.id


def test_history_filtered_by_test_excludes_other_analytes(session):
    patient = get_or_create_default_patient(session)
    text = "TSH 2.0 0.4 - 4.0 Normal mIU/L T4 (Thyroxine) 9.0 5.0 - 12.0 Normal ug/dL"

    save_lab_results(session, patient.id, extract_lab_values(text), collection_date_str="2024-01-15")

    tsh_only = get_lab_history(session, patient.id, test="TSH")
    assert len(tsh_only) == 1
    assert tsh_only[0].test == "TSH"


def test_missing_collection_date_does_not_crash_or_drop_the_record(session):
    patient = get_or_create_default_patient(session)
    results = extract_lab_values("TSH 2.0 0.4 - 4.0 Normal mIU/L")

    save_lab_results(session, patient.id, results, collection_date_str=None)
    history = get_lab_history(session, patient.id)

    assert len(history) == 1
    assert history[0].collection_date is None


@pytest.mark.parametrize("message", [
    "Is my TSH improving?",
    "how are my thyroid levels doing",
    "what's my T4 trend",
    "am I getting better",
])
def test_trend_keywords_are_detected(message):
    assert looks_like_lab_trend_question(message)


@pytest.mark.parametrize("message", [
    "what foods should I avoid",
    "hi there",
    "can I take ibuprofen with my medication",
])
def test_unrelated_messages_are_not_flagged_as_trend_questions(message):
    assert not looks_like_lab_trend_question(message)


def test_format_history_for_prompt_is_empty_for_no_history():
    assert format_history_for_prompt([]) == ""


def test_format_history_for_prompt_includes_dates_values_and_status(session):
    patient = get_or_create_default_patient(session)
    save_lab_results(session, patient.id, extract_lab_values("TSH 5.2 0.4 - 4.0 High mIU/L"), collection_date_str="2024-01-15")
    save_lab_results(session, patient.id, extract_lab_values("TSH 2.1 0.4 - 4.0 Normal mIU/L"), collection_date_str="2024-06-15")

    text = format_history_for_prompt(get_lab_history(session, patient.id))

    assert "TSH:" in text
    assert "2024-01-15: 5.2 miu/l, reference 0.4-4.0 (High)" in text
    assert "2024-06-15: 2.1 miu/l, reference 0.4-4.0 (Normal)" in text
    # oldest first, matching chronological reading order
    assert text.index("2024-01-15") < text.index("2024-06-15")


def test_format_history_for_prompt_groups_by_test(session):
    patient = get_or_create_default_patient(session)
    text_block = "TSH 2.0 0.4 - 4.0 Normal mIU/L T4 (Thyroxine) 9.0 5.0 - 12.0 Normal ug/dL"
    save_lab_results(session, patient.id, extract_lab_values(text_block), collection_date_str="2024-01-15")

    text = format_history_for_prompt(get_lab_history(session, patient.id))

    assert "TSH:" in text
    assert "T4:" in text


def test_two_patients_do_not_see_each_others_history(session):
    patient_a = get_or_create_default_patient(session)
    from models.db_models import Patient
    patient_b = Patient(name="patient-b")
    session.add(patient_b)
    session.commit()

    save_lab_results(session, patient_a.id, extract_lab_values("TSH 2.0 0.4 - 4.0 Normal mIU/L"), collection_date_str="2024-01-15")
    save_lab_results(session, patient_b.id, extract_lab_values("TSH 9.0 0.4 - 4.0 High mIU/L"), collection_date_str="2024-01-15")

    assert [h.value for h in get_lab_history(session, patient_a.id)] == [2.0]
    assert [h.value for h in get_lab_history(session, patient_b.id)] == [9.0]
