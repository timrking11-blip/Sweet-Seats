"""Offline contract tests. No live integration, authentication or DB claims."""
import asyncio
import copy
import json
from pathlib import Path
import unittest

from adapters.linear import LinearClient
from adapters.perplexity_research import run_research
from jobs.linear_research import process_job, sweep
from jobs.research_contracts import (ContractError, FOOTER, MARKER, digest, publication_digest,
                                     select_hourly, timestamp, validate_approval, validate_report,
                                     validate_request)
from services.api.linear_webhook import linear_webhook


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.f = json.loads(Path('tests/fixtures/research/hourly.json').read_text())
        self.r = self.f['candidates'][0]['request']
        self.a = self.f['approvals'][digest(self.r)]
        self.p = self.f['policy']
        self.now = timestamp(self.f['now'])

    def test_approved_request_and_report(self):
        self.assertTrue(validate_request(self.r, self.a, self.p, self.now))
        validate_report(self.f['report'], self.r)

    def test_no_approval_or_label_is_not_authority(self):
        self.assertEqual(select_hourly(self.f['candidates'], {}, set(), self.p, self.now), [])

    def test_brief_or_budget_change_invalidates_approval(self):
        for field, value in [('brief', 'Changed'), ('budget_cents', 2)]:
            altered = dict(self.r, **{field: value})
            with self.assertRaises(ContractError):
                validate_request(altered, self.a, self.p, self.now)

    def test_scope_and_classification_denied(self):
        for field, value in [('team_id', 'other'), ('project_id', 'other'),
                             ('classification', 'private'), ('allowed_use', 'train'), ('mode', 'deep')]:
            altered = dict(self.r, **{field: value})
            with self.assertRaises(ContractError):
                validate_request(altered, self.a, self.p, self.now)

    def test_untrusted_approver_denied(self):
        with self.assertRaises(ContractError):
            validate_request(self.r, dict(self.a, actor_id='stranger'), self.p, self.now)

    def test_expired_approval_and_request_denied(self):
        with self.assertRaises(ContractError):
            validate_request(self.r, dict(self.a, expires_at='2026-01-01T00:00:00Z'), self.p, self.now)
        with self.assertRaises(ContractError):
            validate_request(dict(self.r, expires_at='2026-01-01T00:00:00Z'), self.a, self.p, self.now)

    def test_hourly_repeat_does_not_repeat_completed_request(self):
        plan = select_hourly(self.f['candidates'], self.f['approvals'], set(), self.p, self.now)
        self.assertEqual(len(plan), 1)
        self.assertEqual(select_hourly(self.f['candidates'], self.f['approvals'],
                                      {plan[0]['key']}, self.p, self.now), [])

    def test_new_revision_requires_new_approval_and_allows_rerun(self):
        old_key = validate_request(self.r, self.a, self.p, self.now)
        new = dict(self.r, revision=2)
        candidate = [{'label': 'research-quick', 'request': new}]
        self.assertEqual(select_hourly(candidate, self.f['approvals'], {old_key}, self.p, self.now), [])
        approvals = {digest(new): dict(self.a, digest=digest(new))}
        self.assertEqual(len(select_hourly(candidate, approvals, {old_key}, self.p, self.now)), 1)

    def test_exact_publication_target_and_body(self):
        body = MARKER + '\nSynthetic reviewed report\n' + FOOTER
        target = {'workspace_id': 'demo-workspace', 'issue_id': 'demo-issue'}
        bound = publication_digest(target, body)
        approval = dict(self.a, digest=bound)
        validate_approval(approval, bound, set(self.p['trusted_actors']), self.now)
        for changed in [publication_digest(dict(target, issue_id='other'), body),
                        publication_digest(target, body.replace('Synthetic', 'Modified'))]:
            with self.assertRaises(ContractError):
                validate_approval(approval, changed, set(self.p['trusted_actors']), self.now)

    def test_report_requires_evidence_lineage(self):
        report = copy.deepcopy(self.f['report'])
        report['claims'][0]['evidence_ids'] = ['missing']
        with self.assertRaises(ContractError):
            validate_report(report, self.r)
        report = dict(self.f['report'], allowed_use='features')
        with self.assertRaises(ContractError):
            validate_report(report, self.r)

    def test_naive_timestamps_and_boolean_budget_rejected(self):
        with self.assertRaises(ContractError):
            timestamp('2026-10-15T12:00:00')
        with self.assertRaises(ContractError):
            validate_request(dict(self.r, budget_cents=True), self.a, self.p, self.now)

    def test_all_legacy_network_paths_disabled(self):
        client = LinearClient()
        for call in [lambda: run_research('brief', 'low'), lambda: process_job(None, None),
                     lambda: sweep(None, None), lambda: linear_webhook(None),
                     lambda: client.add_comment('issue', 'text'), lambda: client.get_issue('issue'),
                     lambda: client.graphql('query'), lambda: client.open_issues_with_label('research-quick')]:
            with self.assertRaises(RuntimeError):
                asyncio.run(call())


if __name__ == '__main__':
    unittest.main()
