"""Zeitkonto-Salden: ein Zeile je Mitarbeiter.

Saldo zum Stichtag, Saldo zu Monatsbeginn, Veraenderung dazwischen und
Resturlaub. Die Salden kommen wie im Report "Overtime Ledger" aus
``balance_after`` der letzten gueltigen Zeitkonto-Buchung
(``get_previous_balance``), nicht aus einer Summe ueber ``hour_variance``
-- Stornos und Gegenbuchungen wuerden eine Summe verfaelschen.
"""

import frappe
from frappe.utils import add_days, flt, get_first_day, getdate, today

from hr_addon.events.overtime_ledger import get_previous_balance


def execute(filters=None):
	filters = frappe._dict(filters or {})
	stichtag = getdate(filters.stichtag or today())
	monatsbeginn = get_first_day(stichtag)
	leave_type = filters.leave_type

	emp_filters = {"status": "Active"}
	if filters.company:
		emp_filters["company"] = filters.company
	if filters.department:
		emp_filters["department"] = filters.department

	employees = frappe.get_all(
		"Employee",
		filters=emp_filters,
		fields=["name", "employee_name", "department", "default_shift"],
		order_by="employee_name",
	)

	data = []
	for emp in employees:
		saldo = flt(get_previous_balance(emp.name, f"{add_days(stichtag, 1)} 00:00:00"), 2)
		saldo_monatsbeginn = flt(get_previous_balance(emp.name, f"{monatsbeginn} 00:00:00"), 2)
		data.append(
			{
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"department": emp.department,
				"default_shift": emp.default_shift,
				"saldo_monatsbeginn": saldo_monatsbeginn,
				"veraenderung": flt(saldo - saldo_monatsbeginn, 2),
				"saldo": saldo,
				"resturlaub": _resturlaub(emp.name, leave_type, stichtag),
			}
		)

	return get_columns(leave_type), data, None, get_chart(data)


def _resturlaub(employee, leave_type, stichtag):
	if not leave_type:
		return None
	from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on

	# Genehmigte, aber noch kommende Abwesenheiten sind schon abgezogen.
	return flt(
		get_leave_balance_on(
			employee, leave_type, stichtag, consider_all_leaves_in_the_allocation_period=True
		),
		1,
	)


def get_columns(leave_type):
	columns = [
		{"fieldname": "employee", "label": "Mitarbeiter", "fieldtype": "Link", "options": "Employee", "width": 130},
		{"fieldname": "employee_name", "label": "Name", "fieldtype": "Data", "width": 200},
		{"fieldname": "department", "label": "Abteilung", "fieldtype": "Link", "options": "Department", "width": 150},
		{"fieldname": "default_shift", "label": "Standardschicht", "fieldtype": "Link", "options": "Shift Type", "width": 120},
		{"fieldname": "saldo_monatsbeginn", "label": "Saldo Monatsbeginn (Std.)", "fieldtype": "Float", "precision": 2, "width": 170},
		{"fieldname": "veraenderung", "label": "Veränderung im Monat (Std.)", "fieldtype": "Float", "precision": 2, "width": 180},
		{"fieldname": "saldo", "label": "Saldo (Std.)", "fieldtype": "Float", "precision": 2, "width": 120},
	]
	if leave_type:
		columns.append(
			{"fieldname": "resturlaub", "label": f"Resturlaub {leave_type} (Tage)", "fieldtype": "Float", "precision": 1, "width": 170}
		)
	return columns


def get_chart(data):
	if not data:
		return None
	return {
		"data": {
			"labels": [d["employee_name"] for d in data],
			"datasets": [{"name": "Saldo (Std.)", "values": [d["saldo"] for d in data]}],
		},
		"type": "bar",
		"colors": ["#2490EF"],
	}
