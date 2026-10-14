import boto3
from conftest import AMI, REGION, tag

from cost_sentinel import checks


def ids(findings):
    return {f.resource_id for f in findings}


def test_unattached_volume_is_found_and_priced(ec2, make_cfg):
    loose = ec2.create_volume(AvailabilityZone="us-east-1a", Size=100, VolumeType="gp3")
    ec2.run_instances(ImageId=AMI, MinCount=1, MaxCount=1)  # its root volume is attached

    [f] = checks.unattached_volumes(REGION, make_cfg())

    assert f.resource_id == loose["VolumeId"]
    assert f.monthly_cost == 8.00  # 100 GiB * $0.08


def test_unassociated_eip_only(ec2, make_cfg):
    free = ec2.allocate_address(Domain="vpc")
    used = ec2.allocate_address(Domain="vpc")
    inst = ec2.run_instances(ImageId=AMI, MinCount=1, MaxCount=1)["Instances"][0]
    ec2.associate_address(AllocationId=used["AllocationId"], InstanceId=inst["InstanceId"])

    findings = checks.unassociated_eips(REGION, make_cfg())

    assert ids(findings) == {free["AllocationId"]}
    assert findings[0].monthly_cost == 3.65  # $0.005 * 730 h


def test_old_snapshot_skips_recent_and_ami_backed(ec2, make_cfg):
    vol = ec2.create_volume(AvailabilityZone="us-east-1a", Size=50)
    orphan = ec2.create_snapshot(VolumeId=vol["VolumeId"])
    inst = ec2.run_instances(ImageId=AMI, MinCount=1, MaxCount=1)["Instances"][0]
    image = ec2.create_image(InstanceId=inst["InstanceId"], Name="golden")
    backing = ec2.describe_images(ImageIds=[image["ImageId"]])["Images"][0]
    backing_snap = backing["BlockDeviceMappings"][0]["Ebs"]["SnapshotId"]

    assert checks.old_snapshots(REGION, make_cfg(days_ahead=10)) == []
    findings = checks.old_snapshots(REGION, make_cfg(days_ahead=100))

    assert ids(findings) == {orphan["SnapshotId"]}
    assert backing_snap not in ids(findings)
    assert findings[0].monthly_cost == 2.50  # 50 GiB * $0.05


def test_stopped_instance_reports_ebs_cost(ec2, make_cfg):
    stopped, running = ec2.run_instances(ImageId=AMI, MinCount=2, MaxCount=2)["Instances"]
    ec2.stop_instances(InstanceIds=[stopped["InstanceId"]])

    assert checks.stopped_instances(REGION, make_cfg(days_ahead=5)) == []
    [f] = checks.stopped_instances(REGION, make_cfg(days_ahead=45))

    assert f.resource_id == stopped["InstanceId"]
    assert f.detail.startswith("stopped 45 days")
    assert f.monthly_cost > 0


def test_stopped_instance_without_parseable_time_is_skipped(monkeypatch, make_cfg):
    class FakeEC2:
        def get_paginator(self, _):
            return self

        def paginate(self, **_):
            inst = {"InstanceId": "i-1", "StateTransitionReason": "", "BlockDeviceMappings": []}
            return [{"Reservations": [{"Instances": [inst]}]}]

    monkeypatch.setattr(checks.boto3, "client", lambda *a, **k: FakeEC2())
    assert checks.stopped_instances(REGION, make_cfg(days_ahead=365)) == []


def test_old_ami_is_opt_in_and_skips_amis_in_use(ec2, make_cfg):
    inst = ec2.run_instances(ImageId=AMI, MinCount=1, MaxCount=1)["Instances"][0]
    unused = ec2.create_image(InstanceId=inst["InstanceId"], Name="unused-ami")["ImageId"]
    in_use = ec2.create_image(InstanceId=inst["InstanceId"], Name="in-use-ami")["ImageId"]
    ec2.run_instances(ImageId=in_use, MinCount=1, MaxCount=1)

    assert checks.old_amis(REGION, make_cfg(days_ahead=365)) == []  # check_amis defaults to off
    findings = checks.old_amis(REGION, make_cfg(days_ahead=365, check_amis=True))

    assert ids(findings) == {unused}


def test_idle_load_balancer(ec2, make_cfg):
    elb = boto3.client("elbv2", region_name=REGION)
    vpc = ec2.describe_vpcs()["Vpcs"][0]["VpcId"]
    subnets = [s["SubnetId"] for s in ec2.describe_subnets()["Subnets"]][:2]
    elb.create_load_balancer(Name="idle-alb", Subnets=subnets)
    busy = elb.create_load_balancer(Name="busy-alb", Subnets=subnets)["LoadBalancers"][0]
    tg = elb.create_target_group(Name="web", Protocol="HTTP", Port=80, VpcId=vpc)["TargetGroups"][0]
    elb.create_listener(
        LoadBalancerArn=busy["LoadBalancerArn"],
        Protocol="HTTP",
        Port=80,
        DefaultActions=[{"Type": "forward", "TargetGroupArn": tg["TargetGroupArn"]}],
    )
    inst = ec2.run_instances(ImageId=AMI, MinCount=1, MaxCount=1)["Instances"][0]
    elb.register_targets(TargetGroupArn=tg["TargetGroupArn"], Targets=[{"Id": inst["InstanceId"]}])

    [f] = checks.idle_load_balancers(REGION, make_cfg())

    assert f.resource_id == "idle-alb"
    assert f.monthly_cost == 16.43  # $0.0225 * 730 h


def test_missing_tags(ec2, make_cfg):
    vol = ec2.create_volume(
        AvailabilityZone="us-east-1a",
        Size=1,
        TagSpecifications=[{"ResourceType": "volume", "Tags": tag("owner", "data-team")}],
    )
    ec2.create_volume(
        AvailabilityZone="us-east-1a",
        Size=1,
        TagSpecifications=[
            {
                "ResourceType": "volume",
                "Tags": tag("owner", "web") + tag("cost-center", "cc-42"),
            }
        ],
    )

    [f] = checks.missing_tags(REGION, make_cfg())

    assert f.resource_id == f"volume/{vol['VolumeId']}"
    assert f.detail == "missing cost-center"
    assert f.monthly_cost == 0.0
    assert checks.missing_tags(REGION, make_cfg(required_tags=())) == []


def test_allowlist_tag_marks_finding_ignored(ec2, make_cfg):
    ec2.create_volume(
        AvailabilityZone="us-east-1a",
        Size=10,
        TagSpecifications=[{"ResourceType": "volume", "Tags": tag("cost-sentinel:ignore", "True")}],
    )
    [f] = checks.unattached_volumes(REGION, make_cfg())
    assert f.ignored
