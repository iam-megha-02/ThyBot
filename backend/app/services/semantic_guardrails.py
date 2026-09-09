from sentence_transformers import SentenceTransformer, util

_model = SentenceTransformer("all-MiniLM-L6-v2")

EMERGENCY_REFERENCE_PHRASES = [
    "I want to end my life",
    "I am having thoughts of suicide",
    "I am having severe chest pain",
    "I can't breathe",
    "I am having a seizure right now",
    "I am bleeding severely and can't stop it",
    "I am gasping for air and struggling to breathe right now",
    "Someone near me is struggling to breathe or gasping for air right now",
]

DOSAGE_REFERENCE_PHRASES = [
    "What dose of medication should I take",
    "Should I increase or decrease my medication dose",
    "Is it safe to change how much medication I take",
    "Should I stop taking my medication",
    "Calculate the exact medication dose I personally should take",
    "What amount of medication should I give my child",
    "Convert my prescription into a different medication amount",
]

_emergency_embeddings = _model.encode(EMERGENCY_REFERENCE_PHRASES, convert_to_tensor=True)
_dosage_embeddings = _model.encode(DOSAGE_REFERENCE_PHRASES, convert_to_tensor=True)


def _max_similarity(question: str, reference_embeddings) -> float:
    question_embedding = _model.encode(question, convert_to_tensor=True)
    scores = util.cos_sim(question_embedding, reference_embeddings)[0]
    return float(scores.max())


def semantic_emergency_score(question: str) -> float:
    return _max_similarity(question, _emergency_embeddings)


def semantic_dosage_score(question: str) -> float:
    return _max_similarity(question, _dosage_embeddings)