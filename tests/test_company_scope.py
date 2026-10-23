"""Company scoping must survive direct RPCs and caller context overrides."""
import asyncio
import json
from types import SimpleNamespace

import odoorpc
import pytest

from odoo_mcp.connection import CompanyOdoo
from odoo_mcp.remote import RemoteOdoo
from odoo_mcp.manufacturing import ManufacturingHandler


@pytest.mark.parametrize('connection_type', [CompanyOdoo, RemoteOdoo])
@pytest.mark.parametrize('method', ['search', 'read', 'create', 'write', 'formatted_read_group'])
def test_every_rpc_pins_company(monkeypatch, connection_type, method):
    calls = []
    def execute(self, model, method, args, kwargs):
        calls.append(kwargs)
        return []
    monkeypatch.setattr(odoorpc.ODOO, 'execute_kw', execute)
    connection = object.__new__(connection_type)
    caller = {'context': {'allowed_company_ids': [1, 2], 'company_id': 2,
                           'force_company': 2, 'active_test': False}}
    connection.execute_kw('example.model', method, [[]], caller)
    assert calls[0]['context'] == {'allowed_company_ids': [1], 'company_id': 1,
                                  'force_company': 1, 'active_test': False}
    assert caller['context']['company_id'] == 2
    connection.execute('example.model', method, [])
    assert calls[1]['context']['allowed_company_ids'] == [1]


@pytest.mark.parametrize('include_archived', [False, True])
def test_locations_separate_companies_with_duplicate_names(include_archived):
    records = [
        {'id': 24, 'complete_name': 'Storage', 'active': False, 'usage': 'internal',
         'company_id': [1, 'Company One']},
        {'id': 50, 'complete_name': 'Storage', 'active': True, 'usage': 'internal',
         'company_id': [2, 'Company Two']},
    ]
    def search(domain, order):
        assert ('company_id', '=', 1) in domain
        archived = ('active', 'in', [True, False]) in domain
        return [r['id'] for r in records if r['company_id'][0] == 1 and (archived or r['active'])]
    handler = ManufacturingHandler()
    handler.odoo = SimpleNamespace(company_id=1, env={
        'stock.location': SimpleNamespace(search=search)})
    handler.safe_read_records = lambda model, ids, fields: [r for r in records if r['id'] in ids]
    result = asyncio.run(handler.list_locations({'include_archived': include_archived}))[0].text
    rows = json.loads(result.split('```json\n')[1].split('```')[0])
    assert [r['id'] for r in rows] == ([24] if include_archived else [])
    if rows:
        assert rows[0]['company_id'] == 1
        assert rows[0]['company_name'] == 'Company One'
        assert rows[0]['active'] is False
