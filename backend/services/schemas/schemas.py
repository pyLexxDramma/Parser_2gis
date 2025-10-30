from pydantic import BaseModel, Field, EmailStr, AnyUrl
from typing import Optional, List, Dict, Any, Literal
import uuid


class CompanySearchRequest(BaseModel):
    report_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    company_name: str
    company_site: str
    email: EmailStr


class PlatformStats(BaseModel):
    cards_count: int = 0
    total_rating: Optional[float] = None
    total_reviews: int = 0
    answered_reviews: int = 0
    avg_response_time_days: Optional[int] = None
    avg_response_time_months: Optional[int] = None
    negative_reviews_count: int = 0
    positive_reviews_count: int = 0


class Review(BaseModel):
    text: str
    rating: int
    date: str
    responded: bool = False
    response_text: Optional[str] = None
    response_date: Optional[str] = None
    response_time_str: Optional[str] = None


class CompanyCard(BaseModel):
    name: str
    url: AnyUrl
    rating: Optional[float] = None
    reviews_count: int = 0
    answered_reviews: int = 0
    response_time_str: Optional[str] = None
    negative_reviews_count: int = 0
    positive_reviews_count: int = 0
    reviews: List[Review] = []


class Report(BaseModel):
    report_id: uuid.UUID
    company_name: str
    status: Literal["processing", "completed", "error"]
    error_message: Optional[str] = None

    yandex_stats: Optional[PlatformStats] = None
    yandex_cards: List[CompanyCard] = []

    gis_stats: Optional[PlatformStats] = None
    gis_cards: List[CompanyCard] = []
