from pydantic import BaseModel
from typing import Optional, Literal

class Entry(BaseModel):
    date: str
    value: float
    description: Optional[str] = None
    store: Optional[str] = None

class Transaction(BaseModel):
    date: str
    description: Optional[str] = None
    t_type: Literal['in','out','transfer']
    value: float
    account_id: Optional[int] = None
    bucket_id: Optional[int] = None
    goal_id: Optional[int] = None
    store: Optional[str] = None

class Goal(BaseModel):
    name: str
    goal_type: Literal['debt','savings']
    cost: float
    monthly_relief: float = 0.0
    interest_pa: Optional[float] = None
    priority_weight: float = 0.0
