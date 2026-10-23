"""Resource bounds for the shared remote Odoo connection (not stdio)."""

from .connection import CompanyOdoo

MAX_RECORDS = 500


class RemoteLimitError(ValueError):
    """The operation needs narrower filters or pagination."""


class RemoteOdoo(CompanyOdoo):
    def execute(self, model, method, *args):
        return self.execute_kw(model, method, args)

    def execute_kw(self, model, method, args=None, kwargs=None):
        args, kwargs = list(args or []), dict(kwargs or {})
        positions = {"search": 2, "search_read": 3, "read_group": 4,
                     "formatted_read_group": 5}
        if method in positions:
            position = positions[method]
            limit = args[position] if len(args) > position else kwargs.get("limit")
            # Ask for one extra row when the caller expects the complete set.
            # Detect overflow and fail instead of returning misleading totals.
            bounded = min(limit, MAX_RECORDS + 1) if type(limit) is int and limit > 0 else MAX_RECORDS + 1
            if len(args) > position:
                args[position] = bounded
            else:
                kwargs["limit"] = bounded
        if method == "read":
            ids = args[0] if args else kwargs.get("ids", [])
            if isinstance(ids, (list, tuple)) and len(ids) > MAX_RECORDS:
                raise RemoteLimitError("Too many records; narrow the filters")
        result = super().execute_kw(model, method, args, kwargs)
        if method in (*positions, "read") and isinstance(result, list) and len(result) > MAX_RECORDS:
            raise RemoteLimitError("Too many records; narrow the filters")
        return result
