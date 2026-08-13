from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase

from hosting.models import Host, NetworkSegment, Route, SegmentPolicy
from hosting.services.microsegmentation import evaluate_segments, find_route_violations


class MicrosegmentationTests(TestCase):
    def setUp(self):
        self.users = NetworkSegment.objects.create(
            name='Users',
            default_action=NetworkSegment.DefaultAction.DENY,
        )
        self.servers = NetworkSegment.objects.create(
            name='Servers',
            default_action=NetworkSegment.DefaultAction.DENY,
        )
        self.user_host = Host.objects.create(
            ipaddr='192.0.2.10',
            hostname='user-host',
            segment=self.users,
        )
        self.server_host = Host.objects.create(
            ipaddr='192.0.2.20',
            hostname='server-host',
            segment=self.servers,
        )
        self.route = Route.objects.create(
            parent=self.user_host,
            child=self.server_host,
        )

    def test_default_deny_marks_route_as_violation(self):
        violations = find_route_violations()

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].route, self.route)
        self.assertIn('default is deny', violations[0].reason)

    def test_explicit_allow_policy_permits_route(self):
        SegmentPolicy.objects.create(
            name='Users to servers',
            source=self.users,
            destination=self.servers,
            action=SegmentPolicy.Action.ALLOW,
        )

        self.assertEqual(find_route_violations(), [])

    def test_first_policy_by_priority_wins(self):
        SegmentPolicy.objects.create(
            name='Broad allow',
            source=self.users,
            destination=self.servers,
            action=SegmentPolicy.Action.ALLOW,
            priority=200,
        )
        deny = SegmentPolicy.objects.create(
            name='Emergency deny',
            source=self.users,
            destination=self.servers,
            action=SegmentPolicy.Action.DENY,
            priority=10,
        )

        decision = evaluate_segments(self.users, self.servers)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.policy, deny)

    def test_same_segment_is_allowed(self):
        decision = evaluate_segments(self.users, self.users)

        self.assertTrue(decision.allowed)

    def test_host_without_segment_is_reported(self):
        self.server_host.segment = None
        self.server_host.save(update_fields=['segment'])

        violations = find_route_violations()

        self.assertEqual(len(violations), 1)
        self.assertIn('no assigned network segment', violations[0].reason)

    def test_policy_rejects_invalid_port(self):
        policy = SegmentPolicy(
            name='Invalid port',
            source=self.users,
            destination=self.servers,
            action=SegmentPolicy.Action.ALLOW,
            port=70000,
        )

        with self.assertRaises(ValidationError):
            policy.full_clean()

    def test_icmp_policy_rejects_port(self):
        policy = SegmentPolicy(
            name='Invalid ICMP port',
            source=self.users,
            destination=self.servers,
            action=SegmentPolicy.Action.ALLOW,
            protocol=SegmentPolicy.Protocol.ICMP,
            port=8,
        )

        with self.assertRaises(ValidationError):
            policy.full_clean()

    def test_tcp_port_policy_matches_requested_traffic(self):
        allow_https = SegmentPolicy.objects.create(
            name='Allow HTTPS',
            source=self.users,
            destination=self.servers,
            action=SegmentPolicy.Action.ALLOW,
            protocol=SegmentPolicy.Protocol.TCP,
            port=443,
            priority=10,
        )

        allowed = evaluate_segments(self.users, self.servers, protocol='tcp', port=443)
        denied = evaluate_segments(self.users, self.servers, protocol='tcp', port=80)

        self.assertTrue(allowed.allowed)
        self.assertEqual(allowed.policy, allow_https)
        self.assertFalse(denied.allowed)

    def test_any_policy_matches_specific_traffic(self):
        SegmentPolicy.objects.create(
            name='Broad allow',
            source=self.users,
            destination=self.servers,
            action=SegmentPolicy.Action.ALLOW,
            protocol=SegmentPolicy.Protocol.ANY,
        )

        decision = evaluate_segments(self.users, self.servers, protocol='udp', port=53)

        self.assertTrue(decision.allowed)

    def test_generic_audit_does_not_assume_a_specific_port(self):
        SegmentPolicy.objects.create(
            name='Allow HTTPS only',
            source=self.users,
            destination=self.servers,
            action=SegmentPolicy.Action.ALLOW,
            protocol=SegmentPolicy.Protocol.TCP,
            port=443,
        )

        self.assertEqual(len(find_route_violations()), 1)

    def test_duplicate_priority_for_segment_pair_is_rejected(self):
        SegmentPolicy.objects.create(
            name='First',
            source=self.users,
            destination=self.servers,
            action=SegmentPolicy.Action.ALLOW,
            priority=10,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            SegmentPolicy.objects.create(
                name='Second',
                source=self.users,
                destination=self.servers,
                action=SegmentPolicy.Action.DENY,
                priority=10,
            )

    def test_audit_command_accepts_traffic_context(self):
        SegmentPolicy.objects.create(
            name='Allow HTTPS',
            source=self.users,
            destination=self.servers,
            action=SegmentPolicy.Action.ALLOW,
            protocol=SegmentPolicy.Protocol.TCP,
            port=443,
        )
        output = StringIO()

        call_command('audit_segments', protocol='tcp', port=443, stdout=output)

        self.assertIn('No segmentation violations found', output.getvalue())

    def test_audit_command_rejects_port_for_icmp(self):
        with self.assertRaises(CommandError):
            call_command('audit_segments', protocol='icmp', port=8)
