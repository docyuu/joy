from __future__ import annotations

import re
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

from app.text_utils import build_summary, extract_methods, normalize_abstract, sanitize_filename

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "literature.db"
CROSSREF_ENDPOINT = "https://api.crossref.org/works"
PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
PUBMED_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
DEFAULT_SOURCES = ["crossref", "pubmed"]

app = FastAPI(title="Literature Workflow", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class CrawlRequest(BaseModel):
    query: str = Field(..., min_length=2, description="领域关键词，例如 'graph neural network'")
    rows: int = Field(10, ge=1, le=50)
    sources: list[str] = Field(default_factory=lambda: DEFAULT_SOURCES.copy())


class ObsidianExportRequest(BaseModel):
    vault_path: str | None = Field(None, description="Obsidian Vault 路径（可选）")
    folder: str = Field("Literature", description="导出文件夹名称")
    limit: int = Field(20, ge=1, le=100)


class Paper(BaseModel):
    source: str
    source_id: str
    title: str
    doi: str
    journal: str
    published: str
    abstract: str
    methods: list[str]
    summary: str
    url: str


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS papers (
                uid TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                source_id TEXT,
                doi TEXT,
                title TEXT NOT NULL,
                journal TEXT,
                published TEXT,
                abstract TEXT,
                methods TEXT,
                summary TEXT,
                url TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def fetch_crossref(query: str, rows: int) -> list[dict[str, Any]]:
    params = {
        "query": query,
        "rows": rows,
        "select": "DOI,title,container-title,published-print,published-online,abstract,URL",
        "sort": "published",
        "order": "desc",
    }
    response = requests.get(CROSSREF_ENDPOINT, params=params, timeout=20)
    response.raise_for_status()
    return response.json().get("message", {}).get("items", [])


def fetch_pubmed(query: str, rows: int) -> list[dict[str, Any]]:
    esearch_params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": rows, "sort": "pub date"}
    esearch = requests.get(PUBMED_ESEARCH, params=esearch_params, timeout=20)
    esearch.raise_for_status()
    ids = esearch.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []

    id_csv = ",".join(ids)
    esummary = requests.get(
        PUBMED_ESUMMARY,
        params={"db": "pubmed", "id": id_csv, "retmode": "json"},
        timeout=20,
    )
    esummary.raise_for_status()
    summary_data = esummary.json().get("result", {})

    efetch = requests.get(
        PUBMED_EFETCH,
        params={"db": "pubmed", "id": id_csv, "retmode": "xml", "rettype": "abstract"},
        timeout=20,
    )
    efetch.raise_for_status()
    xml_text = efetch.text

    abstracts: dict[str, str] = {}
    for pmid in ids:
        pattern = rf"<PMID[^>]*>{pmid}</PMID>[\s\S]*?<Abstract>([\s\S]*?)</Abstract>"
        match = re.search(pattern, xml_text)
        if not match:
            abstracts[pmid] = ""
            continue
        abstract_block = re.sub(r"<[^>]+>", " ", match.group(1))
        abstracts[pmid] = re.sub(r"\s+", " ", abstract_block).strip()

    items: list[dict[str, Any]] = []
    for pmid in ids:
        article = summary_data.get(pmid, {})
        items.append(
            {
                "pmid": pmid,
                "title": article.get("title", ""),
                "journal": article.get("fulljournalname") or article.get("source", ""),
                "published": article.get("pubdate", ""),
                "doi": next((aid.get("value", "") for aid in article.get("articleids", []) if aid.get("idtype") == "doi"), ""),
                "abstract": abstracts.get(pmid, ""),
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            }
        )
    return items


def parse_crossref_date(item: dict[str, Any]) -> str:
    for field in ("published-print", "published-online"):
        date_parts = item.get(field, {}).get("date-parts", [])
        if date_parts and date_parts[0]:
            vals = date_parts[0]
            if len(vals) == 1:
                return str(vals[0])
            if len(vals) == 2:
                return f"{vals[0]}-{vals[1]:02d}"
            return f"{vals[0]}-{vals[1]:02d}-{vals[2]:02d}"
    return ""


def crossref_to_paper(item: dict[str, Any]) -> Paper:
    abstract = normalize_abstract(item.get("abstract"))
    methods = extract_methods(abstract)
    doi = item.get("DOI", "")
    return Paper(
        source="crossref",
        source_id=doi,
        title=(item.get("title") or [""])[0],
        doi=doi,
        journal=(item.get("container-title") or [""])[0],
        published=parse_crossref_date(item),
        abstract=abstract,
        methods=methods,
        summary=build_summary(abstract, methods),
        url=item.get("URL", ""),
    )


def pubmed_to_paper(item: dict[str, Any]) -> Paper:
    abstract = normalize_abstract(item.get("abstract"))
    methods = extract_methods(abstract)
    return Paper(
        source="pubmed",
        source_id=item.get("pmid", ""),
        title=item.get("title", ""),
        doi=item.get("doi", ""),
        journal=item.get("journal", ""),
        published=item.get("published", ""),
        abstract=abstract,
        methods=methods,
        summary=build_summary(abstract, methods),
        url=item.get("url", ""),
    )


def save_papers(papers: list[Paper]) -> int:
    now = datetime.utcnow().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        for paper in papers:
            uid = f"{paper.source}:{paper.source_id or paper.doi or paper.title[:60]}"
            conn.execute(
                """
                INSERT INTO papers (uid, source, source_id, doi, title, journal, published, abstract, methods, summary, url, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(uid) DO UPDATE SET
                    doi=excluded.doi,
                    title=excluded.title,
                    journal=excluded.journal,
                    published=excluded.published,
                    abstract=excluded.abstract,
                    methods=excluded.methods,
                    summary=excluded.summary,
                    url=excluded.url,
                    created_at=excluded.created_at
                """,
                (
                    uid,
                    paper.source,
                    paper.source_id,
                    paper.doi,
                    paper.title,
                    paper.journal,
                    paper.published,
                    paper.abstract,
                    "\n".join(paper.methods),
                    paper.summary,
                    paper.url,
                    now,
                ),
            )
    return len(papers)


def load_recent(limit: int) -> list[dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT source, source_id, doi, title, journal, published, abstract, methods, summary, url, created_at
            FROM papers ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "source": row[0],
            "source_id": row[1],
            "doi": row[2],
            "title": row[3],
            "journal": row[4],
            "published": row[5],
            "abstract": row[6],
            "methods": [m for m in (row[7] or "").split("\n") if m],
            "summary": row[8],
            "url": row[9],
            "created_at": row[10],
        }
        for row in rows
    ]


def export_to_obsidian(papers: list[dict[str, Any]], export_dir: Path) -> list[str]:
    export_dir.mkdir(parents=True, exist_ok=True)
    created_files: list[str] = []
    for paper in papers:
        title = paper.get("title") or (paper.get("doi") or "untitled")
        filename = sanitize_filename(title) + ".md"
        path = export_dir / filename
        methods = "\n".join(f"- {m}" for m in paper.get("methods", [])) or "- 暂无提取"
        content = f"""---
title: "{title}"
source: "{paper.get('source', '')}"
source_id: "{paper.get('source_id', '')}"
doi: "{paper.get('doi', '')}"
journal: "{paper.get('journal', '')}"
published: "{paper.get('published', '')}"
url: "{paper.get('url', '')}"
---

# {title}

## 文献总结
{paper.get('summary', '')}

## 方法要点
{methods}

## 摘要
{paper.get('abstract', '') or '无摘要'}
"""
        path.write_text(content, encoding="utf-8")
        created_files.append(str(path))
    return created_files


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def home() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.post("/api/crawl")
def crawl(req: CrawlRequest) -> dict[str, Any]:
    papers: list[Paper] = []
    errors: list[str] = []
    source_set = {s.lower() for s in req.sources}

    if "crossref" in source_set:
        try:
            papers.extend(crossref_to_paper(item) for item in fetch_crossref(req.query, req.rows) if item.get("title"))
        except requests.RequestException as exc:
            errors.append(f"crossref 抓取失败: {exc}")

    if "pubmed" in source_set:
        try:
            papers.extend(pubmed_to_paper(item) for item in fetch_pubmed(req.query, req.rows) if item.get("title"))
        except requests.RequestException as exc:
            errors.append(f"pubmed 抓取失败: {exc}")

    if not papers and errors:
        raise HTTPException(status_code=502, detail="; ".join(errors))

    saved = save_papers(papers)
    return {"saved": saved, "sources": sorted(source_set), "errors": errors, "papers": [p.model_dump() for p in papers]}


@app.get("/api/papers")
def list_papers(limit: int = 30) -> list[dict[str, Any]]:
    return load_recent(limit)


@app.post("/api/export/obsidian")
def export_obsidian(req: ObsidianExportRequest) -> dict[str, Any]:
    base = Path(req.vault_path).expanduser() if req.vault_path else (BASE_DIR / "obsidian_export")
    export_dir = base / req.folder
    papers = load_recent(req.limit)
    files = export_to_obsidian(papers, export_dir)
    return {"exported": len(files), "directory": str(export_dir), "files": files}
