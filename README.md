# 自动文献收集与内容整理工作流（Web 版）

当前版本支持：

1. **只输入关键词**，从多来源抓取文献（Crossref + PubMed）。
2. 自动抽取摘要中的“方法相关句子”（启发式规则）。
3. 自动生成简要文献总结（研究概览 + 方法要点）。
4. 存入本地 SQLite 并在网页端展示。
5. 一键导出为 **Obsidian 可直接读取的 Markdown**。

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
for windows
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload

打开 `http://127.0.0.1:8000`。

## API

- `POST /api/crawl`
  - body:
    - `query`: 关键词（必填）
    - `rows`: 每个来源抓取条数（1~50）
    - `sources`: 来源列表，如 `['crossref', 'pubmed']`
- `GET /api/papers?limit=30`
  - 查询本地数据库中最近抓取的文献。
- `POST /api/export/obsidian`
  - body:
    - `vault_path`: Obsidian Vault 路径（可选）
    - `folder`: 导出目录名（默认 `Literature`）
    - `limit`: 导出篇数（1~100）

## Obsidian 导出说明

- 若提供 `vault_path`，文件会直接写入 `<vault_path>/<folder>`。
- 若不提供，则默认导出到项目目录下 `obsidian_export/<folder>`。
- 每篇文献一个 Markdown，包含 frontmatter（source/doi/url 等）+ 总结 + 方法要点 + 摘要。

## 后续可扩展

- 增加 arXiv/Semantic Scholar 等来源。
- 引入 LLM 做更高质量结构化抽取（方法、实验设置、结论、局限）。
- 增加定时任务、去重策略、标签管理和引用格式导出（BibTeX）。
