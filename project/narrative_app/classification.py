from typing import List, Tuple, Any
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

def classify_subject(raw_text:str) -> str:
    # recommend Subject-Tags based on the raw_text
    # return subject_tags;
    if not raw_text.strip():
        return None
    
    system_prompt= (
        "You are a classifier for school lesson narratives."
        "From the given text, choose appropriate subject tags"
        "from the provided lists"
        "Only use tags from the lists. Return a JSON object with fields"
        '"subject_tags" with a list of strings'
    )

    user_prompt=f"""
    
[TEXT]
{raw_text}"

[AVAILABLE SUBJECT TAGS]
{",".join(SUBJECT_TAGS)}
    
Rules:
- Only use tags from the available lists.
- subject_tags: choose only one tag that fit best
- If unsure, return Return JSON like: "subject_tags":"None"

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

      if subject_tag == "None" or not subject_tag:
         return "None"
      
      return subject_tag
    except Exception as e:
       logger.exception("Error in classify_subject: %s", e)
       return "None"

