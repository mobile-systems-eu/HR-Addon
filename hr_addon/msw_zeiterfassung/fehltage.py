"""Fehltage erkennen und mit Minusstunden buchen (abschaltbar).

Problem
-------
Ein Arbeitstag ohne jede Stempelung bekommt im Addon den Status
``Absent``. ``create_attendace_record()`` bucht dafuer nichts
(``else: return``) -- wer unentschuldigt fehlt, verliert keine Stunde.
Ausserdem steht jeder stempelfreie Samstag (Sollzeit 0) ebenfalls auf
``Absent`` und ist in Listen nicht von einem echten Fehltag zu trennen.

Loesung
-------
Haengt an ``Workday``:

* ``validate``: Tag ohne Stempelung **und ohne Sollzeit** -> Status
  ``Not Workday`` ("Kein Arbeitstag") statt ``Absent``.
* ``on_update``: vergangener Tag mit Status ``Absent`` und Sollzeit > 0
  -> Anwesenheit mit Status ``Absent``, Soll = Tagessoll, Ist = 0. Beim
  Einreichen bucht das Addon selbst die Abweichung (-Soll) ins Zeitkonto
  (``create_overtime_ledger_entry_on_attendance_submit``).

Heute wird nie als Fehltag gebucht -- der Tag laeuft noch. Den Tag danach
erledigt der naechtliche Lauf des Addons (legt den Workday an) bzw. der
Tagesabschluss (``close_past_workdays``), der auch Fehltage der letzten
Tage ohne Anwesenheit nachholt.

Kommt spaeter doch eine Stempelung, rechnet der Workday neu, der Status
wird ``Present``, und das Addon aktualisiert die bestehende Anwesenheit
samt Zeitkonto-Buchung an Ort und Stelle (``_update_existing_attendance``).
Wird nachtraeglich Urlaub eingetragen, uebernimmt hrms die Anwesenheit.

Schalter: ``msw_fehltage_buchen`` in den HR Addon Settings.
"""

import frappe
from frappe.utils import flt, getdate, today

from hr_addon.msw_zeiterfassung import einstellungen


def aktiv() -> bool:
	return bool(einstellungen.get("msw_fehltage_buchen"))


def kein_arbeitstag_ohne_sollzeit(doc, method=None):
	"""Workday.validate: stempelfreier Tag ohne Sollzeit ist kein Fehltag."""
	if not aktiv():
		return
	if doc.status == "Absent" and flt(doc.target_hours) <= 0 and not doc.get("employee_checkins"):
		doc.status = "Not Workday"


def buche_fehltag(doc, method=None):
	"""Workday.on_update: unentschuldigten Fehltag als Anwesenheit ``Absent`` buchen."""
	if not aktiv() or doc.status != "Absent":
		return
	if getdate(doc.log_date) >= getdate(today()):
		return

	from hr_addon.events.attendance import get_effective_ole_target_hours
	from hr_addon.events.overtime_ledger import is_overtime_ledger_enabled

	if not is_overtime_ledger_enabled():
		return
	soll = flt(get_effective_ole_target_hours(flt(doc.target_hours), doc.employee, doc.log_date))
	if soll <= 0:
		return

	bestehend = frappe.get_all(
		"Attendance",
		filters={"employee": doc.employee, "attendance_date": doc.log_date, "docstatus": 1},
		fields=["name", "status", "custom_workday"],
	)
	for att in bestehend:
		if att.status == "Absent":
			return  # schon gebucht
		if att.status == "Present" and att.custom_workday == doc.name:
			# Stempelungen wurden geloescht: Teilbuchung zuruecknehmen
			frappe.get_doc("Attendance", att.name).cancel()
			continue
		return  # Urlaub, halber Tag o. Ae. -- nicht anfassen

	attendance = frappe.get_doc(
		{
			"doctype": "Attendance",
			"employee": doc.employee,
			"attendance_date": doc.log_date,
			"company": doc.company or frappe.db.get_value("Employee", doc.employee, "company"),
			"status": "Absent",
			"custom_workday": doc.name,
			"custom_target_hours": soll,
			"custom_actual_working_hours": 0,
			"custom_hour_variance": -soll,
			"custom_create_overtime_ledger_entry": 0,
		}
	)
	attendance.flags.ignore_permissions = True
	stumm = getattr(frappe.flags, "mute_messages", False)
	frappe.flags.mute_messages = True
	try:
		attendance.insert()
		attendance.submit()  # on_submit des Addons bucht -soll ins Zeitkonto
	finally:
		frappe.flags.mute_messages = stumm

	frappe.db.set_value("Workday", doc.name, "attendance", attendance.name, update_modified=False)
