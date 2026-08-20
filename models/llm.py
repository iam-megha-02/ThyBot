# models/llm.py

import json

from groq import Groq
from config.config import GROQ_API_KEY

client = Groq(api_key=GROQ_API_KEY)

# llama3-70b-8192 (the original model here) was decommissioned by Groq
# at some point after this project's initial commit — Groq's lineup no
# longer includes any Llama models as of this writing. Confirmed live
# against client.models.list() rather than assumed from stale docs.
DEFAULT_MODEL = "openai/gpt-oss-120b"

def get_groq_model():
    class GroqWrapper:
        def invoke(self, prompt_or_messages):
            # If plain string, convert to message format
            if isinstance(prompt_or_messages, str):
                prompt_or_messages = [{"role": "user", "content": prompt_or_messages}]
            response = client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=prompt_or_messages
            )
            return response.choices[0].message.content
    return GroqWrapper()


def get_json_completion(messages, model=DEFAULT_MODEL):
    """
    For structured classification calls (e.g. intent routing), not
    general chat — forces valid JSON output and uses temperature=0
    since a classification should be consistent, not creative.
    Raises on any failure (network, malformed JSON); callers are
    expected to catch and fall back rather than let a routing call
    take down the whole chat response.
    """
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(response.choices[0].message.content)
