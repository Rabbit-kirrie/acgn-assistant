from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str


def _normalize_query(q: str) -> str:
    return " ".join((q or "").strip().split())


def search_serper(*, api_key: str, query: str, limit: int = 5, timeout_seconds: float = 12.0) -> list[WebSearchResult]:
    """Search the web via Serper (https://serper.dev/) Google Search API.

    Returns a list of organic results with title/url/snippet.

    Notes:
    - Uses trust_env=False to avoid Windows proxy env issues.
    - Raises RuntimeError if api_key is missing.
    """

    q = _normalize_query(query)
    if not q:
        return []
    if not str(api_key or "").strip():
        raise RuntimeError("WEB_SEARCH_API_KEY 未配置")

    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {"q": q, "num": max(1, min(int(limit or 5), 10))}

    with httpx.Client(timeout=timeout_seconds, trust_env=False) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json() or {}

    organic = data.get("organic") or []
    out: list[WebSearchResult] = []
    for item in organic:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        link = str(item.get("link") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        if not (title and link):
            continue
        out.append(WebSearchResult(title=title, url=link, snippet=snippet))
        if len(out) >= max(1, min(int(limit or 5), 10)):
            break
    return out


def format_search_context(results: list[WebSearchResult], *, max_chars: int = 1800) -> str:
    """Format search results into a compact context block for LLM prompting."""

    if not results:
        return ""

    lines: list[str] = ["【联网搜索结果（仅供参考）】"]
    for i, r in enumerate(results, start=1):
        snippet = (r.snippet or "").strip()
        lines.append(f"{i}. {r.title}\n{r.url}")
        if snippet:
            lines.append(snippet)
        lines.append("")

    text = "\n".join(lines).strip()
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)] + "…"
