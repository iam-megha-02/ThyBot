from utils.lab_extraction import extract_collection_date, extract_lab_values, is_plausible

# Verbatim text as PyPDFLoader/pdfminer actually extracts it from
# data/Thyroid-Report.pdf — cell labels get glued together across line
# wraps ("ThyroidStimulating" with no space) and whitespace is erratic.
# This is real bundled sample data, not a synthetic fixture.
SAMPLE_REPORT_TEXT = """
Thyroid Profile I Test Report
Patient Information:
 Name: John Doe  Sample Collection Date: 2024-11-29
 Age: 38  Report Generation Date: 2024-12-01
 Gender: Male
Thyroid Profile i Result Reference Range Status Unit
T3
(Triiodothyronine)
110.0 80 - 200 Normal ng/dL
T4 (Thyroxine) 9.0 5.0 – 12.0 Normal µg/dL
TSH (ThyroidStimulating
Hormone)
1.3 0.4 – 4.0 Normal mIU/L
Key Notes for Patients
 Avoid biotin supplements 48 hours before the test for accurate results.
 Results should be interpreted in consultation with a healthcare professional.

www.bootlab.in
"""


def _by_test(results, name):
    return next(r for r in results if r.test == name)


def test_extracts_all_three_analytes():
    results = extract_lab_values(SAMPLE_REPORT_TEXT)
    assert {r.test for r in results} == {"TSH", "T3", "T4"}


def test_tsh_value_range_unit_and_status():
    tsh = _by_test(extract_lab_values(SAMPLE_REPORT_TEXT), "TSH")
    assert tsh.value == 1.3
    assert tsh.reference_low == 0.4
    assert tsh.reference_high == 4.0
    assert tsh.unit == "miu/l"
    assert tsh.reported_status == "Normal"


def test_t3_is_correctly_tagged_as_total_not_free():
    t3 = _by_test(extract_lab_values(SAMPLE_REPORT_TEXT), "T3")
    assert t3.value == 110.0
    assert t3.variant == "total"
    assert t3.unit == "ng/dl"


def test_t4_is_correctly_tagged_as_total_not_free():
    t4 = _by_test(extract_lab_values(SAMPLE_REPORT_TEXT), "T4")
    assert t4.value == 9.0
    assert t4.reference_low == 5.0
    assert t4.reference_high == 12.0
    assert t4.variant == "total"


def test_collection_date_extracted():
    assert extract_collection_date(SAMPLE_REPORT_TEXT) == "2024-11-29"


def test_all_extracted_values_pass_plausibility_check():
    for result in extract_lab_values(SAMPLE_REPORT_TEXT):
        assert is_plausible(result)


def test_free_t3_report_is_not_mistaken_for_total():
    text = "Free T3 (FT3) 3.1 2.3 - 4.2 Normal pg/mL"
    [t3] = extract_lab_values(text)
    assert t3.variant == "free"
    assert t3.value == 3.1


def test_missing_analyte_is_skipped_not_guessed():
    text = "TSH 2.0 0.4 - 4.0 Normal mIU/L"
    results = extract_lab_values(text)
    assert {r.test for r in results} == {"TSH"}


def test_implausible_value_is_flagged():
    from utils.lab_extraction import LabResult

    bogus = LabResult(
        test="TSH", variant="unspecified", value=5000.0, unit="miu/l",
        reference_low=0.4, reference_high=4.0, reported_status=None, raw_snippet="",
    )
    assert not is_plausible(bogus)
