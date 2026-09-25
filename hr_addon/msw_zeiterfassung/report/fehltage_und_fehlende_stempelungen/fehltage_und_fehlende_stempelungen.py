"""Fehltage und fehlende Stempelungen je Tag und Mitarbeiter.

"Fehlt": Arbeitstag mit Sollzeit ohne jede Stempelung und ohne
Abwesenheit. "Stempelung fehlt": ungerade Anzahl Stempelungen, der Tag
zaehlt mit null Stunden, bis die Stempelung nachgetragen ist.
"""

import frappe
from frappe.utils import add_days, flt, getdate, today

ARTEN = {
	"Absent": "Fehlt",
	"Missing Checkin": "Stempelung fehlt",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	von = getdate(filters.from_date or add_days(today(), -30))
	bis = getdate(filters.to_date or add_days(today(), -1))

	status = list(ARTEN)
	if filters.art == "Fehlt":
		status = ["Absent"]
	elif filters.art == "Stempelung fehlt":
		status = ["Missing Checkin"]

	wd_filters = {"log_date": ["between", [von, bis]], "status": ["in", status]}
	if filters.employee:
		wd_filters["employee"] = filters.employee
	if filters.company:
		wd_filters["company"] = filters.company

	workdays = frappe.get_all(
		"Workday",
		filters=wd_filters,
		fields=["name", "employee", "employee_name", "log_date", "status", "target_hours", "attendance"],
		order_by="log_date desc, employee_name asc",
	)

	data = []
	for wd in workdays:
		# Samstag o. Ae. ohne Sollzeit ist kein Fehltag
		if wd.status == "Absent" and flt(wd.target_hours) <= 0:
			continue
		gebucht = None
		if wd.attendance:
			gebucht = frappe.db.get_value(
				"Attendance", {"name": wd.attendance, "docstatus": 1}, "custom_hour_variance"
			)
		data.append(
			{
				"log_date": wd.log_date,
				"wochentag": _wochentag(wd.log_date),
				"employee": wd.employee,
				"employee_name": wd.employee_name,
				"art": ARTEN[wd.status],
				"target_hours": flt(wd.target_hours, 2),
				"gebucht": flt(gebucht, 2) if gebucht is not None else None,
				"workday": wd.name,
			}
		)

	return get_columns(), data


def _wochentag(datum):
	return ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")[getdate(datum).weekday()]


def get_columns():
	return [
		{"fieldname": "log_date", "label": "Datum", "fieldtype": "Date", "width": 100},
		{"fieldname": "wochentag", "label": "Tag", "fieldtype": "Data", "width": 50},
		{"fieldname": "employee", "label": "Mitarbeiter", "fieldtype": "Link", "options": "Employee", "width": 130},
		{"fieldname": "employee_name", "label": "Name", "fieldtype": "Data", "width": 200},
		{"fieldname": "art", "label": "Art", "fieldtype": "Data", "width": 140},
		{"fieldname": "target_hours", "label": "Sollstunden", "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "gebucht", "label": "Im Zeitkonto (Std.)", "fieldtype": "Float", "precision": 2, "width": 140},
		{"fieldname": "workday", "label": "Arbeitstag", "fieldtype": "Link", "options": "Workday", "width": 140},
	]
