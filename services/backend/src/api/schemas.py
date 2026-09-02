"""Pydantic request bodies for the jobs API."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class JournalBody(BaseModel):
    heading: Optional[str] = None
    paragraphs: List[str] = Field(default_factory=list)


class PreviewEditBody(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    journal: Optional[JournalBody] = None
    captions: Dict[str, str] = Field(default_factory=dict)


class PublishBody(BaseModel):
    access_token: str


class RestartBody(BaseModel):
    access_token: Optional[str] = None
    mode: Literal["all", "remaining"] = "all"


class ReprocessBody(BaseModel):
    mode: Literal["overwrite", "new"] = "overwrite"
    title_prefix: Optional[str] = None


class ScrapeBody(BaseModel):
    url: str
    headers: Dict[str, str] = Field(default_factory=dict)
    auto_publish: bool = False
    access_token: Optional[str] = None


class OrchestratorSettingsBody(BaseModel):
    max_concurrent_jobs: int
