from notion_client import Client
from core.config import NOTION_PORTFOLIO_API_KEY

_notion_client = None

def get_notion_client() -> Client:
    global _notion_client
    if _notion_client is None:
        if NOTION_PORTFOLIO_API_KEY is None:
            raise RuntimeError("NOTION_PORTFOLIO_API_KEY is not set in environment")
        _notion_client = Client(auth=NOTION_PORTFOLIO_API_KEY)
    return _notion_client
