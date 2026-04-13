"""Display formatting utilities for the demo."""

import shutil


def get_width() -> int:
    """Get terminal width, default 80."""
    return min(shutil.get_terminal_size().columns, 100)


def banner(text: str):
    """Print a prominent section banner."""
    w = get_width()
    print()
    print("=" * w)
    print(f"  {text}")
    print("=" * w)
    print()


def sub_banner(text: str):
    """Print a subsection header."""
    w = get_width()
    print()
    print(f"--- {text} " + "-" * max(0, w - len(text) - 5))
    print()


def narrate(text: str):
    """Print narrator text with distinctive formatting."""
    w = get_width() - 4
    lines = _wrap(text, w)
    for line in lines:
        print(f"  {line}")
    print()


def tool_call(tool_name: str, args: str = ""):
    """Display a tool call being made."""
    if args:
        print(f"  >> {tool_name}({args})")
    else:
        print(f"  >> {tool_name}()")


def result_summary(text: str):
    """Display a brief result summary."""
    print(f"  <- {text}")


def table(headers: list[str], rows: list[list], max_col_width: int = 30):
    """Print a formatted table."""
    if not rows:
        print("  (no data)")
        return

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], min(len(str(cell)), max_col_width))

    # Print header
    header_line = "  " + "  ".join(
        str(h).ljust(widths[i]) for i, h in enumerate(headers)
    )
    print(header_line)
    print("  " + "  ".join("-" * w for w in widths))

    # Print rows
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            s = str(cell)
            if i < len(widths) and len(s) > widths[i]:
                s = s[: widths[i] - 2] + ".."
            cells.append(s.ljust(widths[i]) if i < len(widths) else s)
        print("  " + "  ".join(cells))
    print()


def source_tree(sources: list[dict]):
    """Display data lake contents as a directory tree."""
    print("  data/")
    # Group by directory
    dirs: dict[str, list] = {}
    for src in sources:
        path = src.get("file_path", "")
        parts = path.replace("data/", "").split("/")
        if len(parts) >= 2:
            d = parts[0]
            if d not in dirs:
                dirs[d] = []
            dirs[d].append({
                "file": parts[1],
                "format": src.get("format", "?"),
                "rows": src.get("row_count", 0),
            })

    for i, (dirname, files) in enumerate(sorted(dirs.items())):
        is_last_dir = i == len(dirs) - 1
        prefix = "  └── " if is_last_dir else "  ├── "
        print(f"{prefix}{dirname}/")

        for j, f in enumerate(sorted(files, key=lambda x: x["file"])):
            is_last_file = j == len(files) - 1
            connector = "  " if is_last_dir else "  │"
            file_prefix = "   └── " if is_last_file else "   ├── "
            rows_str = f"{f['rows']:,}" if isinstance(f['rows'], int) else "?"
            print(f"{connector}{file_prefix}{f['file']}  ({f['format']}, {rows_str} rows)")
    print()


def timeline(sources: list[dict]):
    """Display a simple ASCII timeline of data source coverage."""
    # Parse date ranges
    entries = []
    for src in sources:
        name = src.get("name", "")[:35]
        start = src.get("active_from", "")
        end = src.get("active_to", "")
        fmt = src.get("format", "")
        if start and end:
            entries.append((name, start, end, fmt))

    if not entries:
        return

    # Find overall range
    all_years = set()
    for _, start, end, _ in entries:
        all_years.add(int(start[:4]))
        all_years.add(int(end[:4]))

    min_year = min(all_years)
    max_year = max(all_years) + 1
    year_range = max_year - min_year

    # Header
    label_width = 38
    bar_width = min(50, year_range * 6)

    header = " " * label_width
    for y in range(min_year, max_year + 1):
        pos = int((y - min_year) / year_range * bar_width)
        header = header[:label_width + pos] + str(y) + header[label_width + pos + 4:]
    print(header)
    print(" " * label_width + "│" + "─" * (bar_width - 1) + "│")

    for name, start, end, fmt in entries:
        start_frac = (int(start[:4]) + int(start[5:7]) / 12 - min_year) / year_range
        end_frac = (int(end[:4]) + int(end[5:7]) / 12 - min_year) / year_range

        start_pos = max(0, int(start_frac * bar_width))
        end_pos = min(bar_width, int(end_frac * bar_width))

        bar = "░" * start_pos + "█" * max(1, end_pos - start_pos) + "░" * (bar_width - end_pos)
        label = f"{name} ({fmt})".ljust(label_width)
        print(f"{label}{bar}")

    print()


def pause(prompt: str = "Press Enter to continue..."):
    """Pause for presenter."""
    try:
        input(f"\n  [{prompt}]")
    except (EOFError, KeyboardInterrupt):
        pass
    print()


def _wrap(text: str, width: int) -> list[str]:
    """Simple word-wrapping."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    return lines
