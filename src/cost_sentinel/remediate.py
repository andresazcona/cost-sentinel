"""Optional clean-up: off unless a check is listed in REMEDIATE; dry-run unless DRY_RUN=false."""

import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .checks import Finding
from .config import Config

log = logging.getLogger(__name__)


def _snapshot_then_delete_volume(ec2, f: Finding) -> str:
    snap = ec2.create_snapshot(
        VolumeId=f.resource_id,
        Description=f"cost-sentinel backup of {f.resource_id} before delete",
        TagSpecifications=[
            {
                "ResourceType": "snapshot",
                "Tags": [{"Key": "cost-sentinel:source-volume", "Value": f.resource_id}],
            }
        ],
    )
    # Never delete the volume until its backup is durable. Up to 10 minutes (Lambda timeout is 15).
    ec2.get_waiter("snapshot_completed").wait(
        SnapshotIds=[snap["SnapshotId"]], WaiterConfig={"Delay": 15, "MaxAttempts": 40}
    )
    ec2.delete_volume(VolumeId=f.resource_id)
    return f"deleted, backup {snap['SnapshotId']}"


def _release_eip(ec2, f: Finding) -> str:
    ec2.release_address(AllocationId=f.resource_id)
    return "released"


def _delete_snapshot(ec2, f: Finding) -> str:
    ec2.delete_snapshot(SnapshotId=f.resource_id)
    return "deleted"


def _deregister_ami(ec2, f: Finding) -> str:
    # Backing snapshots are kept; the old_snapshot check picks them up on a later run.
    ec2.deregister_image(ImageId=f.resource_id)
    return "deregistered, snapshots kept"


# Stopped instances, idle load balancers and missing tags are report-only: deleting them
# needs a human who knows what they are for.
ACTIONS = {
    "unattached_volume": ("snapshot then delete volume", _snapshot_then_delete_volume),
    "unassociated_eip": ("release address", _release_eip),
    "old_snapshot": ("delete snapshot", _delete_snapshot),
    "old_ami": ("deregister image", _deregister_ami),
}


def remediate(f: Finding, cfg: Config) -> str | None:
    """Return a one-line outcome, or None when this finding is not eligible for remediation."""
    if f.check not in cfg.remediate or f.check not in ACTIONS or f.ignored:
        return None
    description, action = ACTIONS[f.check]
    if cfg.dry_run:
        log.info("DRY_RUN: would %s %s in %s", description, f.resource_id, f.region)
        return f"would {description}"
    try:
        outcome = action(boto3.client("ec2", region_name=f.region), f)
    except (ClientError, BotoCoreError) as exc:  # one failure must not stop the report
        log.exception("remediation failed for %s", f.resource_id)
        return f"failed: {exc}"
    log.info("%s %s in %s: %s", description, f.resource_id, f.region, outcome)
    return outcome
