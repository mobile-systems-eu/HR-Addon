"""Methoden fuer die Number Cards im Bereich Zeiterfassung."""

import frappe
from frappe.utils import getdate, today


@frappe.whitelist()
def gerade_eingestempelt(filters=None):
	"""Mitarbeiter mit ungerader Stempelzahl heute -- also gerade im Haus.

	Wer in der Pause ist (ausgestempelt), zaehlt nicht mit.
	"""
	frappe.has_permission("Employee Checkin", "read", throw=True)

	heute = getdate(today())
	rows = frappe.db.sql(
		"""
		select employee
		from `tabEmployee Checkin`
		where time >= %(von)s and time < %(von)s + interval 1 day
		group by employee
		having mod(count(*), 2) = 1
		""",
		{"von": heute},
	)
	return {"value": len(rows), "fieldtype": "Int"}
