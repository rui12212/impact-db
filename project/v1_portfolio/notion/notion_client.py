import logging
from notion_client import Client
from notion_client.errors import APIResponseError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential
from core.config import NOTION_PORTFOLIO_API_KEY

logger = logging.getLogger(__name__)

def _is_rate_limited(exc: BaseException) -> bool:
    return isinstance(exc, APIResponseError) and exc.code == "rate_limited"

_retry_on_rate_limit = retry(
    retry=retry_if_exception(_is_rate_limited),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    stop=stop_after_attempt(5),
    before_sleep=lambda retry_state: logger.warning(
        "Notion rate limited, retrying in %.1fs (attempt %d)",
        retry_state.next_action.sleep,
        retry_state.attempt_number,
    ),
)


class RetryClient:
    def __init__(self, client: Client):
        self._client = client
        self.pages = _RetryPages(client.pages)
        self.databases = _RetryDatabases(client.databases)
        self.blocks = _RetryBlocks(client.blocks)


class _RetryPages:
    def __init__(self, pages):
        self._pages = pages

    @_retry_on_rate_limit
    def retrieve(self, *args, **kwargs):
        return self._pages.retrieve(*args, **kwargs)

    @_retry_on_rate_limit
    def create(self, *args, **kwargs):
        return self._pages.create(*args, **kwargs)

    @_retry_on_rate_limit
    def update(self, *args, **kwargs):
        return self._pages.update(*args, **kwargs)


class _RetryDatabases:
    def __init__(self, databases):
        self._databases = databases

    @_retry_on_rate_limit
    def query(self, *args, **kwargs):
        return self._databases.query(*args, **kwargs)


class _RetryBlocks:
    def __init__(self, blocks):
        self._blocks = blocks
        self.children = _RetryBlockChildren(blocks.children)

    @_retry_on_rate_limit
    def update(self, *args, **kwargs):
        return self._blocks.update(*args, **kwargs)


class _RetryBlockChildren:
    def __init__(self, children):
        self._children = children

    @_retry_on_rate_limit
    def list(self, *args, **kwargs):
        return self._children.list(*args, **kwargs)

    @_retry_on_rate_limit
    def append(self, *args, **kwargs):
        return self._children.append(*args, **kwargs)


_notion_client = None

def get_notion_client() -> RetryClient:
    global _notion_client
    if _notion_client is None:
        if NOTION_PORTFOLIO_API_KEY is None:
            raise RuntimeError("NOTION_PORTFOLIO_API_KEY is not set in environment")
        _notion_client = RetryClient(Client(auth=NOTION_PORTFOLIO_API_KEY))
    return _notion_client
