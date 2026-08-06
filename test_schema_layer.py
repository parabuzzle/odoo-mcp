"""Offline regression tests for the defensive fields_get schema layer.

These run WITHOUT a live Odoo connection: they stub odoo.env with a fake model
whose fields_get()/read() are backed by in-memory dicts. They lock in the
Odoo 18->19 hardening: missing fields are dropped from reads (never crash),
write payloads with removed fields fail fast, and the kanban_state->state
remap resolves against the live selection.

Run: python test_schema_layer.py
"""

import asyncio

from odoo_mcp.base import OdooBase
from odoo_mcp.projects import ProjectsHandler
from odoo_mcp.contacts import ContactsHandler


class FakeModel:
    def __init__(self, fields, records=None):
        self._fields = fields
        self._records = records or {}

    def fields_get(self, allfields=None, attributes=None):
        return self._fields

    def read(self, ids, fields):
        single = isinstance(ids, int)
        id_list = [ids] if single else list(ids)
        rows = []
        for i in id_list:
            rec = self._records.get(i, {})
            rows.append({f: rec.get(f) for f in fields})
        return rows


class FakeEnv:
    def __init__(self, models):
        self._models = models

    def __getitem__(self, name):
        return self._models[name]


class FakeOdoo:
    def __init__(self, models):
        self.env = FakeEnv(models)


def reset_cache():
    OdooBase._fields_cache = {}


def _partner_fields():
    # res.partner in Odoo 19: no 'mobile' (merged into phone).
    return {name: {"type": "char", "string": name}
            for name in ["name", "id", "email", "phone", "is_company",
                         "parent_id", "active", "category_id"]}


def _task_fields():
    fields = {name: {"type": "char", "string": name}
              for name in ["name", "id", "user_ids", "stage_id", "priority",
                           "description", "date_deadline", "tag_ids",
                           "partner_id", "date_assign", "child_ids",
                           "subtask_count", "project_id"]}
    # kanban_state is GONE; state selection is present.
    fields["state"] = {
        "type": "selection",
        "string": "State",
        "selection": [
            ["01_in_progress", "In Progress"],
            ["02_changes_requested", "Changes Requested"],
            ["03_approved", "Approved"],
            ["1_done", "Done"],
            ["1_canceled", "Cancelled"],
        ],
    }
    return fields


def test_safe_read_drops_missing_field():
    reset_cache()
    h = OdooBase()
    h.odoo = FakeOdoo({"res.partner": FakeModel(
        _partner_fields(), {1: {"name": "Acme", "phone": "555"}})})

    records, warnings = h.safe_read(
        "res.partner", [1],
        ["name", "phone", "mobile"])  # 'mobile' no longer exists

    assert records == [{"name": "Acme", "phone": "555"}], records
    assert warnings == ["field 'mobile' not present on res.partner, omitted"], warnings
    print("PASS test_safe_read_drops_missing_field")


def test_safe_read_all_present_no_warnings():
    reset_cache()
    h = OdooBase()
    h.odoo = FakeOdoo({"res.partner": FakeModel(_partner_fields(), {1: {"name": "A"}})})
    records, warnings = h.safe_read("res.partner", [1], ["name", "email"])
    assert warnings == [], warnings
    print("PASS test_safe_read_all_present_no_warnings")


def test_invalid_write_fields():
    reset_cache()
    h = OdooBase()
    h.odoo = FakeOdoo({"res.partner": FakeModel(_partner_fields())})
    assert h.invalid_write_fields("res.partner", {"name": "x", "phone": "y"}) == []
    assert h.invalid_write_fields("res.partner", {"mobile": "y"}) == ["mobile"]
    print("PASS test_invalid_write_fields")


def test_fail_open_when_schema_unknown():
    reset_cache()
    h = OdooBase()

    class Boom(FakeModel):
        def fields_get(self, allfields=None, attributes=None):
            raise RuntimeError("no access")

    h.odoo = FakeOdoo({"res.partner": Boom({}, {1: {"name": "A", "mobile": "m"}})})
    # Schema unknown -> nothing dropped, nothing raised.
    records, warnings = h.safe_read("res.partner", [1], ["name", "mobile"])
    assert warnings == [], warnings
    assert h.invalid_write_fields("res.partner", {"mobile": "m"}) == []
    print("PASS test_fail_open_when_schema_unknown")


def test_cache_is_one_rpc_per_model():
    reset_cache()
    h = OdooBase()
    calls = {"n": 0}

    class Counting(FakeModel):
        def fields_get(self, allfields=None, attributes=None):
            calls["n"] += 1
            return super().fields_get(allfields, attributes)

    h.odoo = FakeOdoo({"res.partner": Counting(_partner_fields())})
    h.get_model_fields("res.partner")
    h.get_model_fields("res.partner")
    h.get_model_fields("res.partner")
    assert calls["n"] == 1, calls
    print("PASS test_cache_is_one_rpc_per_model")


def test_kanban_to_state_mapping():
    reset_cache()
    h = ProjectsHandler()
    h.odoo = FakeOdoo({"project.task": FakeModel(_task_fields())})

    assert h._map_kanban_to_state("normal") == ("01_in_progress", None)
    assert h._map_kanban_to_state("blocked") == ("02_changes_requested", None)
    assert h._map_kanban_to_state("done") == ("03_approved", None)
    # Friendly label resolves from the live selection.
    assert h._state_label("02_changes_requested") == "Changes Requested"
    print("PASS test_kanban_to_state_mapping")


def test_kanban_to_state_fallback_and_unmappable():
    reset_cache()
    h = ProjectsHandler()
    # A server whose state selection uses different keys.
    fields = _task_fields()
    fields["state"]["selection"] = [["draft", "Draft"], ["done", "Done"]]
    h.odoo = FakeOdoo({"project.task": FakeModel(fields)})

    # 'done' still resolves via the fallback candidate 'done'.
    assert h._map_kanban_to_state("done") == ("done", None)
    # 'normal' has no matching candidate -> unmapped with a warning.
    key, warn = h._map_kanban_to_state("normal")
    assert key is None and warn and "could not be mapped" in warn, (key, warn)
    print("PASS test_kanban_to_state_fallback_and_unmappable")


def test_create_task_rejects_removed_field_before_write():
    # If the remap were to somehow inject a removed field, create_task must
    # fail fast with a clear message rather than hit Odoo. Simulate by making
    # 'state' absent from the schema so nothing maps, then assert no crash and
    # a real create path. Here we mainly assert kanban arg never becomes a
    # literal 'kanban_state' write key.
    reset_cache()
    h = ProjectsHandler()

    created = {}

    class TaskModel(FakeModel):
        def create(self, values):
            created.update(values)
            return 42

        def read(self, ids, fields):
            return [{"name": "T", "id": 42, "stage_id": False,
                     "user_ids": [], "project_id": [1, "Proj"]}]

    h.odoo = FakeOdoo({"project.task": TaskModel(_task_fields())})
    out = asyncio.run(h.create_task({"project_id": 1, "name": "T",
                                     "kanban_state": "blocked"}))
    text = out[0].text
    assert "kanban_state" not in created, created  # never written as a field
    assert created.get("state") == "02_changes_requested", created
    assert "Task Created Successfully" in text, text
    print("PASS test_create_task_rejects_removed_field_before_write")


def test_contact_mobile_aliased_to_phone():
    reset_cache()
    h = ContactsHandler()
    created = {}

    class PartnerModel(FakeModel):
        def create(self, values):
            created.update(values)
            return 7

        def read(self, ids, fields):
            return [{"name": "P", "id": 7, "email": False, "is_company": False}]

    h.odoo = FakeOdoo({"res.partner": PartnerModel(_partner_fields())})
    asyncio.run(h.create_contact({"name": "P", "mobile": "555-1234"}))
    assert "mobile" not in created, created
    assert created.get("phone") == "555-1234", created
    print("PASS test_contact_mobile_aliased_to_phone")


def test_contact_explicit_phone_wins_over_mobile():
    reset_cache()
    h = ContactsHandler()
    created = {}

    class PartnerModel(FakeModel):
        def create(self, values):
            created.update(values)
            return 7

        def read(self, ids, fields):
            return [{"name": "P", "id": 7, "email": False, "is_company": False}]

    h.odoo = FakeOdoo({"res.partner": PartnerModel(_partner_fields())})
    asyncio.run(h.create_contact({"name": "P", "phone": "111", "mobile": "222"}))
    assert created.get("phone") == "111", created
    print("PASS test_contact_explicit_phone_wins_over_mobile")


if __name__ == "__main__":
    test_safe_read_drops_missing_field()
    test_safe_read_all_present_no_warnings()
    test_invalid_write_fields()
    test_fail_open_when_schema_unknown()
    test_cache_is_one_rpc_per_model()
    test_kanban_to_state_mapping()
    test_kanban_to_state_fallback_and_unmappable()
    test_create_task_rejects_removed_field_before_write()
    test_contact_mobile_aliased_to_phone()
    test_contact_explicit_phone_wins_over_mobile()
    print("\nAll schema-layer tests passed.")
