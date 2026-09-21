"""Structured patent document for the desktop reader."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PatentFigure:
    thumbnail_url: str
    full_url: str


@dataclass(frozen=True, slots=True)
class PatentReaderDocument:
    publication_number: str
    title: str | None = None
    abstract: str | None = None
    claims: str = ""
    description: str = ""
    classifications: tuple[str, ...] = ()
    figures: tuple[PatentFigure, ...] = ()
    claims_source: str | None = None
    description_source: str | None = None
    figures_source: str | None = None
    warnings: tuple[str, ...] = ()
