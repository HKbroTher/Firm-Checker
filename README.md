# Firm Checker：企业信息检索 RAG 助手

技术栈：Python、FastAPI、Claude API（LLM）、ChromaDB

- **检索增强生成流程**：抓取企业官网、新闻稿等公开资料（也可以直接提交文本），抽取正文后切分，写入 ChromaDB 向量库。
- **结构化企业画像**：按“概况 / 业务线 / 产品类别 / 目标市场”分维度检索，把片段编号后交给 Claude，用 JSON Schema 结构化输出生成画像。每一项都附上来源引用（URL、标题、原文片段）。

## 架构

```
             ┌────────────┐   ┌───────────┐   ┌──────────────┐
 URLs ──────▶│ fetcher.py │──▶│chunking.py│──▶│vectorstore.py│ (ChromaDB, 按 company 隔离)
 文本资料 ───┘ 抓取+正文抽取  │ 段落/句子切分 │   └──────┬───────┘
                              │ 重叠窗口     │          │ 分维度多查询召回
                              └───────────┘          ▼
                                             ┌──────────────┐   ┌────────┐
                                             │ profiler.py  │──▶│ llm.py │ Claude 结构化输出
                                             │ S1..Sn 编号  │◀──│        │
                                             │ 引用校验     │   └────────┘
                                             └──────┬───────┘
                                                    ▼
                                         CompanyProfile（每项带 citations）
```

| 模块 | 说明 |
|---|---|
| `app/fetcher.py` | httpx 抓取页面，BeautifulSoup 去掉导航、脚本等噪声后抽取正文；可选同域爬取，优先跟进“关于 / 产品 / 新闻”类链接 |
| `app/chunking.py` | 按段落 → 句子（支持中英文标点）→ 硬切分，再贪心打包成 `CHUNK_SIZE` 大小的块，块之间保留 `CHUNK_OVERLAP` 重叠 |
| `app/vectorstore.py` | ChromaDB 持久化（cosine），默认用 BAAI/bge-m3 多语言向量模型（1024 维，中英文都适用）。元数据保存 company/url/title/类型，检索时按企业过滤。同一 URL 重新入库前会先删除旧切片 |
| `app/profiler.py` | 每个维度用中英文多条查询召回，轮流合并去重后编号为 `S1..Sn` 交给 LLM。返回后校验引用：不存在的编号被丢弃，没有有效引用的条目会从画像中移除，处理情况记录在 `warnings` 里 |
| `app/llm.py` | Claude Messages API，使用 `output_config.format`（JSON Schema）保证输出可解析，开启自适应思考；启用服务端拒答回退 `fallbacks: "default"`，并处理 refusal / max_tokens |
| `app/main.py` | FastAPI 接口 |

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env        # 填入 ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

首次启动会从 Hugging Face 下载 bge-m3（约 2.3GB），并在启动阶段加载到内存（CPU 上约需 3GB 内存）。国内网络可以设置 `HF_ENDPOINT=https://hf-mirror.com`；有 GPU 时设置 `EMBEDDING_DEVICE=cuda`。

打开 http://localhost:8000/docs 查看交互式接口文档。

### 1. 入库

```bash
curl -X POST localhost:8000/ingest -H 'content-type: application/json' -d '{
  "company": "示例科技",
  "urls": ["https://www.example.com/"],
  "crawl": true,
  "documents": [
    {"url": "https://news.example.com/2026/01", "title": "示例科技发布新品",
     "source_type": "press_release", "text": "……新闻稿全文……", "published_at": "2026-01-15"}
  ]
}'
# => {"company":"示例科技","documents":6,"chunks":42,"failures":[]}
```

### 2. 检索（调试用）

```bash
curl -X POST localhost:8000/search -H 'content-type: application/json' \
  -d '{"company": "示例科技", "query": "主要产品", "top_k": 5}'
```

### 3. 生成企业画像

```bash
curl -X POST localhost:8000/profile -H 'content-type: application/json' \
  -d '{"company": "示例科技", "language": "zh"}'
```

返回示例（节选）：

```json
{
  "company": "示例科技",
  "summary": "示例科技是一家总部位于深圳的工业机器人企业……",
  "summary_citations": [{"source_id": "S1", "url": "https://www.example.com/", "title": "关于我们", "snippet": "……"}],
  "business_lines": [
    {"name": "智能制造", "description": "提供产线自动化整体方案。",
     "citations": [{"source_id": "S3", "url": "https://www.example.com/business", "title": "业务板块", "snippet": "……"}]}
  ],
  "product_categories": [...],
  "target_markets": [...],
  "generated_at": "2026-10-24T08:00:00Z",
  "model": "claude-opus-5-5",
  "warnings": []
}
```

### 其他接口

- `GET /companies`：已入库的企业及切片数
- `DELETE /companies/{company}`：删除某企业的全部资料
- `GET /health`

## 配置

见 `.env.example`。常用项：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLM_MODEL` | `claude-opus-5-5` | Claude 模型 |
| `LLM_EFFORT` | `medium` | 思考深度：`low` / `medium` / `high` / `xhigh` / `max` |
| `EMBEDDING_BACKEND` | `bge-m3` | `bge-m3`：多语言模型，中文检索效果好；`default`：Chroma 内置的 all-MiniLM-L6-v2（约 80MB，英文为主）；`hash`：离线哈希向量，只适合测试 |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | bge-m3 后端使用的模型名，也可以填本地模型目录 |
| `EMBEDDING_DEVICE` | `cpu` | `cpu` / `cuda` / `mps` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 800 / 150 | 切分长度（字符数） |
| `RETRIEVAL_TOP_K` / `MAX_CONTEXT_CHUNKS` | 6 / 24 | 每条查询的召回数 / 送入 LLM 的片段上限 |
| `MAX_CRAWL_PAGES` | 10 | 单次入库最多抓取的页面数 |

> 每种向量后端使用独立的 Chroma 集合（如 `company_docs_bge-m3`），因为不同模型的向量维度不同。切换后端后需要重新调用 `/ingest` 入库，旧集合的数据不会被读取，也不会被删除。

## 测试

```bash
pytest -q
```

测试完全离线运行：HTTP 用 MockTransport 模拟，向量化使用哈希向量（bge-m3 的接入用假模型替代 sentence-transformers 来验证），Chroma 使用内存实例，LLM 用假实现替代。另外有一组测试通过模拟传输层，校验发给 Claude API 的请求结构。
