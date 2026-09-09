from groq import Groq
from app.core.config import settings
from app.schemas.retrieval import Chunk

client = Groq(api_key=settings.groq_api_key, max_retries=5, timeout=45)

GROUNDED_PROMPT_TEMPLATE = """You are a thyroid health education assistant. Answer the question using ONLY the
context provided below. Do not use any outside knowledge. If the context does not contain
enough information to answer, say so honestly rather than guessing.

Do not diagnose conditions, prescribe treatment, or give medication-dosage advice, even if asked.

Do not add crisis hotlines, emergency phone numbers, or self-harm disclaimers of your own,
even if the topic (e.g. depression) touches on mental health. The application already handles
emergencies separately before you are called. If the provided context itself mentions a crisis
resource, you may repeat it, but only if it is an Indian resource (e.g. the number 112 or the
KIRAN helpline 1800-599-0019); never invent or reference a non-Indian number such as 911 or 988.

Answer naturally and directly, as if you already know this information, do not say phrases
like "based on the context," "according to the provided information," or similar meta-commentary
about where the answer comes from. Just answer the question plainly.

Context:
{context}

Question: {question}

Answer:"""

FIXED_DISCLAIMER = (
    "This is educational information, not medical advice. "
    "Please consult a healthcare provider for guidance specific to your situation."
)


def generate_grounded_answer(question: str, chunks: list[Chunk]) -> dict:
    context = "\n\n".join(f"[Source: {c.source_file}]\n{c.text}" for c in chunks)
    prompt = GROUNDED_PROMPT_TEMPLATE.format(context=context, question=question)

    response = client.chat.completions.create(
        model="qwen/qwen3.8-27b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=600,
    )

    return {
        "answer": response.choices[0].message.content,
        "sources": sorted(set(c.source_file for c in chunks)),
        "disclaimer": FIXED_DISCLAIMER,
    }