import json

import boto3
import pytest
from botocore.exceptions import ClientError
from conftest import tag

from cost_sentinel import handler
from cost_sentinel.checks import IGNORE_TAG
from cost_sentinel.config import Config

SENDER = "finops@example.com"
WEBHOOK = "/cost-sentinel/slack-webhook"


@pytest.fixture
def slack(monkeypatch):
    sent = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"ok"

    def fake_urlopen(req, timeout):
        sent.append((req.full_url, json.loads(req.data)))
        return Response()

    monkeypatch.setattr(handler.urllib.request, "urlopen", fake_urlopen)
    return sent


@pytest.fixture
def outputs(ec2):
    """SES sender verified and the Slack webhook stored as a SecureString, as Terraform expects."""
    boto3.client("ses", region_name="us-east-1").verify_email_identity(EmailAddress=SENDER)
    boto3.client("ssm", region_name="us-east-1").put_parameter(
        Name=WEBHOOK, Value="https://hooks.slack.com/services/T0/B0/x", Type="SecureString"
    )


def test_end_to_end_across_regions(ec2, outputs, slack, make_cfg):
    eu = boto3.client("ec2", region_name="eu-west-1")
    ec2.create_volume(AvailabilityZone="us-east-1a", Size=100, VolumeType="gp2")
    eu.allocate_address(Domain="vpc")
    ec2.create_volume(
        AvailabilityZone="us-east-1a",
        Size=999,
        TagSpecifications=[{"ResourceType": "volume", "Tags": tag(IGNORE_TAG, "true")}],
    )
    cfg = make_cfg(
        regions=("us-east-1", "eu-west-1"),
        required_tags=(),
        remediate=frozenset({"unattached_volume"}),
        ses_sender=SENDER,
        ses_recipients=("team@example.com",),
        slack_webhook_param=WEBHOOK,
    )

    s = handler.run(cfg)

    assert s.total == 13.65  # 100 GiB gp2 ($10.00) + one EIP ($3.65)
    assert s.by_region == [("us-east-1", 1, 10.0), ("eu-west-1", 1, 3.65)]
    assert s.ignored == 1  # the 999 GiB volume is allowlisted, not counted
    assert [outcome for _, outcome in s.actions] == ["would snapshot then delete volume"]
    quota = boto3.client("ses", region_name="us-east-1").get_send_quota()
    assert quota["SentLast24Hours"] == 1
    [(url, payload)] = slack
    assert url.startswith("https://hooks.slack.com/")
    assert "~$13.65/month" in payload["text"]


def test_failing_check_is_reported_and_others_still_run(ec2, monkeypatch, make_cfg):
    def denied(region, cfg):
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "DescribeX")

    ec2.allocate_address(Domain="vpc")
    monkeypatch.setattr(handler, "CHECKS", (denied, *handler.CHECKS))

    s = handler.run(make_cfg(required_tags=()))

    assert s.count == 1
    assert len(s.errors) == 1
    assert "denied in us-east-1" in s.errors[0]


def test_unknown_remediation_is_rejected(make_cfg):
    with pytest.raises(ValueError, match="idle_load_balancer"):
        handler.run(make_cfg(remediate=frozenset({"idle_load_balancer"})))


def test_slack_webhook_must_be_https(ec2, make_cfg):
    boto3.client("ssm", region_name="us-east-1").put_parameter(
        Name=WEBHOOK, Value="file:///etc/passwd", Type="SecureString"
    )
    with pytest.raises(ValueError, match="https"):
        handler.run(make_cfg(required_tags=(), slack_webhook_param=WEBHOOK))


def test_config_defaults_are_safe():
    cfg = Config.from_env({"REGIONS": "us-east-1, eu-west-1", "DRY_RUN": "flase"})
    assert cfg.regions == ("us-east-1", "eu-west-1")
    assert cfg.dry_run is True  # a typo keeps dry-run on
    assert cfg.remediate == frozenset()
    assert cfg.required_tags == ("owner", "cost-center")
    assert Config.from_env({"DRY_RUN": "False"}).dry_run is False


def test_lambda_handler_returns_summary(ec2, monkeypatch):
    monkeypatch.setenv("REGIONS", "us-east-1")
    monkeypatch.setenv("REQUIRED_TAGS", "")
    ec2.allocate_address(Domain="vpc")

    result = handler.lambda_handler({}, None)

    assert result == {"findings": 1, "monthly_waste_usd": 3.65, "remediated": 0, "errors": 0}
