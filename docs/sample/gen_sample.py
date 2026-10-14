"""Render the README sample report from made-up findings.

PYTHONPATH=src python docs/sample/gen_sample.py
"""

from datetime import UTC, datetime
from pathlib import Path

from cost_sentinel.checks import Finding
from cost_sentinel.config import Config
from cost_sentinel.report import summarize, to_html, to_text

OUT = Path(__file__).parent
F = Finding
findings = [
    F(
        "unattached_volume",
        "us-east-1",
        "vol-0a1b2c3d4e5f60001",
        "500 GiB gp2, not attached",
        50.0,
    ),
    F(
        "unattached_volume",
        "eu-west-1",
        "vol-0a1b2c3d4e5f60002",
        "200 GiB gp3, not attached",
        16.0,
    ),
    F(
        "unattached_volume",
        "us-east-1",
        "vol-0a1b2c3d4e5f60003",
        "100 GiB gp3, not attached",
        8.0,
    ),
    F(
        "idle_load_balancer",
        "us-east-1",
        "app/legacy-api/50dc6c495c0c9188",
        "application, 2 target groups, 0 healthy targets",
        16.43,
    ),
    F(
        "idle_load_balancer",
        "eu-west-1",
        "net/staging-nlb/6d0ecf831eec9f09",
        "network, 1 target groups, 0 healthy targets",
        16.43,
    ),
    F(
        "stopped_instance",
        "us-east-1",
        "i-0123456789abcdef0",
        "stopped 63 days, 300 GiB EBS still billed",
        24.0,
    ),
    F(
        "stopped_instance",
        "eu-west-1",
        "i-0fedcba9876543210",
        "stopped 35 days, 80 GiB EBS still billed",
        6.4,
    ),
    F(
        "old_snapshot",
        "us-east-1",
        "snap-0aaa111bbb222ccc3",
        "800 GiB, 212 days old, no AMI uses it",
        40.0,
    ),
    F(
        "old_snapshot",
        "us-east-1",
        "snap-0ddd444eee555fff6",
        "120 GiB, 131 days old, no AMI uses it",
        6.0,
    ),
    F(
        "old_snapshot",
        "eu-west-1",
        "snap-0777888999aaabbb0",
        "60 GiB, 97 days old, no AMI uses it",
        3.0,
    ),
    F(
        "unassociated_eip",
        "us-east-1",
        "eipalloc-0b1c2d3e4f5a60007",
        "34.200.0.10, not associated",
        3.65,
    ),
    F(
        "unassociated_eip",
        "eu-west-1",
        "eipalloc-0b1c2d3e4f5a60008",
        "52.30.0.20, not associated",
        3.65,
    ),
    F(
        "missing_tags",
        "us-east-1",
        "volume/vol-0a1b2c3d4e5f60009",
        "missing owner, cost-center",
        0.0,
    ),
    F(
        "missing_tags",
        "eu-west-1",
        "instance/i-0a1b2c3d4e5f60010",
        "missing owner",
        0.0,
    ),
]
cfg = Config(now=datetime(2026, 10, 12, 8, 0, tzinfo=UTC), top_n=6)
s = summarize(
    findings,
    [(findings[7], "would delete snapshot")],
    ignored=3,
    errors=[],
    cfg=cfg,
)
(OUT / "report.html").write_text(
    f'<!doctype html><meta charset="utf-8"><body style="margin:0;padding:24px;background:#fff">{to_html(s)}',
    encoding="utf-8",
)
(OUT / "report.txt").write_text(to_text(s) + "\n", encoding="utf-8")
print(s.subject)
