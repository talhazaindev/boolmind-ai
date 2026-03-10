"""Rich logging for voice pipeline: panels, tables, and per-event timings."""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("app.voice.rich")

# Optional Rich imports (only used when handler is active)
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
    _RICH_AVAILABLE = True
    _console = Console()
except ImportError:
    _RICH_AVAILABLE = False
    _console = None
    Console = None
    Panel = None
    Table = None


class RichVoiceHandler(logging.Handler):
    """Logging handler that prints Rich renderables (Panel/Table) when record has voice_renderable."""

    def emit(self, record: logging.LogRecord) -> None:
        renderable = getattr(record, "voice_renderable", None)
        if renderable is not None and _console is not None:
            try:
                _console.print(renderable)
            except Exception:
                self.handleError(record)
        else:
            msg = self.format(record)
            if msg and _console is not None:
                try:
                    _console.print(f"[dim]{msg}[/]")
                except Exception:
                    self.handleError(record)


def setup_rich_voice_logging(level: int = logging.DEBUG) -> None:
    """Add Rich handler to voice logger so panels/tables are printed. Call from main when VOICE_RICH_LOGS=1."""
    if not _RICH_AVAILABLE:
        return
    log = logging.getLogger("app.voice.rich")
    for h in list(log.handlers):
        if isinstance(h, RichVoiceHandler):
            return
    h = RichVoiceHandler()
    h.setLevel(level)
    log.addHandler(h)
    log.setLevel(level)


@dataclass
class VoiceTurnTimings:
    """Collect timings for one voice turn (STT → LLM → TTS) for a summary panel."""
    conn_id: str = ""
    t_start: float = 0.0
    events: list[tuple[str, str, float]] = field(default_factory=list)  # (phase, detail, offset_sec)

    def _elapsed(self) -> float:
        return time.monotonic() - self.t_start if self.t_start else 0.0

    def add(self, phase: str, detail: str) -> None:
        self.events.append((phase, detail, self._elapsed()))

    def emit_panel(self) -> None:
        if not _RICH_AVAILABLE:
            return
        table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
        table.add_column("Phase", style="green")
        table.add_column("Detail", style="white")
        table.add_column("Δt (s)", justify="right", style="yellow")
        for phase, detail, t in self.events:
            table.add_row(phase, detail, f"{t:.3f}")
        total = self._elapsed()
        table.add_row("[bold]Total[/]", f"{len(self.events)} events", f"[bold]{total:.3f}[/]")
        panel = Panel(
            table,
            title=f"[bold]Voice turn[/] [dim]conn={self.conn_id}[/]",
            border_style="blue",
            padding=(0, 1),
        )
        _log_renderable(panel)


def _log_renderable(renderable: Any) -> None:
    """Emit a Rich renderable via the voice logger (only shown when Rich handler is attached)."""
    logger.info("", extra={"voice_renderable": renderable})


def _maybe_panel(title: str, content: str, border_style: str = "blue") -> None:
    if not _RICH_AVAILABLE:
        return
    _log_renderable(Panel(content, title=f"[bold]{title}[/]", border_style=border_style, padding=(0, 1)))


def log_audio_chunk(conn_id: str, index: int, n_bytes: int, elapsed: float, emit_rich: bool = False) -> None:
    """Log one incoming client audio chunk. Set emit_rich=True to print a Rich table (e.g. every 10th chunk)."""
    extra = {}
    if _RICH_AVAILABLE and emit_rich:
        extra["voice_renderable"] = _table_one("Audio in", f"chunk #{index}", f"{n_bytes} B", f"{elapsed:.3f}s")
    logger.debug(
        "[voice] audio_chunk conn=%s #%d len=%d Δt=%.3fs",
        conn_id, index, n_bytes, elapsed,
        extra=extra or None,
    )


def _table_one(phase: str, col1: str, col2: str, col3: str) -> Optional[Any]:
    if not _RICH_AVAILABLE:
        return None
    t = Table(show_header=False, box=box.SIMPLE)
    t.add_column(style="cyan")
    t.add_column(style="white")
    t.add_row(phase, f"{col1} | {col2} | {col3}")
    return t


def log_audio_summary(conn_id: str, total_frames: int, total_bytes: int, elapsed: float) -> None:
    """Log summary of client audio received (e.g. on end_utterance)."""
    _maybe_panel(
        "STT audio received",
        f"conn=[cyan]{conn_id}[/]\nframes=[green]{total_frames}[/]  bytes=[green]{total_bytes}[/]\nΔt=[yellow]{elapsed:.3f}s[/]",
        "green",
    )


def log_llm_input(conn_id: str, session_id: str, message_len: int, elapsed: float) -> None:
    """Log when LLM receives the user message."""
    _maybe_panel(
        "LLM input",
        f"conn=[cyan]{conn_id}[/]  session=[dim]{session_id[:8]}…[/]\nmessage_len=[green]{message_len}[/]  Δt=[yellow]{elapsed:.3f}s[/]",
        "magenta",
    )


def log_llm_chunk(conn_id: str, chunk_index: int, chunk_len: int, elapsed: float, preview: str = "", emit_rich: bool = False) -> None:
    """Log one LLM token chunk. Set emit_rich=True to print a Rich panel (e.g. first and every 10th)."""
    extra = {}
    if _RICH_AVAILABLE and emit_rich:
        extra["voice_renderable"] = Panel(
            f"chunk #[bold]{chunk_index}[/]  len=[green]{chunk_len}[/]  Δt=[yellow]{elapsed:.3f}s[/]\n[dim]{preview[:60]}[/]",
            title="[bold]LLM chunk[/]",
            border_style="magenta",
            padding=(0, 1),
        )
    logger.debug(
        "[voice] llm_chunk conn=%s #%d len=%d Δt=%.3fs",
        conn_id, chunk_index, chunk_len, elapsed,
        extra=extra or None,
    )


def log_llm_done(conn_id: str, total_chars: int, total_chunks: int, elapsed: float) -> None:
    """Log when LLM stream is complete."""
    _maybe_panel(
        "LLM done",
        f"conn=[cyan]{conn_id}[/]\nchars=[green]{total_chars}[/]  chunks=[green]{total_chunks}[/]\nΔt=[yellow]{elapsed:.3f}s[/]",
        "magenta",
    )


def log_tts_sentence(conn_id: str, index: int, sentence_len: int, elapsed: float, text_preview: str = "") -> None:
    """Log when a sentence is sent to TTS."""
    _maybe_panel(
        f"TTS sentence #{index}",
        f"len=[green]{sentence_len}[/]  Δt=[yellow]{elapsed:.3f}s[/]\n[dim]{text_preview[:70]}[/]",
        "yellow",
    )


def log_tts_audio_chunk(conn_id: str, index: int, n_bytes: int, elapsed: float, emit_rich: bool = False) -> None:
    """Log one TTS audio chunk. Set emit_rich=True to print a Rich table (e.g. first and every 10th)."""
    extra = {}
    if _RICH_AVAILABLE and emit_rich:
        extra["voice_renderable"] = _table_one("TTS audio", f"chunk #{index}", f"{n_bytes} B", f"{elapsed:.3f}s")
    logger.debug(
        "[voice] tts_chunk conn=%s #%d len=%d Δt=%.3fs",
        conn_id, index, n_bytes, elapsed,
        extra=extra or None,
    )


def log_tts_flushed(conn_id: str, total_chunks: int, total_bytes: int, elapsed: float) -> None:
    """Log when TTS stream is done (Flushed received)."""
    _maybe_panel(
        "TTS flushed",
        f"conn=[cyan]{conn_id}[/]\nchunks=[green]{total_chunks}[/]  bytes=[green]{total_bytes}[/]\nΔt=[yellow]{elapsed:.3f}s[/]",
        "yellow",
    )


def log_turn_summary(timings: VoiceTurnTimings) -> None:
    """Emit the full turn summary panel with a table of all events."""
    timings.emit_panel()
