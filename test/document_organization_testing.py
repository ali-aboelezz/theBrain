import pytest
from src.DocumentOrganizationAgent import DocumentIntelligencePipeline

@pytest.fixture(scope="module")
def pipeline():
    pipeline = DocumentIntelligencePipeline()
    pipeline.__init__()  
    return pipeline

# ========== NEGATIVE CASES (Expect category to be 'non-sense') ==========

def test_empty_text_input(pipeline):
    text = ""
    result = pipeline.analyze_document(text)
    assert result["document_category"].lower() == "non-sense"
    assert result["summary"] != ""

def test_meaningless_text_input(pipeline):
    text = "asdf asdf asdf lkjf lkjf lkjf"
    result = pipeline.analyze_document(text)
    assert result["document_category"].lower() == "non-sense"
    assert result["summary"] != ""

def test_random_symbol_input(pipeline):
    text = "@#$%^&*()_+}{[]"
    result = pipeline.analyze_document(text)
    assert result["document_category"].lower() == "non-sense"
    assert result["summary"] != ""

# ========== POSITIVE CASES ==========

def test_similar_job_application_1(pipeline):
    text = """Dear HR Team,
    I’m writing to apply for the role of Data Scientist at your company.
    I have 3 years of experience in machine learning and data analysis.
    I’m eager to bring my skills to your innovative team.
    Best regards, John"""
    result = pipeline.analyze_document(text)
    assert result["document_category"].lower() not in ["non-sense", ""]
    assert result["summary"] != ""
    return result["document_category"].lower()

def test_similar_job_application_2(pipeline):
    text = """Dear Hiring Manager,
    I’m excited to apply for the AI Engineer role.
    My background in NLP, deep learning, and Python development aligns with your needs.
    Looking forward to contributing to your team.
    Best, Ali"""
    result = pipeline.analyze_document(text)
    assert result["document_category"].lower() not in ["non-sense", ""]
    assert result["summary"] != ""
    return result["document_category"].lower()

def test_category_consistency_for_valid_inputs(pipeline):
    cat1 = test_similar_job_application_1(pipeline)
    cat2 = test_similar_job_application_2(pipeline)
    assert cat1 == cat2, f"Expected same category, but got '{cat1}' and '{cat2}'"

# ========== SEMANTICALLY AMBIGUOUS INPUT ==========

def test_ambiguous_text_input(pipeline):
    text = "The system calculates the revenue based on past trends. Efficiency must be optimized."
    result = pipeline.analyze_document(text)
    assert result["document_category"].lower() not in ["", None]
    assert result["summary"] != ""