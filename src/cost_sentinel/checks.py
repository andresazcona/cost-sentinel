"""Waste checks. Each check is a plain function `(region, cfg) -> list[Finding]`."""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import batched

import boto3

from .config import Config

IGNORE_TAG = "cost-sentinel:ignore"

# Approximate on-demand list prices in USD for us-east-1 (checked 2026-10).
# Other regions are usually 0-30% higher, so treat every estimate as order-of-magnitude.
HOURS_PER_MONTH = 730
EBS_GB_MONTH = {
    "gp3": 0.08,
    "gp2": 0.10,
    "io1": 0.125,
    "io2": 0.125,
    "st1": 0.045,
    "sc1": 0.015,
    "standard": 0.05,
}
# Snapshots are incremental, so size * price is an upper bound.
SNAPSHOT_GB_MONTH = 0.05
EIP_HOUR = 0.005
# Base hourly charge only; LCU/NLCU usage on an idle balancer is close to zero.
LB_HOUR = {"application": 0.0225, "network": 0.0225, "gateway": 0.0125}


@dataclass(frozen=True)
class Finding:
    check: str
    region: str
    resource_id: str
    detail: str
    monthly_cost: float
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def ignored(self) -> bool:
        return self.tags.get(IGNORE_TAG, "").strip().lower() == "true"


def _tags(items: list[dict] | None) -> dict[str, str]:
    return {t["Key"]: t["Value"] for t in items or []}


def _ebs_cost(size_gb: int, volume_type: str) -> float:
    return round(size_gb * EBS_GB_MONTH.get(volume_type, EBS_GB_MONTH["gp2"]), 2)


def _own_images(ec2) -> list[dict]:
    return [
        img
        for page in ec2.get_paginator("describe_images").paginate(Owners=["self"])
        for img in page["Images"]
    ]


def _instances(ec2, **kwargs) -> list[dict]:
    return [
        inst
        for page in ec2.get_paginator("describe_instances").paginate(**kwargs)
        for res in page["Reservations"]
        for inst in res["Instances"]
    ]


def unattached_volumes(region: str, cfg: Config) -> list[Finding]:
    ec2 = boto3.client("ec2", region_name=region)
    pages = ec2.get_paginator("describe_volumes").paginate(
        Filters=[{"Name": "status", "Values": ["available"]}]
    )
    return [
        Finding(
            "unattached_volume",
            region,
            v["VolumeId"],
            f"{v['Size']} GiB {v['VolumeType']}, not attached",
            _ebs_cost(v["Size"], v["VolumeType"]),
            _tags(v.get("Tags")),
        )
        for page in pages
        for v in page["Volumes"]
    ]


def unassociated_eips(region: str, cfg: Config) -> list[Finding]:
    ec2 = boto3.client("ec2", region_name=region)
    return [
        Finding(
            "unassociated_eip",
            region,
            a["AllocationId"],
            f"{a['PublicIp']}, not associated",
            round(EIP_HOUR * HOURS_PER_MONTH, 2),
            _tags(a.get("Tags")),
        )
        for a in ec2.describe_addresses()["Addresses"]
        if "AssociationId" not in a
    ]


def old_snapshots(region: str, cfg: Config) -> list[Finding]:
    ec2 = boto3.client("ec2", region_name=region)
    cutoff = cfg.now - timedelta(days=cfg.snapshot_max_age_days)
    backing_amis = {
        bdm["Ebs"]["SnapshotId"]
        for img in _own_images(ec2)
        for bdm in img.get("BlockDeviceMappings", [])
        if "SnapshotId" in bdm.get("Ebs", {})
    }
    pages = ec2.get_paginator("describe_snapshots").paginate(OwnerIds=["self"])
    return [
        Finding(
            "old_snapshot",
            region,
            s["SnapshotId"],
            f"{s['VolumeSize']} GiB, {(cfg.now - s['StartTime']).days} days old, no AMI uses it",
            round(s["VolumeSize"] * SNAPSHOT_GB_MONTH, 2),
            _tags(s.get("Tags")),
        )
        for page in pages
        for s in page["Snapshots"]
        if s["StartTime"] < cutoff and s["SnapshotId"] not in backing_amis
    ]


# AWS writes e.g. "User initiated (2026-01-31 10:00:00 GMT)" when an instance is stopped.
_STOPPED_AT = re.compile(r"\((\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def stopped_instances(region: str, cfg: Config) -> list[Finding]:
    ec2 = boto3.client("ec2", region_name=region)
    cutoff = cfg.now - timedelta(days=cfg.stopped_max_days)
    stale = []
    for inst in _instances(ec2, Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]):
        match = _STOPPED_AT.search(inst.get("StateTransitionReason", ""))
        if not match:
            continue  # stop time unknown: report nothing rather than guess
        stopped_at = datetime.strptime(match[1], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        if stopped_at < cutoff:
            stale.append((inst, stopped_at))
    if not stale:
        return []

    volume_ids = [
        bdm["Ebs"]["VolumeId"]
        for inst, _ in stale
        for bdm in inst.get("BlockDeviceMappings", [])
        if "Ebs" in bdm
    ]
    # ponytail: one DescribeVolumes call, fine up to ~500 volumes; batch it if a region has more.
    volumes = {
        v["VolumeId"]: v
        for v in (ec2.describe_volumes(VolumeIds=volume_ids)["Volumes"] if volume_ids else [])
    }
    findings = []
    for inst, stopped_at in stale:
        attached = [
            volumes[bdm["Ebs"]["VolumeId"]]
            for bdm in inst.get("BlockDeviceMappings", [])
            if "Ebs" in bdm and bdm["Ebs"]["VolumeId"] in volumes
        ]
        gb = sum(v["Size"] for v in attached)
        findings.append(
            Finding(
                "stopped_instance",
                region,
                inst["InstanceId"],
                f"stopped {(cfg.now - stopped_at).days} days, {gb} GiB EBS still billed",
                round(sum(_ebs_cost(v["Size"], v["VolumeType"]) for v in attached), 2),
                _tags(inst.get("Tags")),
            )
        )
    return findings


def old_amis(region: str, cfg: Config) -> list[Finding]:
    if not cfg.check_amis:
        return []
    ec2 = boto3.client("ec2", region_name=region)
    cutoff = cfg.now - timedelta(days=cfg.ami_max_age_days)
    in_use = {inst["ImageId"] for inst in _instances(ec2)}
    findings = []
    for img in _own_images(ec2):
        created = datetime.fromisoformat(img["CreationDate"])
        if created >= cutoff or img["ImageId"] in in_use:
            continue
        gb = sum(
            bdm["Ebs"].get("VolumeSize", 0)
            for bdm in img.get("BlockDeviceMappings", [])
            if "Ebs" in bdm
        )
        findings.append(
            Finding(
                "old_ami",
                region,
                img["ImageId"],
                f"{img.get('Name', '')}, {(cfg.now - created).days} days old, no instance uses it",
                round(gb * SNAPSHOT_GB_MONTH, 2),
                _tags(img.get("Tags")),
            )
        )
    return findings


def idle_load_balancers(region: str, cfg: Config) -> list[Finding]:
    elb = boto3.client("elbv2", region_name=region)
    lbs = [
        lb
        for page in elb.get_paginator("describe_load_balancers").paginate()
        for lb in page["LoadBalancers"]
    ]
    tags = {}
    for chunk in batched([lb["LoadBalancerArn"] for lb in lbs], 20):  # DescribeTags max is 20
        for desc in elb.describe_tags(ResourceArns=list(chunk))["TagDescriptions"]:
            tags[desc["ResourceArn"]] = _tags(desc.get("Tags"))

    groups_by_lb = defaultdict(list)
    for page in elb.get_paginator("describe_target_groups").paginate():
        for tg in page["TargetGroups"]:
            for lb_arn in tg.get("LoadBalancerArns", []):
                groups_by_lb[lb_arn].append(tg)

    findings = []
    for lb in lbs:
        groups = groups_by_lb[lb["LoadBalancerArn"]]
        healthy = sum(
            1
            for tg in groups
            for t in elb.describe_target_health(TargetGroupArn=tg["TargetGroupArn"])[
                "TargetHealthDescriptions"
            ]
            if t["TargetHealth"]["State"] == "healthy"
        )
        if healthy:
            continue
        findings.append(
            Finding(
                "idle_load_balancer",
                region,
                lb["LoadBalancerName"],
                f"{lb['Type']}, {len(groups)} target groups, 0 healthy targets",
                round(LB_HOUR.get(lb["Type"], LB_HOUR["application"]) * HOURS_PER_MONTH, 2),
                tags.get(lb["LoadBalancerArn"], {}),
            )
        )
    return findings


def missing_tags(region: str, cfg: Config) -> list[Finding]:
    """Governance, not waste: costs nobody can attribute. Reported at $0."""
    if not cfg.required_tags:
        return []
    api = boto3.client("resourcegroupstaggingapi", region_name=region)
    findings = []
    for page in api.get_paginator("get_resources").paginate():
        for res in page["ResourceTagMappingList"]:
            tags = _tags(res.get("Tags"))
            missing = [t for t in cfg.required_tags if t not in tags]
            if missing:
                # arn:aws:ec2:us-east-1:111111111111:volume/vol-1 -> volume/vol-1
                short_id = res["ResourceARN"].split(":", 5)[-1]
                findings.append(
                    Finding(
                        "missing_tags", region, short_id, "missing " + ", ".join(missing), 0.0, tags
                    )
                )
    return findings


CHECKS = (
    unattached_volumes,
    unassociated_eips,
    old_snapshots,
    stopped_instances,
    old_amis,
    idle_load_balancers,
    missing_tags,
)
