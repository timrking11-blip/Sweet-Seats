"""SS-RESEARCH-0.3 offline tests: mocked Claude responses only, no network, no authentication claims."""
import asyncio
import copy
import json
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest

from adapters import claude_research as claude
from jobs.research_contracts import FOOTER, MARKER, ContractError, digest, timestamp
from jobs.research_pipeline import ApprovalStore, BudgetLedger, execute, replay, write_review_export


class ClaudePipelineTests(unittest.TestCase):
    def setUp(self):
        self.f = json.loads(Path('tests/fixtures/research/claude-v0.3.json').read_text(encoding='utf-8'))
        self.policy, self.profile, self.request = self.f['policy'], self.f['profile'], self.f['request']
        self.now = timestamp(self.f['now'])
        self.store = ApprovalStore(set(self.policy['trusted_actors']))
        for approval in self.f['approvals']:
            self.store.record(approval['actor_id'], approval['digest'], approval['expires_at'])
        self.ledger = BudgetLedger(self.policy['hourly_budget_cents'], self.policy['daily_budget_cents'])
        self.completed = set()

    def run_pipeline(self, request=None, profile=None, responses=None):
        return execute(request or self.request, profile or self.profile, self.store, self.ledger, self.policy,
                       self.completed, replay(responses or self.f['mock_responses']), self.now)

    def test_synthetic_request_to_saved_review_export(self):
        report = self.run_pipeline()
        self.assertEqual(report['review_status'], 'pending_human_review')
        self.assertTrue(all(c['verified'] is False for c in report['claims']))
        self.assertTrue(all(e['rights_context'] == 'unverified' for e in report['evidence']))
        self.assertEqual(report['provider']['stop_reasons'], ['pause_turn', 'end_turn'])
        self.assertEqual(report['cost']['actual_cents'], 18)
        self.assertEqual(report['cost']['reserved_cents'], claude.ceiling_cents(self.profile))
        with tempfile.TemporaryDirectory() as out:
            json_path, md_path = write_review_export(report, Path(out))
            self.assertEqual(json.loads(json_path.read_text(encoding='utf-8'))['report_id'], report['report_id'])
            body = md_path.read_text(encoding='utf-8')
            self.assertTrue(body.startswith(MARKER) and body.endswith(FOOTER))

    def test_evidence_comes_from_tool_results_with_citation_passages(self):
        report = self.run_pipeline()
        origins = {e['url']: e['origin'] for e in report['evidence']}
        self.assertEqual(origins['https://example.com/provider-a/terms'], 'web_fetch')
        cited = next(e for e in report['evidence'] if e['url'] == 'https://example.com/provider-a')
        self.assertEqual(cited['passages'], ['SYNTHETIC: offers are listed per seat.'])

    def test_claim_citing_unretrieved_url_rejected(self):
        responses = copy.deepcopy(self.f['mock_responses'])
        final = json.loads(responses[-1]['content'][-1]['text'])
        final['claims'][0]['source_urls'] = ['https://attacker.example/asserted']
        responses[-1]['content'][-1]['text'] = json.dumps(final)
        with self.assertRaisesRegex(ContractError, 'not retrieved'):
            self.run_pipeline(responses=responses)

    def test_profile_change_invalidates_approval(self):
        for field, value in [('model', 'claude-sonnet-5-5'), ('prompt_version', 'other'),
                             ('max_continuations', 3)]:
            with self.assertRaises(ContractError):
                self.run_pipeline(profile=dict(self.profile, **{field: value}))
        # Even a registered new profile needs a new approval: the request digest changes.
        changed = copy.deepcopy(self.profile)
        changed['tools'][0]['max_uses'] = 4
        new_digest = claude.validate_profile(changed)
        self.policy['approved_profiles'].append(new_digest)
        request = dict(self.request, execution_profile_digest=new_digest)
        with self.assertRaisesRegex(ContractError, 'no execution approval'):
            self.run_pipeline(request=request, profile=changed)

    def test_research_role_has_only_web_tools_and_no_sdk_retries(self):
        bad_tools = [{'type': 'bash_20250124', 'name': 'bash', 'max_uses': 1},
                     {'type': 'web_search_20260209', 'name': 'approve_findings', 'max_uses': 1}]
        for tool in bad_tools:
            profile = copy.deepcopy(self.profile)
            profile['tools'].append(tool)
            with self.assertRaises(ContractError):
                claude.validate_profile(profile)
        no_citations = copy.deepcopy(self.profile)
        no_citations['tools'][1]['citations'] = {'enabled': False}
        for profile in (dict(self.profile, sdk_max_retries=2), no_citations,
                        dict(self.profile, provider='perplexity')):
            with self.assertRaises(ContractError):
                claude.validate_profile(profile)

    def test_client_tool_call_or_unapproved_server_tool_rejected(self):
        for block in ({'type': 'tool_use', 'id': 't', 'name': 'merge_pr', 'input': {}},
                      {'type': 'server_tool_use', 'id': 's', 'name': 'code_execution', 'input': {}}):
            responses = copy.deepcopy(self.f['mock_responses'])
            responses[0]['content'].append(block)
            with self.assertRaises(ContractError):
                self.setUp()
                self.run_pipeline(responses=responses)

    def test_approval_is_single_use_and_completed_request_not_repeated(self):
        self.run_pipeline()
        with self.assertRaises(ContractError):
            self.run_pipeline()

    def test_untrusted_actor_cannot_record_approval(self):
        with self.assertRaises(ContractError):
            self.store.record('claude-research-role', digest(self.request), self.f['approvals'][0]['expires_at'])

    def test_budget_below_worst_case_denied(self):
        request = dict(self.request, budget_cents=claude.ceiling_cents(self.profile) - 1)
        self.store.record('demo-owner', digest(request), self.f['approvals'][0]['expires_at'])
        with self.assertRaisesRegex(ContractError, 'worst case'):
            self.run_pipeline(request=request)
        self.assertEqual(self.ledger.entries, {})

    def test_aggregate_hourly_cap_enforced(self):
        self.ledger.hourly = claude.ceiling_cents(self.profile) - 1
        with self.assertRaisesRegex(ContractError, 'aggregate'):
            self.run_pipeline()

    def test_ambiguous_dispatch_leaves_unresolved_charge(self):
        def lost(params):
            raise TimeoutError('response lost after dispatch')
        with self.assertRaisesRegex(ContractError, 'ambiguous'):
            execute(self.request, self.profile, self.store, self.ledger, self.policy, self.completed, lost, self.now)
        key = next(iter(self.ledger.entries))
        self.assertEqual(self.ledger.entries[key]['status'], 'unresolved')
        with self.assertRaisesRegex(ContractError, 'reconcile'):
            self.ledger.reserve(key, 1, self.now)

    def test_ledger_retry_reuses_reservation_and_settled_window_expires(self):
        first = self.ledger.reserve('k', 100, self.now)
        self.assertIs(self.ledger.reserve('k', 100, self.now), first)
        self.ledger.settle('k', 120)
        self.assertTrue(first['overrun'])
        self.ledger.reserve('other', 400, self.now + timedelta(hours=2))

    def test_continuation_and_stop_reason_limits(self):
        paused = copy.deepcopy(self.f['mock_responses'])
        paused[-1]['stop_reason'] = 'pause_turn'
        refusal = copy.deepcopy(self.f['mock_responses'])
        refusal[-1]['stop_reason'] = 'refusal'
        for responses in (paused, refusal):
            with self.assertRaises(ContractError):
                self.setUp()
                self.run_pipeline(responses=responses)

    def test_tool_errors_recorded_not_used_as_evidence(self):
        responses = copy.deepcopy(self.f['mock_responses'])
        responses[0]['content'][1]['content'] = {'type': 'web_search_tool_result_error', 'error_code': 'max_uses_exceeded'}
        final = json.loads(responses[-1]['content'][-1]['text'])
        final['claims'] = [c for c in final['claims'] if not set(c['source_urls']) & {
            'https://example.com/provider-a', 'https://example.org/provider-b'}]
        responses[-1]['content'][-1]['text'] = json.dumps(final)
        report = self.run_pipeline(responses=responses)
        self.assertEqual(report['tool_errors'], [{'tool': 'web_search', 'error_code': 'max_uses_exceeded'}])
        self.assertEqual([e['origin'] for e in report['evidence']], ['web_fetch'])
        self.assertEqual(report['unmapped_citations'], 1)

    def test_schema_validation_beyond_linkage(self):
        report = self.run_pipeline()
        for mutate in (lambda r: r['claims'][3].update(confidence='high'),
                       lambda r: r['claims'][0].update(confidence='certain'),
                       lambda r: r['evidence'][0].update(rights_context='permitted'),
                       lambda r: r.update(executive_summary=''),
                       lambda r: r.update(next_actions='call vendor'),
                       lambda r: r['claims'][0].update(verified=True),
                       lambda r: r.update(review_status='approved')):
            altered = copy.deepcopy(report)
            mutate(altered)
            with self.assertRaises(ContractError):
                claude.validate_report_schema(altered)

    def test_request_params_declare_web_tools_and_live_execution_disabled(self):
        params = claude.build_request_params(self.profile, self.request['brief'])
        self.assertEqual([t['type'] for t in params['tools']], ['web_search_20260209', 'web_fetch_20260209'])
        self.assertEqual(params['tools'][1]['citations'], {'enabled': True})
        self.assertNotIn('thinking', params)
        with self.assertRaises(RuntimeError):
            asyncio.run(claude.run_research(params))


if __name__ == '__main__':
    unittest.main()
