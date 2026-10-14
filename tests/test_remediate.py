import pytest
from conftest import REGION, tag

from cost_sentinel.checks import IGNORE_TAG, Finding, unattached_volumes
from cost_sentinel.remediate import remediate


@pytest.fixture
def volume(ec2):
    return ec2.create_volume(AvailabilityZone="us-east-1a", Size=20)["VolumeId"]


def volume_exists(ec2, volume_id):
    return any(v["VolumeId"] == volume_id for v in ec2.describe_volumes()["Volumes"])


def test_remediation_is_off_unless_check_is_listed(ec2, volume, make_cfg):
    [f] = unattached_volumes(REGION, make_cfg())
    assert remediate(f, make_cfg(dry_run=False)) is None
    assert volume_exists(ec2, volume)


def test_dry_run_reports_but_changes_nothing(ec2, volume, make_cfg):
    cfg = make_cfg(remediate=frozenset({"unattached_volume"}))  # dry_run defaults to True
    [f] = unattached_volumes(REGION, cfg)

    assert remediate(f, cfg) == "would snapshot then delete volume"
    assert volume_exists(ec2, volume)
    assert ec2.describe_snapshots(OwnerIds=["self"])["Snapshots"] == []


def test_live_run_snapshots_volume_before_deleting(ec2, volume, make_cfg):
    cfg = make_cfg(dry_run=False, remediate=frozenset({"unattached_volume"}))
    [f] = unattached_volumes(REGION, cfg)

    outcome = remediate(f, cfg)

    [snap] = ec2.describe_snapshots(OwnerIds=["self"])["Snapshots"]
    assert snap["VolumeId"] == volume
    assert {"Key": "cost-sentinel:source-volume", "Value": volume} in snap["Tags"]
    assert outcome == f"deleted, backup {snap['SnapshotId']}"
    assert not volume_exists(ec2, volume)


def test_allowlisted_resource_is_never_touched(ec2, make_cfg):
    volume = ec2.create_volume(
        AvailabilityZone="us-east-1a",
        Size=20,
        TagSpecifications=[{"ResourceType": "volume", "Tags": tag(IGNORE_TAG, "true")}],
    )["VolumeId"]
    cfg = make_cfg(dry_run=False, remediate=frozenset({"unattached_volume"}))
    [f] = unattached_volumes(REGION, cfg)

    assert remediate(f, cfg) is None
    assert volume_exists(ec2, volume)


def test_release_eip(ec2, make_cfg):
    alloc = ec2.allocate_address(Domain="vpc")["AllocationId"]
    cfg = make_cfg(dry_run=False, remediate=frozenset({"unassociated_eip"}))
    f = Finding("unassociated_eip", REGION, alloc, "", 3.65)

    assert remediate(f, cfg) == "released"
    assert ec2.describe_addresses()["Addresses"] == []


def test_failure_is_reported_not_raised(ec2, make_cfg):
    cfg = make_cfg(dry_run=False, remediate=frozenset({"old_snapshot"}))
    f = Finding("old_snapshot", REGION, "snap-does-not-exist", "", 1.0)

    assert remediate(f, cfg).startswith("failed:")


def test_report_only_checks_have_no_action(ec2, make_cfg):
    cfg = make_cfg(dry_run=False, remediate=frozenset({"idle_load_balancer"}))
    f = Finding("idle_load_balancer", REGION, "alb", "", 16.43)
    assert remediate(f, cfg) is None
