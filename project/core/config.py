# This is core setting for entire project
# You can import these info anywhere in the pj

import os
from dotenv import load_dotenv

load_dotenv()

# Notion Related
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_SCHOOLS_DB_ID = os.getenv("NOTION_SCHOOLS_DB_ID")
NOTION_TEACHERS_DB_ID = os.getenv("NOTION_TEACHERS_DB_ID")
NOTION_NARRATIVES_DB_ID = os.getenv("NOTION_NARRATIVES_DB_ID")

# Narrative time-window
# Test:15min / Develop:1080 , change the blow from .env
NARRATIVE_WINDOW_MINUTES = int(os.getenv("NARRATIVE_WINDOW_MINUTES","15"))