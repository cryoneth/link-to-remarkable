"""link2rm CLI — send a URL to your reMarkable as a clean ePub or PDF."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

import click

from link2rm import config


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("url", required=False)
@click.option("--llm", is_flag=True, default=False, help="Enable LLM cleanup (requires ANTHROPIC_API_KEY)")
@click.option("--folder", default=None, metavar="PATH", help="reMarkable folder (overrides REMARKABLE_FOLDER env)")
@click.option(
    "--format", "fmt",
    type=click.Choice(["epub", "pdf"], case_sensitive=False),
    default=None,
    help=f"Output format (default: {config.REMARKABLE_FORMAT}). arXiv always uses pdf.",
)
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None, metavar="FILE", help="Save file locally, skip upload")
@click.option("--register", "do_register", is_flag=True, default=False, help="Register this device with reMarkable and exit")
@click.option("--server", "do_server", is_flag=True, default=False, help="Start the FastAPI ingest server")
@click.option("--host", default=config.HOST, show_default=True, help="Server bind host")
@click.option("--port", default=config.PORT, show_default=True, type=int, help="Server bind port")
def main(
    url: Optional[str],
    llm: bool,
    folder: Optional[str],
    fmt: Optional[str],
    output: Optional[Path],
    do_register: bool,
    do_server: bool,
    host: str,
    port: int,
) -> None:
    """Send a URL to your reMarkable tablet as a clean ePub (default) or PDF.

    Examples:

    \b
      link2rm https://example.com/article
      link2rm https://arxiv.org/abs/1706.03762
      link2rm --format pdf https://example.com/post
      link2rm --llm https://some-blog.com/post
      link2rm -o article.epub https://example.com/post   # local only
      link2rm --server                                    # start HTTP server
    """
    if do_register:
        _cmd_register()
        return

    if do_server:
        _cmd_server(host, port)
        return

    if not url:
        click.echo(main.get_help(click.Context(main)))
        sys.exit(1)

    asyncio.run(_cmd_ingest(url, llm=llm, folder=folder, fmt=fmt, output=output))


def _cmd_register() -> None:
    from link2rm import remarkable
    remarkable.ensure_authenticated()


def _cmd_server(host: str, port: int) -> None:
    import uvicorn
    from link2rm.server import app
    click.echo(f"Starting link2rm server on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


async def _cmd_ingest(
    url: str,
    llm: bool,
    folder: Optional[str],
    fmt: Optional[str],
    output: Optional[Path],
) -> None:
    from link2rm.pipeline import run

    use_llm = llm or config.LLM_CLEANUP
    if use_llm and not config.ANTHROPIC_API_KEY:
        click.echo("Error: --llm requires ANTHROPIC_API_KEY to be set.", err=True)
        sys.exit(1)

    click.echo(f"→ {url}")
    try:
        result = await run(url, use_llm=use_llm, folder=folder, fmt=fmt, local_output=output)
    except Exception as e:
        click.echo(f"✗ Failed: {e}", err=True)
        sys.exit(1)

    _print_result(result, output)


def _print_result(result, output: Optional[Path]) -> None:
    from link2rm.pipeline import PipelineResult
    r: PipelineResult = result

    fmt_tag = r.output_format.upper()
    llm_note = f"  llm_tokens={r.llm_tokens}" if r.llm_tokens else ""
    size_kb = r.file_bytes // 1024

    if output:
        click.echo(
            f"✓ Saved  [{r.strategy}] [{fmt_tag}]  {size_kb} KB  "
            f"({r.extraction_ms} ms){llm_note}\n"
            f"  File: {output}"
        )
    else:
        click.echo(
            f"✓ Uploaded  [{r.strategy}] [{fmt_tag}]  {size_kb} KB  "
            f"({r.extraction_ms} ms){llm_note}\n"
            f'  "{r.doc_name}" → reMarkable'
        )
