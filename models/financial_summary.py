from pydantic import BaseModel
from typing import Literal, List

class FinancialSummary(BaseModel):
    ticker: str
    period: str
    trend_12m: Literal["up", "down", "flat", "unknown"]
    key_metrics: List[KeyMetric]
    narrative: str