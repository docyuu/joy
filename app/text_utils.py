import re
from typing import Any


def normalize_abstract(raw: str | None) -> str:
    if not raw:
        return ""
    clean = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", clean).strip()


def extract_methods(text: str) -> list[str]:
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    patterns = [
        r"\b(method|methodology|approach|framework|pipeline)\b",
        r"\b(we propose|we present|we develop|our model)\b",
        r"\b(experiment|evaluation|dataset|benchmark)\b",
    ]
    selected: list[str] = []
    for sentence in sentences:
        s = sentence.strip()
        if not s:
            continue
        if any(re.search(pattern, s, flags=re.IGNORECASE) for pattern in patterns):
            selected.append(s)
    return selected[:6]


def build_summary(abstract: str, methods: list[str]) -> str:
    if not abstract and not methods:
        return "暂无摘要，建议查看原文获取更多信息。"
    abstract_sentences = [s.strip() for s in re.split(r"(?<=[.!?。；;])\s*", abstract) if s.strip()]
    lead = abstract_sentences[0] if abstract_sentences else "该研究围绕目标关键词开展。"
    method_text = methods[0] if methods else "未自动识别到明确方法句，建议人工复核。"
    return f"研究概览：{lead}\n方法要点：{method_text}"


def sanitize_filename(name: str) -> str:
    sanitized = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip()
    return (sanitized or "untitled")[:120]


def build_llm_prompt(title: str, abstract: str, methods: list[str]) -> str:
    method_lines = "\n".join(f"- {m}" for m in methods) if methods else "- 未提取到方法句"
    return (
        "你是科研助手。请根据给定文献信息，输出中文总结，包含三部分：\n"
        "1) 核心问题与贡献（2-3句）\n"
        "2) 方法与实验要点（要点列表）\n"
        "3) 可学习/可复用的地方（要点列表）\n\n"
        f"标题：{title or '未知'}\n"
        f"摘要：{abstract or '无'}\n"
        f"已提取方法句：\n{method_lines}\n"
    )


def extract_chat_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = [c.get("text", "") for c in content if isinstance(c, dict)]
        return "\n".join(t for t in texts if t).strip()
    return ""
