from typing import List, Tuple, Any, Optional
import json
import logging

logger = logging.getLogger(__name__)

SUBJECT_TAGS = [
    "Khmer",
    "Math",
    "Science",
    "PE",
    "IT",
    "Reginal Lifeskill Program",
    "None",
]

# use OpenAI
from openai import OpenAI
client = OpenAI()

def classify_subject(raw_text:str) -> Optional[str]:
    # recommend Subject-Tags based on the raw_text
    # return subject_tags;
    if not raw_text.strip():
        return None
    
    system_prompt= (
        "You are a classifier for school lesson narratives."
        "From the given text, choose appropriate subject tags"
        "from the provided lists"
        "Only use tags from the lists. Return a JSON object with fields"
        '"subject_tags" with  string'
    )

    user_prompt=f"""
    
[TEXT]
{raw_text}

[AVAILABLE SUBJECT TAGS]
{",".join(SUBJECT_TAGS)}
    
Rules:
- Only use tags from the available lists.
- subject_tags: choose only ONE tag that fit best
- If unsure, set subject_tags to ""(empty string).

Return JSON like:
{{
"subject_tags": "Math"
}}
"""

    try:
      response = client.chat.completions.create(
         model="gpt-4.1-mini",
         messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
         ],
         response_format={"type": "json_object"},
      )

      content = response.choices[0].message.content
      subject_json_data = json.loads(content)
      subject_tag = subject_json_data.get("subject_tags","")

      if isinstance(subject_tag, list):
         if not subject_tag:
            return None
         subject_tag = subject_tag[0]

      if not isinstance(subject_tag, str):
         logger.warning("subject_tags is not str or list: %r", subject_tag)
         return None
      
      subject_tag = subject_tag.strip()
      if not subject_tag:
         return None
      
      if subject_tag not in SUBJECT_TAGS:
         logger.warning("Unknown subject tag from LLM: %s",subject_tag)
         return None
      
      return subject_tag
    except Exception as e:
       logger.exception("Error in classify_subject: %s", e)
       return "None"

