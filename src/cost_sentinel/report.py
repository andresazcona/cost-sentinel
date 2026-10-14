"""Turn findings into totals, a plaintext report (Slack, email text part) and an HTML email."""

from collections import defaultdict
from dataclasses import dataclass
from html import escape

from .checks import Finding
from .config import Config


@dataclass(frozen=True)
class Summary:
    total: float
    count: int
    by_check: list[tuple[str, int, float]]
    by_region: list[tuple[str, int, float]]
    top: list[Finding]
    actions: list[tuple[Finding, str]]
    ignored: int
    errors: list[str]
    dry_run: bool
    generated: str

    @property
    def subject(self) -> str:
        return f"cost-sentinel: ~${self.total:,.2f}/month of waste in {self.count} findings"


def _group(findings: list[Finding], key: str) -> list[tuple[str, int, float]]:
    count: dict[str, int] = defaultdict(int)
    cost: dict[str, float] = defaultdict(float)
    for f in findings:
        count[getattr(f, key)] += 1
        cost[getattr(f, key)] += f.monthly_cost
    return sorted(((k, count[k], round(cost[k], 2)) for k in count), key=lambda r: (-r[2], r[0]))


def summarize(
    findings: list[Finding],
    actions: list[tuple[Finding, str]],
    ignored: int,
    errors: list[str],
    cfg: Config,
) -> Summary:
    priced = sorted((f for f in findings if f.monthly_cost > 0), key=lambda f: -f.monthly_cost)
    return Summary(
        total=round(sum(f.monthly_cost for f in findings), 2),
        count=len(findings),
        by_check=_group(findings, "check"),
        by_region=_group(findings, "region"),
        top=priced[: cfg.top_n],
        actions=actions,
        ignored=ignored,
        errors=errors,
        dry_run=cfg.dry_run,
        generated=cfg.now.strftime("%Y-%m-%d %H:%M UTC"),
    )


def _table(headers: list[str], rows: list[list[str]]) -> str:
    grid = [headers, *rows]
    widths = [max(len(str(c)) for c in col) for col in zip(*grid, strict=True)]
    lines = [
        "  ".join(str(c).ljust(w) for c, w in zip(row, widths, strict=True)).rstrip()
        for row in grid
    ]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(lines)


def to_text(s: Summary) -> str:
    mode = "DRY-RUN (no changes made)" if s.dry_run else "LIVE remediation"
    parts = [
        s.subject,
        f"Generated {s.generated}. Mode: {mode}. {s.ignored} allowlisted resources skipped.",
        "Prices are approximate us-east-1 list prices.",
        "",
        "By check",
        _table(["check", "count", "$/month"], [[c, n, f"{v:,.2f}"] for c, n, v in s.by_check]),
        "",
        "By region",
        _table(["region", "count", "$/month"], [[r, n, f"{v:,.2f}"] for r, n, v in s.by_region]),
        "",
        f"Top {len(s.top)} offenders",
        _table(
            ["$/month", "check", "region", "resource", "detail"],
            [[f"{f.monthly_cost:,.2f}", f.check, f.region, f.resource_id, f.detail] for f in s.top],
        ),
    ]
    if s.actions:
        parts += [
            "",
            "Remediation",
            _table(
                ["resource", "check", "outcome"],
                [[f.resource_id, f.check, outcome] for f, outcome in s.actions],
            ),
        ]
    if s.errors:
        parts += ["", "Errors (these checks did not run):", *(f"- {e}" for e in s.errors)]
    return "\n".join(parts)


_TD = 'style="padding:6px 10px;border-bottom:1px solid #e5e7eb;text-align:{align}"'


def _html_table(headers: list[str], rows: list[list[str]], numeric: set[int]) -> str:
    def cell(tag: str, i: int, value: str) -> str:
        style = _TD.format(align="right" if i in numeric else "left")
        return f"<{tag} {style}>{escape(str(value))}</{tag}>"

    head = "".join(cell("th", i, h) for i, h in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(cell("td", i, v) for i, v in enumerate(row)) + "</tr>" for row in rows
    )
    return (
        '<table style="border-collapse:collapse;font-size:13px;margin:6px 0 18px">'
        f'<tr style="background:#f3f4f6">{head}</tr>{body}</table>'
    )


def to_html(s: Summary) -> str:
    mode = "Dry-run, no changes made" if s.dry_run else "Live remediation enabled"
    sections = [
        f'<h2 style="margin:0 0 4px">~${s.total:,.2f}/month of waste</h2>',
        f'<p style="color:#6b7280;margin:0 0 16px">{s.count} findings &middot; {escape(mode)}'
        f" &middot; {s.ignored} allowlisted skipped &middot; {escape(s.generated)}</p>",
        "<h3>By check</h3>",
        _html_table(
            ["Check", "Count", "$/month"],
            [[c, n, f"{v:,.2f}"] for c, n, v in s.by_check],
            {1, 2},
        ),
        "<h3>By region</h3>",
        _html_table(
            ["Region", "Count", "$/month"],
            [[r, n, f"{v:,.2f}"] for r, n, v in s.by_region],
            {1, 2},
        ),
        f"<h3>Top {len(s.top)} offenders</h3>",
        _html_table(
            ["$/month", "Check", "Region", "Resource", "Detail"],
            [[f"{f.monthly_cost:,.2f}", f.check, f.region, f.resource_id, f.detail] for f in s.top],
            {0},
        ),
    ]
    if s.actions:
        sections += [
            "<h3>Remediation</h3>",
            _html_table(
                ["Resource", "Check", "Outcome"],
                [[f.resource_id, f.check, outcome] for f, outcome in s.actions],
                set(),
            ),
        ]
    if s.errors:
        items = "".join(f"<li>{escape(e)}</li>" for e in s.errors)
        sections.append(f'<h3 style="color:#b91c1c">Checks that did not run</h3><ul>{items}</ul>')
    sections.append(
        '<p style="color:#9ca3af;font-size:12px">Estimates use approximate us-east-1 list prices. '
        "Tag a resource <code>cost-sentinel:ignore=true</code> to exclude it.</p>"
    )
    return (
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
        f'color:#111827;max-width:880px">{"".join(sections)}</div>'
    )
