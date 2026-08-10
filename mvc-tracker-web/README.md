# MVC Research Tracker

这是一个零依赖的 Multi-view Clustering 研究追踪 Web 版本。

它包含三部分：

- `index.html`、`assets/`：静态 Web 仪表盘，支持搜索、团队筛选、方向筛选、年份筛选、状态标记和导出。
- `data/`：团队、关键词、论文库和同步状态。
- `scripts/`：每日同步脚本和数据校验脚本。

## 本地预览

直接打开 `index.html` 即可。如果浏览器因为本地文件限制阻止 `fetch` 读取 JSON，可以在本目录启动一个静态服务器：

```bash
python3 -m http.server 8080
```

然后访问：

```text
http://localhost:8080
```

## 手动同步

```bash
python3 scripts/sync_papers.py --limit 6
python3 scripts/validate_data.py
```

同步脚本会读取：

- `data/groups.json`
- `data/keywords.json`

然后查询：

- Semantic Scholar
- OpenAlex
- arXiv

同步结果写回：

- `data/papers.json`
- `data/sync_status.json`

## 每日自动更新

`.github/workflows/daily-sync.yml` 已配置每日任务：

- UTC 21:10 执行，对应北京时间 05:10。
- 拉取最新论文。
- 校验数据。
- 提交 `data/*.json` 变化。
- 发布到 GitHub Pages。

需要在 GitHub 仓库里开启 Pages，并选择 GitHub Actions 作为发布来源。

## 提高准确率

`data/groups.json` 里每个作者预留了：

- `semantic_scholar_id`
- `openalex_id`

建议后续逐个补全这些 ID。只靠作者名和关键词会遇到重名问题，补 ID 后可以把同步脚本改成按作者固定拉取，误报会明显下降。

## 数据字段

每篇论文使用统一结构：

```json
{
  "id": "",
  "title": "",
  "authors": [],
  "year": 2026,
  "venue": "",
  "team": "",
  "topic": [],
  "doi": "",
  "arxiv_id": "",
  "semantic_scholar_id": "",
  "openalex_id": "",
  "pdf_url": "",
  "code_url": "",
  "abstract": "",
  "source": [],
  "first_seen": "2026-08-10",
  "last_checked": "2026-08-10",
  "status": "new",
  "relevance_score": 0
}
```
