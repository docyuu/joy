# 自动文献收集与内容整理工作流（Web 版）

这个项目提供一个最小可用（MVP）工作流：

1. 按期刊 ISSN + 领域关键词抓取论文（Crossref）。
2. 自动抽取摘要中的“方法相关句子”（启发式规则）。
3. 将结果存入本地 SQLite。
4. 在网页端浏览论文与方法解析结果。

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

打开 `http://127.0.0.1:8000`。

## API

- `POST /api/crawl`
  - body:
    - `issn`: 目标期刊 ISSN
    - `query`: 关键词
    - `rows`: 抓取条数（1~50）
- `GET /api/papers?limit=30`
  - 查询本地数据库中最近抓取的文献。

## 后续可扩展

- 增加调度（定时抓取）与多数据源（PubMed, arXiv, Semantic Scholar）。
- 引入 LLM 进行更准确的方法/实验设置/结论结构化抽取。
- 增加多用户、项目分组、导出 Markdown/CSV。
