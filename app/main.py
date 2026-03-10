from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.text_utils import extract_methods, normalize_abstract

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "literature.db"
CROSSREF_ENDPOINT = "https://api.crossref.org/works"

app = FastAPI(title="Literature Workflow", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class CrawlRequest(BaseModel):
    issn: str = Field(..., description="目标期刊ISSN，例如 1476-4687")
    query: str = Field(..., description="领域关键词，例如 'graph neural network'")
    rows: int = Field(10, ge=1, le=50)


class Paper(BaseModel):
    title: str
    doi: str
    journal: str
    published: str
    abstract: str
    methods: list[str]
    url: str


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS papers (
                doi TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                journal TEXT,
                published TEXT,
                abstract TEXT,
                methods TEXT,
                url TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def fetch_crossref(req: CrawlRequest) -> list[dict[str, Any]]:
    params = {
        "filter": f"issn:{req.issn}",
        "query": req.query,
        "rows": req.rows,
        "select": "DOI,title,container-title,published-print,published-online,abstract,URL",
        "sort": "published",
        "order": "desc",
    }
    try:
        response = requests.get(CROSSREF_ENDPOINT, params=params, timeout=20)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Crossref 请求失败: {exc}") from exc

    message = response.json().get("message", {})
    return message.get("items", [])


def parse_published(item: dict[str, Any]) -> str:
    for field in ("published-print", "published-online"):
        date_parts = item.get(field, {}).get("date-parts", [])
        if date_parts and date_parts[0]:
            values = date_parts[0]
            if len(values) == 1:
                return f"{values[0]}"
            if len(values) == 2:
                return f"{values[0]}-{values[1]:02d}"
            return f"{values[0]}-{values[1]:02d}-{values[2]:02d}"
    return ""


def to_paper(item: dict[str, Any]) -> Paper:
    title = (item.get("title") or [""])[0]
    journal = (item.get("container-title") or [""])[0]
    abstract = normalize_abstract(item.get("abstract"))
    return Paper(
        title=title,
        doi=item.get("DOI", ""),
        journal=journal,
        published=parse_published(item),
        abstract=abstract,
        methods=extract_methods(abstract),
        url=item.get("URL", ""),
    )


def save_papers(papers: list[Paper]) -> int:
    now = datetime.utcnow().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        for paper in papers:
            conn.execute(
                """
                INSERT INTO papers (doi, title, journal, published, abstract, methods, url, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(doi) DO UPDATE SET
                    title=excluded.title,
                    journal=excluded.journal,
                    published=excluded.published,
                    abstract=excluded.abstract,
                    methods=excluded.methods,
                    url=excluded.url,
                    created_at=excluded.created_at
                """,
                (
                    paper.doi,
                    paper.title,
                    paper.journal,
                    paper.published,
                    paper.abstract,
                    "\n".join(paper.methods),
                    paper.url,
                    now,
                ),
            )
    return len(papers)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def home() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.post("/api/crawl")
def crawl(req: CrawlRequest) -> dict[str, Any]:
    items = fetch_crossref(req)
    papers = [to_paper(item) for item in items if item.get("DOI")]
    count = save_papers(papers)
    return {"saved": count, "papers": [paper.model_dump() for paper in papers]}


@app.get("/api/papers")
def list_papers(limit: int = 30) -> list[dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT doi, title, journal, published, abstract, methods, url, created_at
            FROM papers ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "doi": row[0],
            "title": row[1],
            "journal": row[2],
            "published": row[3],
            "abstract": row[4],
            "methods": [m for m in (row[5] or "").split("\n") if m],
            "url": row[6],
            "created_at": row[7],
        }
        for row in rows
    ]
