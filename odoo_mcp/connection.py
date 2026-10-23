"""Pin every ORM RPC to the operator-selected Odoo company."""

import odoorpc


class CompanyOdoo(odoorpc.ODOO):
    company_id = 1

    def execute(self, model, method, *args):
        return self.execute_kw(model, method, args)

    def execute_kw(self, model, method, args=None, kwargs=None):
        kwargs = dict(kwargs or {})
        context = dict(kwargs.get("context") or {})
        context.update(allowed_company_ids=[self.company_id],
                       company_id=self.company_id, force_company=self.company_id)
        kwargs["context"] = context
        return super().execute_kw(model, method, args, kwargs)
