"""Runtime configuration, read once from Lambda environment variables."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _list(value: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in value.split(",") if x.strip())


@dataclass(frozen=True)
class Config:
    regions: tuple[str, ...] = ("us-east-1",)
    required_tags: tuple[str, ...] = ("owner", "cost-center")
    snapshot_max_age_days: int = 90
    stopped_max_days: int = 30
    ami_max_age_days: int = 180
    check_amis: bool = False
    dry_run: bool = True
    remediate: frozenset[str] = frozenset()
    ses_sender: str = ""
    ses_recipients: tuple[str, ...] = ()
    slack_webhook_param: str = ""
    top_n: int = 10
    now: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Config":
        return cls(
            regions=_list(env.get("REGIONS", env.get("AWS_REGION", "us-east-1"))),
            required_tags=_list(env.get("REQUIRED_TAGS", "owner,cost-center")),
            snapshot_max_age_days=int(env.get("SNAPSHOT_MAX_AGE_DAYS", "90")),
            stopped_max_days=int(env.get("STOPPED_MAX_DAYS", "30")),
            ami_max_age_days=int(env.get("AMI_MAX_AGE_DAYS", "180")),
            check_amis=env.get("CHECK_AMIS", "false").strip().lower() == "true",
            # Only an explicit "false" turns dry-run off: a typo must never delete things.
            dry_run=env.get("DRY_RUN", "true").strip().lower() != "false",
            remediate=frozenset(_list(env.get("REMEDIATE", ""))),
            ses_sender=env.get("SES_SENDER", ""),
            ses_recipients=_list(env.get("SES_RECIPIENTS", "")),
            slack_webhook_param=env.get("SLACK_WEBHOOK_PARAM", ""),
            top_n=int(env.get("TOP_N", "10")),
        )
