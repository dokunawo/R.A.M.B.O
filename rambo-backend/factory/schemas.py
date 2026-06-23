"""Pydantic schemas for Factory structured outputs."""

from __future__ import annotations
from pydantic import BaseModel, Field


class Source(BaseModel):
    url: str
    title: str
    excerpt: str = Field(default="", max_length=400)


class ToolWishlistEntry(BaseModel):
    name: str
    purpose: str
    external_dependency: str = ""


class SkillsReport(BaseModel):
    domain: str
    competencies: list[str] = Field(min_length=4, max_length=8)
    tools_available: list[str]
    tools_wishlist: list[ToolWishlistEntry]
    design_patterns: list[str] = Field(min_length=2, max_length=5)
    sources: list[Source] = Field(min_length=3, max_length=15)
