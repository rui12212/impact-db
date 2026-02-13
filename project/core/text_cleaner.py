import os, logging
from google import genai
from google.genai import types
from core.gemini_quota import check_and_increment

log = logging.getLogger('impactdb')

def remove_fillers(text: str) -> str:
    """
    Gemini を使い、原文の内容を一切変えずにフィラーだけを除去する。
    """
    if not text or not text.strip():
        return text

    check_and_increment()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are a text cleaner. Your ONLY task is to remove filler words "
                "and hesitations from the given text. "
                "Fillers include: um, uh, ah, er, hmm, you know, like (when used as filler), "
                "I mean, sort of, kind of, well (when used as filler), so (when used as filler), "
                "basically, actually (when used as filler), right (when used as filler).\n\n"
                "Rules:\n"
                "- Do NOT change the meaning of ANY sentence.\n"
                "- Do NOT rephrase, paraphrase, or summarize.\n"
                "- Do NOT add any new words.\n"
                "- Do NOT fix grammar or improve style.\n"
                "- ONLY remove filler words/hesitations.\n"
                "- Keep all timestamps (e.g. [00:00-00:30]) exactly as they are.\n"
                "- Return the cleaned text only, with no explanation."
            ),
        ),
        contents=[text],
    )
    return response.text.strip()
