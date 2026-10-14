"""Generate cost-sentinel.drawio (architecture + decision flow). Python 3 stdlib only.

python docs/diagrams/gen_drawio.py
"""

from pathlib import Path
from xml.sax.saxutils import quoteattr

OUT = Path(__file__).with_name("cost-sentinel.drawio")

COMPUTE, STORAGE, NETWORK = "#ED7100", "#7AA116", "#8C4FFF"
SECURITY, MANAGEMENT, INTEGRATION = "#DD344C", "#E7157B", "#E7157B"
BLUE, RED, GREY, GREEN = "#1A73E8", "#C62828", "#888888", "#2E7D32"

ICON = (
    "sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor={color};"
    "strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;"
    "html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;"
    "resIcon=mxgraph.aws4.{res};"
)
GROUP = (
    "points=[];outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=12;"
    "fontStyle=1;container=0;pointerEvents=0;collapsible=0;recursiveResize=0;"
    "shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.{icon};strokeColor={color};fillColor=none;"
    "verticalAlign=top;align=left;spacingLeft=30;fontColor={color};dashed={dashed};"
)
BOX = (
    "rounded=1;whiteSpace=wrap;html=1;arcSize={arc};fillColor={fill};strokeColor={stroke};"
    "fontSize=12;align={align};verticalAlign={valign};spacing=10;"
)
EDGE = (
    "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;strokeWidth=2;"
    "strokeColor={color};fontColor={color};fontSize=11;labelBackgroundColor=#ffffff;"
    "dashed={dashed};{extra}"
)
DIAMOND = (
    "rhombus;whiteSpace=wrap;html=1;fillColor=#FFF2CC;strokeColor=#D6B656;fontSize=12;fontStyle=1;"
)


def label(name: str, detail: str = "", cost: str = "") -> str:
    parts = [f"<b>{name}</b>"]
    if detail:
        parts.append(f'<span style="font-size:11px;color:#666;">{detail}</span>')
    if cost:
        parts.append(f'<span style="font-size:11px;color:{GREEN};">{cost}</span>')
    return "<br>".join(parts)


class Page:
    def __init__(self, name: str, title: str, subtitle: str):
        self.name, self.cells, self.n = name, [], 0
        self.text(
            40,
            20,
            1200,
            50,
            f'<b style="font-size:20px;">{title}</b><br>'
            f'<span style="font-size:12px;color:#666;">{subtitle}</span>',
        )

    def _id(self) -> str:
        self.n += 1
        return f"{self.name}-{self.n}"

    def vertex(self, value: str, style: str, x, y, w, h) -> str:
        cid = self._id()
        self.cells.append(
            f'<mxCell id="{cid}" value={quoteattr(value)} style={quoteattr(style)} vertex="1" '
            f'parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>'
            "</mxCell>"
        )
        return cid

    def text(self, x, y, w, h, value: str, align: str = "left") -> str:
        style = f"text;html=1;align={align};verticalAlign=top;whiteSpace=wrap;fontSize=12;"
        return self.vertex(value, style, x, y, w, h)

    def icon(self, x, y, res, color, value, size=78) -> str:
        return self.vertex(value, ICON.format(color=color, res=res), x, y, size, size)

    def group(self, x, y, w, h, value, icon, color, dashed=0) -> str:
        return self.vertex(value, GROUP.format(icon=icon, color=color, dashed=dashed), x, y, w, h)

    def box(
        self,
        x,
        y,
        w,
        h,
        value,
        fill="#ffffff",
        stroke="#666666",
        align="center",
        valign="middle",
        arc=8,
    ) -> str:
        style = BOX.format(fill=fill, stroke=stroke, align=align, valign=valign, arc=arc)
        return self.vertex(value, style, x, y, w, h)

    def diamond(self, x, y, value, w=170, h=110) -> str:
        return self.vertex(value, DIAMOND, x, y, w, h)

    def edge(
        self,
        src,
        tgt,
        value="",
        color=BLUE,
        dashed=0,
        exit=None,
        entry=None,
        points=(),
        label_offset=None,
    ) -> None:
        extra = ""
        if exit:
            extra += f"exitX={exit[0]};exitY={exit[1]};exitDx=0;exitDy=0;"
        if entry:
            extra += f"entryX={entry[0]};entryY={entry[1]};entryDx=0;entryDy=0;"
        style = EDGE.format(color=color, dashed=dashed, extra=extra)
        pts = "".join(f'<mxPoint x="{px}" y="{py}"/>' for px, py in points)
        geo = '<mxGeometry relative="1" as="geometry">'
        if pts:
            geo += f'<Array as="points">{pts}</Array>'
        if label_offset:
            geo += f'<mxPoint x="{label_offset[0]}" y="{label_offset[1]}" as="offset"/>'
        geo += "</mxGeometry>"
        self.cells.append(
            f'<mxCell id="{self._id()}" value={quoteattr(value)} style={quoteattr(style)} '
            f'edge="1" parent="1" source="{src}" target="{tgt}">{geo}</mxCell>'
        )

    def xml(self) -> str:
        return (
            f'<diagram id="{self.name}" name="{self.name}"><mxGraphModel dx="1900" dy="1200" '
            'grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" '
            'page="1" pageScale="1" pageWidth="1900" pageHeight="1200" math="0" shadow="0">'
            '<root><mxCell id="0"/><mxCell id="1" parent="0"/>'
            + "".join(self.cells)
            + "</root></mxGraphModel></diagram>"
        )


def architecture() -> Page:
    p = Page(
        "Architecture",
        "cost-sentinel: weekly AWS waste report",
        "EventBridge Scheduler · Lambda (Python 3.12) · EC2 / EBS / ELB / Tagging APIs · "
        "SES · Slack · SSM Parameter Store · CloudWatch · SQS",
    )
    fx, fy, fw, fh = 400, 170, 300, 380  # Lambda box

    def fn_x(x):
        return (x - fx) / fw

    def fn_y(y):
        return (y - fy) / fh

    ssm = p.icon(
        100,
        150,
        "systems_manager",
        MANAGEMENT,
        label("SSM Parameter Store", "Slack webhook (SecureString)", "$0 · standard tier"),
    )
    sched = p.icon(
        100,
        340,
        "eventbridge",
        MANAGEMENT,
        label("EventBridge Scheduler", "cron(0 8 ? * MON *)", "$0 · 14M free/month"),
    )

    fn = p.box(fx, fy, fw, fh, "", fill="#FFF7ED", stroke=COMPUTE, arc=3)
    p.icon(fx + 20, fy + 20, "lambda", COMPUTE, "", size=64)
    p.text(
        fx + 95,
        fy + 22,
        200,
        70,
        label("cost-sentinel Lambda", "Python 3.12 · arm64 · 256 MB", "~$0 · free tier"),
    )
    p.text(
        fx + 20,
        fy + 105,
        280,
        270,
        "<b>Per region, read-only</b><br>"
        '<span style="font-family:monospace;font-size:11px;">'
        "unattached_volume<br>unassociated_eip<br>old_snapshot<br>stopped_instance<br>"
        "old_ami (opt-in)<br>idle_load_balancer<br>missing_tags</span><br><br>"
        "<b>Then</b><br>"
        "1. drop cost-sentinel:ignore=true<br>"
        "2. remediate (opt-in, dry-run default)<br>"
        "3. totals by check / region, top N<br>"
        "4. email + Slack, full list to logs",
    )

    ax, ay, aw, ah = 880, 110, 980, 530
    acct = p.group(
        ax, ay, aw, ah, "AWS account: every region in REGIONS", "group_account", "#CD2264"
    )
    for name, y in (("us-east-1", 160), ("eu-west-1", 400)):
        p.group(910, y, 920, 200, name, "group_region", "#00A4A6", dashed=1)
        p.icon(
            980, y + 50, "elastic_block_store", STORAGE, label("Amazon EBS", "volumes · snapshots")
        )
        p.icon(1200, y + 50, "ec2", COMPUTE, label("Amazon EC2", "instances · EIPs · AMIs"))
        p.icon(
            1420,
            y + 50,
            "elastic_load_balancing",
            NETWORK,
            label("Elastic Load Balancing", "ALB / NLB · target health"),
        )
        p.icon(
            1640,
            y + 50,
            "resource_explorer",
            MANAGEMENT,
            label("Resource Groups Tagging API", "GetResources"),
        )

    p.edge(sched, fn, "weekly · async invoke", exit=(1, 0.5), entry=(0, fn_y(379)))
    p.edge(fn, ssm, "GetParameter", color=GREY, exit=(0, fn_y(189)), entry=(1, 0.5))
    p.edge(fn, acct, "Describe* (read-only)", exit=(1, fn_y(300)), entry=(0, (300 - ay) / ah))
    p.edge(
        fn,
        acct,
        "Delete* (opt-in)",
        color=RED,
        dashed=1,
        exit=(1, fn_y(500)),
        entry=(0, (500 - ay) / ah),
    )

    by = 760  # bottom row
    dlq = p.icon(
        100,
        by,
        "sqs",
        INTEGRATION,
        label("SQS dead-letter queue", "failed runs + deliveries", "$0 · 1M free/month"),
    )
    alarm = p.icon(
        320,
        by,
        "cloudwatch_2",
        MANAGEMENT,
        label("CloudWatch alarm", "DLQ depth &gt; 0", "$0 · 10 free alarms"),
    )
    logs = p.icon(
        500,
        by,
        "cloudwatch_2",
        MANAGEMENT,
        label("CloudWatch Logs", "one JSON line per finding · 30 d", "$0 · 5 GB free"),
    )
    ses = p.icon(
        760,
        by,
        "simple_email_service",
        SECURITY,
        label("Amazon SES", "SendEmail: HTML + text", "~$0.0004 / month"),
    )
    slack = p.box(
        980, by + 10, 170, 60, label("Slack", "POST to incoming webhook"), stroke="#4A154B"
    )

    p.edge(
        sched,
        dlq,
        "failed delivery",
        color=GREY,
        dashed=1,
        exit=(0, 0.5),
        entry=(0, 0.5),
        points=((60, 379), (60, by + 39)),
    )
    p.edge(
        fn,
        dlq,
        "failed run",
        color=GREY,
        dashed=1,
        exit=(0, fn_y(520)),
        entry=(0.5, 0),
        points=((139, 520),),
    )
    p.edge(dlq, alarm, "depth &gt; 0", color=GREY, exit=(1, 0.5), entry=(0, 0.5))
    p.edge(fn, logs, "logs", color=GREY, exit=(fn_x(539), 1), entry=(0.5, 0))
    p.edge(fn, ses, "", exit=(fn_x(660), 1), entry=(0.5, 0), points=((660, 690), (799, 690)))
    p.edge(fn, slack, "", exit=(fn_x(690), 1), entry=(0.5, 0), points=((690, 660), (1065, 660)))

    p.box(
        1220,
        700,
        640,
        150,
        "<b>Safety model</b><br>"
        "• Read role: Describe* + tag:GetResources only, scoped with aws:RequestedRegion<br>"
        "• Remediation policy is separate, attached only when enable_remediation=true<br>"
        "• Explicit IAM Deny on resources tagged cost-sentinel:ignore=true (also in code)<br>"
        "• DRY_RUN=true by default; only the literal 'false' turns it off<br>"
        "• Volumes are snapshotted, and the snapshot completed, before delete<br>"
        "• Slack webhook lives in SSM, never in Terraform state or env vars",
        fill="#f5f5f5",
        stroke="#999999",
        align="left",
        valign="top",
    )
    p.box(
        40,
        940,
        1820,
        90,
        "<b>Running cost ≈ $0.00 / month</b> (us-east-1, 1 weekly run, ~60 s)<br>"
        '<span style="font-size:11px;">Lambda 4 runs × 60 s × 0.25 GB = 60 GB-s '
        "(free: 400,000) · Scheduler 4 invocations (free: 14M) · SES 4 emails × $0.0001 · "
        "Logs &lt; 10 MB (free: 5 GB) · SQS + 1 alarm within free tier · "
        "Describe API calls are free</span>",
        fill="#D5E8D4",
        stroke="#82B366",
        align="center",
    )
    return p


def decision_flow() -> Page:
    p = Page(
        "Decision flow",
        "What happens to one finding",
        "detect · estimate · allowlist · remediation gate · dry-run · snapshot-before-delete · "
        "report",
    )
    r1, r2 = 130, 330  # box rows (diamonds sit 10 px higher)
    proc = dict(fill="#ffffff", stroke=COMPUTE)
    detect = p.box(40, r1, 190, 90, label("Detect", "check(region, cfg)<br>Describe* only"), **proc)
    estimate = p.box(
        280, r1, 190, 90, label("Estimate $/month", "static us-east-1 price table"), **proc
    )
    allow = p.diamond(520, r1 - 10, "Tagged<br>cost-sentinel:<br>ignore=true?")
    enabled = p.diamond(760, r1 - 10, "Check listed<br>in REMEDIATE?")
    dry = p.diamond(1000, r1 - 10, "DRY_RUN?")
    volume = p.diamond(1240, r1 - 10, "EBS volume?")
    snap = p.box(
        1480,
        r1,
        190,
        90,
        label("Snapshot volume", "tag source-volume,<br>wait until completed"),
        fill="#ffffff",
        stroke=STORAGE,
    )
    delete = p.box(
        1700, r1, 160, 90, label("Delete volume", "only after backup"), fill="#ffffff", stroke=RED
    )

    grey = dict(fill="#f5f5f5", stroke=GREY)
    skipped = p.box(
        520, r2, 170, 90, label("Skip", "counted as allowlisted,<br>never touched"), **grey
    )
    report_only = p.box(
        760,
        r2,
        170,
        90,
        label("Report only", "stopped instances, idle LBs,<br>tags are always here"),
        **grey,
    )
    would = p.box(1000, r2, 170, 90, label("Log only", "outcome: would ..."), **grey)
    other = p.box(
        1240,
        r2,
        170,
        90,
        label("Act", "release EIP · delete snapshot<br>· deregister AMI"),
        fill="#ffffff",
        stroke=RED,
    )
    failed = p.box(
        1480,
        r2,
        200,
        90,
        label("On API error", "outcome: failed: ...<br>run continues, shown in report"),
        fill="#FDECEA",
        stroke=RED,
    )

    rw = 1820
    report = p.box(
        40,
        520,
        rw,
        90,
        label(
            "Report",
            "total $/month · by check · by region · top N offenders · "
            "remediation outcomes · checks that failed · allowlisted count",
        ),
        fill="#E3F2FD",
        stroke=BLUE,
    )
    notify = p.icon(
        800, 650, "simple_email_service", SECURITY, label("Notify", "SES email + Slack webhook")
    )

    p.edge(detect, estimate)
    p.edge(estimate, allow)
    p.edge(allow, enabled, "no")
    p.edge(enabled, dry, "yes")
    p.edge(dry, volume, "no (live)")
    p.edge(volume, snap, "yes")
    p.edge(snap, delete, color=RED)
    p.edge(allow, skipped, "yes", color=GREY)
    p.edge(enabled, report_only, "no", color=GREY)
    p.edge(dry, would, "yes (default)", color=GREY)
    p.edge(volume, other, "no", color=RED)
    p.edge(
        delete,
        failed,
        "error",
        color=RED,
        dashed=1,
        exit=(0.5, 1),
        entry=(0.5, 0),
        points=((1780, 275), (1580, 275)),
    )
    for src, cx in (
        (skipped, 605),
        (report_only, 845),
        (would, 1085),
        (other, 1325),
        (failed, 1580),
    ):
        p.edge(
            src,
            report,
            color=GREY,
            dashed=int(src == failed),
            exit=(0.5, 1),
            entry=((cx - 40) / rw, 0),
        )
    p.edge(
        delete,
        report,
        color=GREY,
        exit=(1, 0.5),
        entry=(1, 0.5),
        points=((1890, r1 + 45), (1890, 565)),
    )
    p.edge(report, notify, exit=((839 - 40) / rw, 1), entry=(0.5, 0))

    p.box(
        40,
        800,
        900,
        150,
        "<b>Why this order</b><br>"
        "• The allowlist is checked before anything else, and IAM denies the same tag again.<br>"
        "• Remediation needs three independent switches: the IAM policy (enable_remediation),<br>"
        "&nbsp;&nbsp;the check in REMEDIATE, and DRY_RUN=false.<br>"
        "• Deleting a volume waits for its snapshot; the snapshot ages out via old_snapshot.<br>"
        "• One failed resource or check never hides the rest of the report.",
        fill="#f5f5f5",
        stroke="#999999",
        align="left",
        valign="top",
    )
    p.box(
        980,
        800,
        880,
        150,
        "<b>Estimates (approximate, us-east-1)</b><br>"
        "EBS gp3 $0.08 / gp2 $0.10 / io1-io2 $0.125 per GB-month · snapshot $0.05 per GB-month "
        "(upper bound, incremental) · idle EIP $0.005/h = $3.65 · ALB/NLB $0.0225/h = $16.43 · "
        "missing tags $0 (governance, not waste)",
        fill="#D5E8D4",
        stroke="#82B366",
        align="left",
        valign="top",
    )
    return p


def main() -> None:
    pages = [architecture(), decision_flow()]
    OUT.write_text(
        '<mxfile host="gen_drawio.py">' + "".join(pg.xml() for pg in pages) + "</mxfile>\n",
        encoding="utf-8",
    )
    print(OUT)


if __name__ == "__main__":
    main()
