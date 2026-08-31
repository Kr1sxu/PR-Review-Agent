"""
CLI 入口 - PR-Review Agent v2
命令行接口，转发参数到 WebTaskManager 执行审查任务。
启动时自动初始化 PostgreSQL 数据库连接。
"""

import argparse
import asyncio
import sys

from dotenv import load_dotenv
load_dotenv()


async def run_cli(args):
    """根据 CLI 参数执行审查任务"""
    from src.core.database import init_db, close_db
    from src.scheduler.task_manager import WebTaskManager
    from src.core.logger import get_logger

    logger = get_logger("cli")

    # 初始化 PostgreSQL 连接池
    try:
        await init_db()
        logger.info("cli", "PostgreSQL 连接成功")
    except Exception as e:
        logger.warning("cli", f"PostgreSQL 连接失败，降级为无持久化模式: {e}")

    manager = WebTaskManager()

    # 创建任务
    task = manager.create_task(
        mode=args.mode,
        repo_path=args.repo,
        base_commit=args.base,
        target_commit=args.target,
        pr_description=args.pr or "",
        rag_enabled=args.rag,
        max_rounds=args.max_rounds,
    )
    logger.info("cli", f"任务已创建：{task.task_id} (模式={args.mode})")
    print(f"任务已创建：{task.task_id}")
    print(f"模式：{args.mode} | 仓库：{args.repo}")
    print(f"提交范围：{args.base} -> {args.target}")
    print("开始审查...\n")

    # 启动任务
    await manager.start_task(task.task_id)

    # 轮询等待完成
    while True:
        info = manager.get_task(task.task_id)
        if info is None:
            break
        if info.status.value in ("completed", "failed"):
            break
        await asyncio.sleep(1)

    # 输出结果
    info = manager.get_task(task.task_id)
    if info.status.value == "completed":
        print(f"\n=== 审查完成 ===")
        print(f"发现数量：{info.findings_count}")
        print(f"耗时：{info.duration_seconds:.1f}秒")
        print(f"输出目录：{info.output_dir}")
        print(f"  - findings.json       # 结构化缺陷数据")
        print(f"  - evidence_store.json # 共享证据仓库")
        print(f"  - report.md           # Markdown 审查报告")
        print(f"  - judge.json / judge.md  # AI 评审评分")
    else:
        print(f"\n=== 审查失败 ===")
        print(f"错误：{info.error_message}")
        await close_db()
        sys.exit(1)

    await close_db()


def main():
    parser = argparse.ArgumentParser(
        description="PR-Review Agent v2 - 多智能体 PR 代码审查系统",
        prog="pr-review",
    )
    parser.add_argument("--repo", required=True, help="Git 仓库路径")
    parser.add_argument("--base", default="HEAD~1", help="基准提交（默认：HEAD~1）")
    parser.add_argument("--target", default="HEAD", help="目标提交（默认：HEAD）")
    parser.add_argument("--pr", default="", help="PR 描述文本")
    parser.add_argument("--mode", default="debate",
                        choices=["simple", "council", "debate", "agentic"],
                        help="审查模式（默认：debate）")
    parser.add_argument("--rag", action="store_true", default=True,
                        help="启用 RAG 知识库（默认：开启）")
    parser.add_argument("--no-rag", dest="rag", action="store_false",
                        help="禁用 RAG 知识库")
    parser.add_argument("--max-rounds", type=int, default=3,
                        help="最大辩论轮次（默认：3）")
    args = parser.parse_args()
    asyncio.run(run_cli(args))


if __name__ == "__main__":
    main()
