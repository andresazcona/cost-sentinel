from cost_sentinel.checks import Finding
from cost_sentinel.report import summarize, to_html, to_text

FINDINGS = [
    Finding("unattached_volume", "us-east-1", "vol-a", "500 GiB gp2", 50.0),
    Finding("unattached_volume", "eu-west-1", "vol-b", "100 GiB gp3", 8.0),
    Finding("idle_load_balancer", "us-east-1", "old-alb", "application", 16.43),
    Finding("unassociated_eip", "eu-west-1", "eipalloc-1", "198.51.100.7", 3.65),
    Finding("missing_tags", "us-east-1", "volume/vol-a", "missing owner", 0.0),
]


def test_totals_by_check_and_region(make_cfg):
    s = summarize(FINDINGS, [], ignored=2, errors=[], cfg=make_cfg())

    assert s.total == 78.08
    assert s.count == 5
    assert s.by_check == [
        ("unattached_volume", 2, 58.0),
        ("idle_load_balancer", 1, 16.43),
        ("unassociated_eip", 1, 3.65),
        ("missing_tags", 1, 0.0),
    ]
    assert s.by_region == [("us-east-1", 3, 66.43), ("eu-west-1", 2, 11.65)]
    assert s.ignored == 2


def test_top_offenders_sorted_limited_and_skip_zero_cost(make_cfg):
    s = summarize(FINDINGS, [], 0, [], make_cfg(top_n=3))
    assert [f.resource_id for f in s.top] == ["vol-a", "old-alb", "vol-b"]


def test_text_report_has_sections_and_mode(make_cfg):
    f = FINDINGS[0]
    text = to_text(
        summarize(FINDINGS, [(f, "would delete")], 0, ["old_amis in x: denied"], make_cfg())
    )

    assert text.startswith("cost-sentinel: ~$78.08/month of waste in 5 findings")
    assert "DRY-RUN" in text
    for section in ("By check", "By region", "Top 4 offenders", "Remediation", "Errors"):
        assert section in text


def test_html_escapes_resource_data(make_cfg):
    evil = Finding("missing_tags", "us-east-1", "<script>x</script>", "d", 1.0)
    html = to_html(summarize([evil], [], 0, [], make_cfg()))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
