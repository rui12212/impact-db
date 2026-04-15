from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class TelegramUserInfo:
    user_id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None


@dataclass
class PortfolioDecisionResult:
    portfolio_page_id: str
    is_new: bool
    started_at: datetime
    needs_confirmation: bool = False
