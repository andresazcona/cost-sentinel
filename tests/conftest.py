import os

# Fake credentials before boto3/moto load: a test must never be able to reach a real account.
os.environ.update(
    AWS_ACCESS_KEY_ID="testing",
    AWS_SECRET_ACCESS_KEY="testing",
    AWS_SESSION_TOKEN="testing",
    AWS_DEFAULT_REGION="us-east-1",
    MOTO_EC2_LOAD_DEFAULT_AMIS="false",
)

from datetime import UTC, datetime, timedelta  # noqa: E402

import boto3  # noqa: E402
import pytest  # noqa: E402
from moto import mock_aws  # noqa: E402

from cost_sentinel.config import Config  # noqa: E402

REGION = "us-east-1"
AMI = "ami-12c6146b"


@pytest.fixture
def ec2():
    with mock_aws():
        yield boto3.client("ec2", region_name=REGION)


@pytest.fixture
def make_cfg():
    """Config whose clock runs `days_ahead` in the future, so resources created now look old."""

    def make(days_ahead: int = 0, **overrides) -> Config:
        now = datetime.now(UTC) + timedelta(days=days_ahead)
        return Config(regions=(REGION,), now=now, **overrides)

    return make


def tag(key: str, value: str) -> list[dict]:
    return [{"Key": key, "Value": value}]
