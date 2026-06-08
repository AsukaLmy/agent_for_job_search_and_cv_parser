# AutoCV

> 「求职这种事，交给程序来做就好了。」

一个面向 **国内招聘平台** 与 **海外 PhD 申请** 的半自动化简历投递工具。
解析你的简历，抓取目标职位，让 AI 完成匹配评分，最后由你亲手按下确认键。

---

## 功能概览

| 阶段 | 描述 |
|------|------|
| `parse` | 从 PDF 简历中提取结构化信息（姓名、技能、教育、经历） |
| `scrape` | 抓取招聘平台职位列表，写入本地 SQLite 数据库 |
| `match` | 调用 DeepSeek API 对每条职位进行 0–100 评分 |
| `submit` | 打开浏览器预填表单，人工审核后确认投递 |

支持平台：**MCPJobs 聚合**（内含 Boss直聘、智联招聘等主流国内平台）

> PhD 申请平台（FindAPhD、PhDPortals 等）已集成但暂未激活，当前聚合网站收录信息较少；如有需要可在 `config.yaml` 中将对应平台的 `enabled` 改为 `true`。

---

## 环境要求

- Python 3.11+
- Node.js 18+（用于 mcp-jobs 爬虫服务）
- [DeepSeek API Key](https://platform.deepseek.com)

---

## 安装

```bash
# 1. 克隆仓库
git clone https://github.com/your-username/autocv.git
cd autocv

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 安装 Playwright 浏览器
python -m playwright install chromium

# 4. 安装 Node.js 依赖（mcp-jobs 爬虫）
npm install

# 5. 应用 mcp-jobs 补丁（见下方说明）
```

### mcp-jobs 补丁说明

`node_modules/` 未提交到仓库。安装后需手动修改以下文件，以修复反爬检测和 JSON-RPC 协议污染问题：

**`node_modules/mcp-jobs/dist/crawler/webCrawler.js`**
- `extractData(page)` 改为 `extractData(page, rules)`，移除内部 URL 匹配查找
- `handleUrl` 中调用改为 `await this.extractData(page, config.rules)`
- 在 `page = await this.context.newPage()` 后添加：
  ```js
  await page.addInitScript("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})");
  ```

**`node_modules/mcp-jobs/dist/services/crawlerConfigService.js`**
- launch args 添加 `'--disable-blink-features=AutomationControlled'`
- 用户代理更新为 Chrome 131 Windows：`Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36`

**`node_modules/mcp-jobs/dist/index.js`** 和 **`dist/services/storageService.js`**
- 所有 `console.log` 改为 `console.error`（stdout 是 MCP JSON-RPC 通道，不可污染）

---

## 配置

```bash
# 复制环境变量模板并填入你的 API Key
copy .env.example .env
```

编辑 `.env`：
```
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```

将你的 PDF 简历放入 `resume/` 目录（支持多文件，自动合并）。

其余参数在 `config.yaml` 中调整：关键词、目标城市、评分阈值、动机信字数限制等。

---

## 使用方法

```bash
# 解析简历
python main.py parse

# 抓取职位（使用 config.yaml 中启用的所有平台）
python main.py scrape

# 只抓取指定平台（当前推荐仅用 mcpjobs）
python main.py scrape --platform mcpjobs

# AI 匹配评分（默认处理 50 条，展示 Top 30）
python main.py match
python main.py match --limit 100 --top 50

# 查看数据库状态
python main.py status

# 半自动投递（分数 ≥ 70）
python main.py submit
python main.py submit --min-score 80 --dry-run   # 测试模式，不写入数据库

# 一键全流程
python main.py run
```

---

## 工作目录结构

```
autocv/
├── resume/          # 放置 PDF 简历（已被 .gitignore 排除）
├── data/
│   └── jobs.db      # SQLite 职位数据库（已被 .gitignore 排除）
├── src/
│   ├── parser.py    # 简历解析
│   ├── matcher.py   # AI 匹配评分
│   ├── submitter.py # 半自动投递
│   ├── db.py        # 数据库操作
│   └── scrapers/    # 各平台爬虫
├── main.py          # CLI 入口
├── config.yaml      # 配置文件
└── .env             # API Key（本地专用，不提交）
```

---

