"""
AutoCV CLI

Usage:
  python main.py parse                            # Parse PDF resume → data/resume.json
  python main.py scrape [--platform boss,findaphd]  # Scrape job listings
  python main.py match  [--limit 50]             # AI match + score
  python main.py submit [--min-score 70]         # Semi-auto browser submission
  python main.py status                          # Show DB statistics
  python main.py run                             # Full pipeline (parse→scrape→match→submit)
"""
import argparse
import json
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich import print as rprint

# Load .env before anything else so DEEPSEEK_API_KEY is available
load_dotenv(Path(__file__).parent / ".env")

console = Console()

# ── Config loading ────────────────────────────────────────────────────────────

def load_config() -> dict:
    cfg_path = Path(__file__).parent / "config.yaml"
    if not cfg_path.exists():
        console.print("[red]config.yaml not found.[/red]")
        sys.exit(1)
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_parse(cfg: dict, force: bool = False) -> None:
    from src.parser import parse_resume
    resume_dir = Path(cfg["resume"]["path"])
    api_key    = cfg["ai"].get("api_key", "")
    model      = cfg["ai"].get("model", "deepseek-v4-flash")
    console.print(f"[cyan]解析简历...[/cyan] 目录: {resume_dir}")
    data = parse_resume(resume_dir, api_key=api_key, model=model, force=force)
    console.print(f"[green]✓ 解析完成[/green]  姓名: {data.get('name')}  邮箱: {data.get('email')}")
    console.print(f"  技能: {', '.join(data.get('skills', [])[:8])}")


def cmd_scrape(cfg: dict, platforms: list[str] | None = None) -> None:
    from src.db import init_db, stats as db_stats

    init_db()
    delay   = cfg["scraping"].get("delay_seconds", 2)
    plat_cfg = cfg["scraping"]["platforms"]
    targets = platforms or [k for k, v in plat_cfg.items() if v.get("enabled")]

    total_added = 0

    for platform in targets:
        p_cfg = plat_cfg.get(platform, {})
        keywords = p_cfg.get("keywords", [])
        if not keywords:
            console.print(f"[yellow]跳过 {platform}：未配置关键词[/yellow]")
            continue

        console.print(f"\n[cyan]抓取 {platform}...[/cyan]  关键词: {keywords}")

        if platform == "mcpjobs":
            from src.scrapers.mcpjobs_scraper import MCPJobsScraper
            scraper = MCPJobsScraper(delay=delay)
            added   = scraper.scrape(
                keywords,
                city=p_cfg.get("city", ""),
                max_pages=p_cfg.get("max_pages", 3),
            )
        elif platform == "jobspy":
            from src.scrapers.jobspy_scraper import JobSpyScraper
            scraper = JobSpyScraper(delay=delay)
            added   = scraper.scrape(
                keywords,
                location=p_cfg.get("location", ""),
                max_results=p_cfg.get("max_results", 30),
                sites=p_cfg.get("sites"),
            )
        elif platform == "phdseeker":
            from src.scrapers.phdseeker_scraper import PhDSeekerScraper
            scraper = PhDSeekerScraper(delay=delay)
            added   = scraper.scrape(
                keywords,
                country=p_cfg.get("country", ""),
                max_pages=p_cfg.get("max_pages", 3),
            )
        elif platform == "boss":
            from src.scrapers.boss import BossScraper
            scraper = BossScraper(delay=delay)
            added   = scraper.scrape(keywords, city=p_cfg.get("city", "全国"))
        elif platform == "zhilian":
            from src.scrapers.zhilian import ZhilianScraper
            scraper = ZhilianScraper(delay=delay)
            added   = scraper.scrape(keywords, city=p_cfg.get("city", ""))
        elif platform == "findaphd":
            from src.scrapers.findaphd import FindAPhDScraper
            scraper = FindAPhDScraper(delay=delay)
            added   = scraper.scrape(keywords, country=p_cfg.get("country", ""))
        elif platform == "phdportals":
            from src.scrapers.phdportals import PhDPortalsScraper
            scraper = PhDPortalsScraper(delay=delay)
            added   = scraper.scrape(keywords, country=p_cfg.get("country", ""))
        else:
            console.print(f"[yellow]未知平台: {platform}[/yellow]")
            continue

        console.print(f"[green]✓ {platform}[/green]  新增职位: {added}")
        total_added += added

    s = db_stats()
    console.print(f"\n数据库总计: {s['total']} 条职位  (已评分: {s['scored']})")


def _show_top_table(top_n: int, min_score: int) -> None:
    from src.db import get_top_jobs
    import json as _json

    rows = get_top_jobs(n=top_n, min_score=min_score)
    if not rows:
        console.print(f"[yellow]数据库中暂无分数 ≥ {min_score} 的职位[/yellow]")
        return

    table = Table(title=f"Top {top_n} 职位 (分数 ≥ {min_score}，含历史评分)", show_lines=True)
    table.add_column("分数", style="bold", width=6)
    table.add_column("平台", width=10)
    table.add_column("职位", width=28)
    table.add_column("公司/机构", width=22)
    table.add_column("AI 评价", width=40)
    table.add_column("链接", width=50)

    for row in rows:
        score = row["match_score"]
        color = "green" if score >= 80 else "yellow" if score >= 60 else "red"
        summary = ""
        if row["match_data"]:
            try:
                summary = _json.loads(row["match_data"]).get("summary", "")
            except Exception:
                pass
        table.add_row(
            f"[{color}]{score}[/{color}]",
            row["platform"] or "",
            (row["title"] or "")[:28],
            (row["company"] or "")[:22],
            summary,
            row["url"] or "",
        )

    console.print(table)


def cmd_match(cfg: dict, limit: int = 50, top_n: int = 30) -> None:
    from src.matcher import match_jobs
    from src.db import init_db, get_unscored

    init_db()
    api_key   = cfg["ai"].get("api_key", "")
    model     = cfg["ai"].get("model", "deepseek-v4-flash")
    threshold = cfg["matching"].get("min_score", 60)
    api_delay = cfg["matching"].get("api_delay_seconds", 1)

    pending = get_unscored(limit=limit)
    n = len(pending)
    if n == 0:
        console.print("[yellow]没有待评分的职位（所有职位已评分）。[/yellow]")
    else:
        est_seconds = n * (api_delay + 3)
        console.print(
            f"\n[bold]即将调用 DeepSeek API[/bold]  共 [cyan]{n}[/cyan] 条职位 · "
            f"间隔 {api_delay}s · 预计约 {est_seconds:.0f}s"
        )
        ans = input("确认开始？[Enter=继续 / q=取消]: ").strip().lower()
        if ans == "q":
            console.print("[yellow]已取消。[/yellow]")
            return

        console.print(f"[cyan]AI 匹配评分...[/cyan]")
        match_jobs(api_key=api_key, model=model, limit=limit, min_score=0, api_delay=api_delay)

    console.print(f"\n[bold cyan]── Top {top_n} 推荐职位 ──[/bold cyan]")
    _show_top_table(top_n=top_n, min_score=threshold)


def cmd_submit(cfg: dict, min_score: int | None = None, dry_run: bool = False) -> None:
    from src.submitter import submit_jobs

    api_key   = cfg["ai"].get("api_key", "")
    model     = cfg["ai"].get("model", "deepseek-v4-flash")
    threshold = min_score if min_score is not None else cfg["submission"].get("min_score", 70)
    max_words = cfg["submission"]["motivation_letter"].get("max_words", 400)

    if dry_run:
        console.print("[yellow][测试模式] 不会写入数据库，不会标记投递状态[/yellow]")

    submit_jobs(
        min_score=threshold,
        api_key=api_key,
        model=model,
        max_words=max_words,
        dry_run=dry_run,
    )


def cmd_status(cfg: dict) -> None:
    from src.db import init_db, stats as db_stats, get_conn

    init_db()
    s = db_stats()
    console.print(f"\n[bold]数据库状态[/bold]  路径: data/jobs.db")
    console.print(f"  总职位: {s['total']}  已评分: {s['scored']}")
    console.print("  各平台:")
    for plat, n in s["by_platform"].items():
        console.print(f"    {plat:12s}  {n}")

    with get_conn() as conn:
        statuses = conn.execute(
            "SELECT status, COUNT(*) as n FROM jobs GROUP BY status"
        ).fetchall()
    console.print("  各状态:")
    for row in statuses:
        console.print(f"    {row['status']:12s}  {row['n']}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AutoCV — 自动简历投递工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    # parse
    p_parse = sub.add_parser("parse", help="解析 PDF 简历")
    p_parse.add_argument("--force", action="store_true", help="强制重新解析（忽略缓存）")

    # scrape
    p_scrape = sub.add_parser("scrape", help="抓取招聘信息")
    p_scrape.add_argument(
        "--platform", default="",
        help="逗号分隔的平台列表，如 boss,findaphd（默认：config.yaml 中启用的所有平台）"
    )

    # match
    p_match = sub.add_parser("match", help="AI 匹配评分")
    p_match.add_argument("--limit", type=int, default=50, help="一次处理的最大职位数")
    p_match.add_argument("--top", type=int, default=30, help="评分结束后展示 Top N 职位（默认 30）")

    # submit
    p_submit = sub.add_parser("submit", help="半自动投递")
    p_submit.add_argument("--min-score", type=int, default=None, help="最低分数阈值")
    p_submit.add_argument("--dry-run", action="store_true", help="测试模式：不写入数据库")

    # status
    sub.add_parser("status", help="查看数据库统计")

    # run (full pipeline)
    p_run = sub.add_parser("run", help="全流程一键执行")
    p_run.add_argument("--platform", default="")
    p_run.add_argument("--min-score", type=int, default=None)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    cfg = load_config()

    if args.command == "parse":
        cmd_parse(cfg, force=args.force)
    elif args.command == "scrape":
        platforms = [p.strip() for p in args.platform.split(",")] if args.platform else None
        cmd_scrape(cfg, platforms=platforms)
    elif args.command == "match":
        cmd_match(cfg, limit=args.limit, top_n=args.top)
    elif args.command == "submit":
        cmd_submit(cfg, min_score=args.min_score, dry_run=args.dry_run)
    elif args.command == "status":
        cmd_status(cfg)
    elif args.command == "run":
        console.rule("[bold cyan]AutoCV 全流程启动[/bold cyan]")
        cmd_parse(cfg)
        platforms = [p.strip() for p in args.platform.split(",")] if args.platform else None
        cmd_scrape(cfg, platforms=platforms)
        cmd_match(cfg)
        cmd_submit(cfg, min_score=args.min_score)


if __name__ == "__main__":
    main()
