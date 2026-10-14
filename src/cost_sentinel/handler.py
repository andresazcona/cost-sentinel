"""Lambda entry point: run every check in every region, remediate if allowed, send the report."""

import json
import logging
import urllib.request

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .checks import CHECKS, Finding
from .config import Config
from .remediate import ACTIONS, remediate
from .report import Summary, summarize, to_html, to_text

log = logging.getLogger()
log.setLevel(logging.INFO)


def run(cfg: Config) -> Summary:
    unknown = cfg.remediate - ACTIONS.keys()
    if unknown:
        raise ValueError(f"REMEDIATE has checks without a remediation: {sorted(unknown)}")

    findings: list[Finding] = []
    errors: list[str] = []
    for region in cfg.regions:
        for check in CHECKS:
            try:
                findings += check(region, cfg)
            except (ClientError, BotoCoreError) as exc:  # e.g. AccessDenied, region not enabled
                log.exception("%s failed in %s", check.__name__, region)
                errors.append(f"{check.__name__} in {region}: {exc}")

    active = [f for f in findings if not f.ignored]
    actions = [(f, outcome) for f in active if (outcome := remediate(f, cfg))]
    for f in active:  # the full list lives in CloudWatch Logs; the report keeps the top N
        log.info(json.dumps({"finding": f.__dict__}, default=str))

    summary = summarize(active, actions, len(findings) - len(active), errors, cfg)
    notify(summary, cfg)
    return summary


def notify(s: Summary, cfg: Config) -> None:
    text = to_text(s)
    if cfg.ses_sender and cfg.ses_recipients:
        boto3.client("ses").send_email(
            Source=cfg.ses_sender,
            Destination={"ToAddresses": list(cfg.ses_recipients)},
            Message={
                "Subject": {"Data": s.subject},
                "Body": {"Text": {"Data": text}, "Html": {"Data": to_html(s)}},
            },
        )
    if cfg.slack_webhook_param:
        param = boto3.client("ssm").get_parameter(Name=cfg.slack_webhook_param, WithDecryption=True)
        url = param["Parameter"]["Value"]
        if not url.startswith("https://"):  # urlopen also speaks file:// and ftp://
            raise ValueError("Slack webhook parameter must hold an https:// URL")
        body = json.dumps({"text": f"*{s.subject}*\n```{text}```"}).encode()
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=body, headers=headers)  # noqa: S310 - https checked
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            resp.read()


def lambda_handler(event: dict, context: object) -> dict:
    s = run(Config.from_env())
    return {
        "findings": s.count,
        "monthly_waste_usd": s.total,
        "remediated": len(s.actions),
        "errors": len(s.errors),
    }
