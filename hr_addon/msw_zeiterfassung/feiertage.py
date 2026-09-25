"""Welche Feiertagsliste fuer einen Mitarbeiter an einem Tag gilt.

hrms v16 ordnet Feiertagslisten ueber ``Holiday List Assignment`` zu --
je Mitarbeiter oder je Firma, mit Gueltigkeitsbeginn. Danach zaehlt hrms
auch die Urlaubstage. Das Addon las dagegen nur ``Employee.holiday_list``
und konnte damit andere Feiertage sehen als die Urlaubsberechnung.

``get_holiday_list()`` loest wie hrms auf und faellt nur dann auf das
Mitarbeiterfeld zurueck, wenn es keine Zuordnung gibt.
"""

import frappe
from frappe.utils import getdate, strip_html


def get_holiday_list(employee: str, datum) -> str | None:
	try:
		from hrms.utils.holiday_list import get_holiday_list_for_employee
	except ImportError:  # aelteres hrms ohne Holiday List Assignment
		get_holiday_list_for_employee = None

	if get_holiday_list_for_employee:
		liste = get_holiday_list_for_employee(
			employee, raise_exception=False, as_on=getdate(datum)
		)
		if liste:
			return liste

	return frappe.get_cached_value("Employee", employee, "holiday_list")


def get_holiday(employee: str, datum) -> frappe._dict | None:
	"""Eintrag der Feiertagsliste fuer diesen Tag, sonst ``None``.

	``beschreibung`` ist bereinigt -- in der Liste steht HTML aus dem
	Editor (``<div class="ql-editor">``).
	"""
	liste = get_holiday_list(employee, datum)
	if not liste:
		return None

	eintrag = frappe.db.get_value(
		"Holiday",
		{"parent": liste, "holiday_date": getdate(datum)},
		["description", "weekly_off"],
		as_dict=True,
	)
	if not eintrag:
		return None

	eintrag.beschreibung = " ".join(strip_html(eintrag.description or "").split())
	return eintrag
