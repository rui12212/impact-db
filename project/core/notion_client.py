from notion_client import Client
from core.config import NOTION_API_KEY

# normal way of get_notion_clinet()

_notion_client = None

def get_notion_client() -> Client:
    # return singleton of Notion
    global _notion_client
    if _notion_client is None:
        if NOTION_API_KEY is None:
            raise RuntimeError("Notion_TOKEN is not set in environment")
        _notion_client = Client(auth=NOTION_API_KEY)
    return _notion_client