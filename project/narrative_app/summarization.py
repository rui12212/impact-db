from typing import Optional
import logging
import textwrap
import json

from openai import OpenAI

logger = logging.getLogger(__name__)
client = OpenAI()

def _call_llm_for_summary(prompt: str) -> str:
    # send LLM prompt LLM and return the text
    # if fail return ""
    try:
        resp = client.chat.completions.create(
            model= "gpt-4.1-mini",
            messages=[
                {
                "role": "system",
                "content": (
                    "You are an assistant that summarizes teachers' classroom"
                    "practice narratives in a way that is easy for school staff to read"
                ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )
        content = resp.choices[0].message.content or ""
        return content.strip()
    except Exception as e:
        logger.exception("Error in _call_llm_for_summary: %s", e)

def generate_summary(raw_text: str) -> str:
    # creating Summary from raw text in Narrative

    raw_text = (raw_text or "").strip()
    if not raw_text:
        return ""
    
    user_prompt = textwrap.dedent(
        f"""
        You are given a narrative written by a teacher about a class or educational activity.
        [NARRATIVE]
        {raw_text}

        Task:
        - Summarize the overall class or activity in a concise way.
        - Focus on :
          - What the teacher tried to do (aim / intention)
          - What kind of activity was conducted
          - How Students responded in general
        - Write in 3-6 sentences.
        """
    ).strip()

    return _call_llm_for_summary(user_prompt)

def generate_detailed_content(raw_text: str) -> str:

    raw_text = (raw_text or "").strip()
    if not raw_text:
        return ""
    
    user_prompt = textwrap.dedent(
        f"""
        you are given a narrative written by a teacher about a class or educational activity.

        [NARRATIVE]
        {raw_text}

        Task:
        - Extract the concrete flow and content of the class in more detail
        - Organize the answwer in bullet points or short paragraphs.
        - Include, if possible:
          - Preparation / Introduction
          - Main activity steps
          - How students reacted (with some concrete examples)
          - How the class was wrapped up
        - Do NOT repeat a short summary only. G into more detail so that
        another teacher could imagine reusing this practice.
        """
    ).strip()

    return _call_llm_for_summary(user_prompt)