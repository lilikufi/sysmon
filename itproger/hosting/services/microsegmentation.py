from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db.models import Q

from hosting.models import NetworkSegment, Route, SegmentPolicy


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    policy: SegmentPolicy | None = None


@dataclass(frozen=True)
class SegmentationViolation:
    route: Route
    reason: str
    policy: SegmentPolicy | None = None


def validate_traffic(protocol=SegmentPolicy.Protocol.ANY, port=None):
    """Normalize and validate the traffic selector used by the policy engine."""
    protocol = (protocol or SegmentPolicy.Protocol.ANY).lower()
    if protocol not in SegmentPolicy.Protocol.values:
        raise ValidationError({'protocol': f'Unsupported protocol: {protocol}'})
    if port is not None:
        if protocol not in (SegmentPolicy.Protocol.TCP, SegmentPolicy.Protocol.UDP):
            raise ValidationError({'port': 'Ports are only valid for TCP or UDP traffic.'})
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise ValidationError({'port': 'Port must be between 1 and 65535.'})
    return protocol, port


def evaluate_segments(source, destination, protocol=SegmentPolicy.Protocol.ANY, port=None):
    """Evaluate connectivity using deterministic first-match policy semantics."""
    protocol, port = validate_traffic(protocol, port)
    if source is None or destination is None:
        return PolicyDecision(False, 'Host has no assigned network segment')
    if source.pk == destination.pk:
        return PolicyDecision(True, 'Hosts belong to the same segment')

    protocol_filter = Q(protocol=SegmentPolicy.Protocol.ANY)
    if protocol != SegmentPolicy.Protocol.ANY:
        protocol_filter |= Q(protocol=protocol)

    port_filter = Q(port__isnull=True)
    if port is not None:
        port_filter |= Q(port=port)

    policy = (
        SegmentPolicy.objects.filter(source=source, destination=destination, enabled=True)
        .filter(protocol_filter, port_filter)
        .order_by('priority', 'pk')
        .first()
    )
    if policy is not None:
        return PolicyDecision(
            policy.action == SegmentPolicy.Action.ALLOW,
            f'Policy {policy.name!r} returned {policy.action}',
            policy,
        )

    allowed = source.default_action == NetworkSegment.DefaultAction.ALLOW
    return PolicyDecision(allowed, f'Source segment default is {source.default_action}')


def find_route_violations(
    routes=None,
    protocol=SegmentPolicy.Protocol.ANY,
    port=None,
):
    """Return topology routes forbidden by current segmentation policy."""
    if routes is None:
        routes = Route.objects.select_related(
            'parent__segment',
            'child__segment',
        )

    violations = []
    for route in routes:
        decision = evaluate_segments(
            route.parent.segment,
            route.child.segment,
            protocol=protocol,
            port=port,
        )
        if not decision.allowed:
            violations.append(
                SegmentationViolation(route, decision.reason, decision.policy)
            )
    return violations
