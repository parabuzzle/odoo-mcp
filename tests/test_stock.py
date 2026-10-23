"""Stock aggregation compatibility across public Odoo RPC APIs."""
import asyncio
import json
from types import SimpleNamespace

import odoorpc
import pytest

from odoo_mcp.manufacturing import ManufacturingHandler
from odoo_mcp.remote import RemoteOdoo, RemoteLimitError, MAX_RECORDS


class Quant:
    def __init__(self, legacy=False, error=None):
        self.legacy, self.error = legacy, error
        self.legacy_calls = 0

    def formatted_read_group(self, domain, *, groupby, aggregates):
        assert ('company_id', '=', 1) in domain
        assert ('location_id.usage', '=', 'internal') in domain
        assert ('location_id', 'in', [4]) in domain
        if self.legacy:
            raise odoorpc.error.RPCError("The method 'stock.quant.formatted_read_group' does not exist")
        if self.error:
            raise self.error
        return [{'product_id': [1, 'Controller'], 'location_id': [4, 'Stock'],
                 'quantity:sum': -2.5, 'value:sum': -30.0}]

    def read_group(self, domain, fields, groupby, lazy):
        self.legacy_calls += 1
        assert self.legacy and lazy is False
        return [{'product_id': [1, 'Controller'], 'location_id': [4, 'Stock'],
                 'quantity': -2.5, 'value': -30.0}]


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('group_by', ['product', 'product_location'])
def test_stock_public_aggregation_apis(legacy, group_by):
    quant = Quant(legacy)
    product = SimpleNamespace(read=lambda ids, fields: [{'id': 1, 'default_code': 'CTRL'}])
    handler = ManufacturingHandler()
    handler.odoo = SimpleNamespace(company_id=1, env={'stock.quant': quant, 'product.product': product,
                                        'stock.location': object()})
    handler.safe_read_records = lambda *args: [{'id': 4, 'complete_name': 'Warehouse/Stock'}]
    result = asyncio.run(handler.get_stock({'product_ids': [1], 'group_by': group_by,
                                          'include_location_ids': [4]}))
    rows = json.loads(result[0].text.split('```json\n')[1].split('```')[0])
    assert rows[0]['quantity'] == -2.5
    assert rows[0]['value'] == -30.0
    assert rows[0]['default_code'] == 'CTRL'
    if group_by == 'product_location':
        assert rows[0]['location_name'] == 'Warehouse/Stock'
    assert quant.legacy_calls == int(legacy)


def test_stock_access_error_does_not_retry_legacy_api():
    quant = Quant(error=odoorpc.error.RPCError('Access denied'))
    handler = ManufacturingHandler()
    handler.odoo = SimpleNamespace(company_id=1, env={'stock.quant': quant})
    result = asyncio.run(handler.get_stock({'product_ids': [1], 'include_location_ids': [4]}))
    assert result[0].text.startswith('Error')
    assert quant.legacy_calls == 0


@pytest.mark.parametrize('positional', [False, True])
def test_formatted_aggregation_remote_bound(monkeypatch, positional):
    def execute(self, model, method, args, kwargs):
        limit = args[5] if positional else kwargs['limit']
        assert limit == MAX_RECORDS + 1
        return [{}] * limit
    monkeypatch.setattr(odoorpc.ODOO, 'execute_kw', execute)
    remote = object.__new__(RemoteOdoo)
    args = [[], ['product_id'], ['quantity:sum']]
    if positional:
        args.extend([[], 0, None])
    with pytest.raises(RemoteLimitError):
        remote.execute_kw('stock.quant', 'formatted_read_group', args)


def test_stock_value_fallback_is_labelled_estimate():
    class QuantityOnly:
        def formatted_read_group(self, domain, *, groupby, aggregates):
            if 'value:sum' in aggregates:
                raise odoorpc.error.RPCError('Cannot aggregate value')
            return [{'product_id': [1, 'Controller'], 'quantity:sum': 2.0}]
    product = SimpleNamespace(read=lambda ids, fields: [
        {'id': 1, 'default_code': 'CTRL', 'standard_price': 3.0}])
    handler = ManufacturingHandler()
    handler.odoo = SimpleNamespace(company_id=1, env={'stock.quant': QuantityOnly(), 'product.product': product})
    result = asyncio.run(handler.get_stock({'product_ids': [1]}))[0].text
    rows = json.loads(result.split('```json\n')[1].split('```')[0])
    assert rows[0]['value'] == 6.0
    assert 'estimated value' in result
    assert "has no 'value' field" not in result


def test_empty_stock_result():
    handler = ManufacturingHandler()
    handler.odoo = SimpleNamespace(company_id=1, env={'stock.quant': SimpleNamespace(
        formatted_read_group=lambda *args, **kwargs: [])})
    result = asyncio.run(handler.get_stock({'product_ids': [1]}))[0].text
    assert 'No quants matched' in result
    assert json.loads(result.split('```json\n')[1].split('```')[0]) == []
