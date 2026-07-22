"""Pydantic request/response models."""
from __future__ import annotations

from pydantic import BaseModel


class AnalyzeIn(BaseModel):
    user_id: int = 1
    question: str
    frame: str = ""
    answer: str
    framework: str = ""
    action: str = ""
    principle: str = ""


class AnalyzeOut(BaseModel):
    session_id: int
    surface: bool
    critique: list[str]
    scores: dict
    feedback: str
    source: str


class CoachIn(BaseModel):
    user_id: int = 1
    text: str
    mode: str = "socratic"   # "socratic" | "debate" | "orchestrate"


class GrowthOut(BaseModel):
    sessions: int
    latest_scores: dict
    trend: dict          # 축별 첫→최근 변화(%)
    principles: list[dict]
