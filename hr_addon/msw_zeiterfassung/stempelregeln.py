"""Stempelungen an Feiertagen und an Tagen ohne Sollarbeitszeit ablehnen.

Haengt an ``Employee Checkin.before_insert``. Zwei getrennt schaltbare
Regeln:

* **Feiertag:** Der Tag steht in der Feiertagsliste des Mitarbeiters
  (Feiertagsliste-Zuordnung, sonst ``Employee.holiday_list``).
* **Tag ohne Sollarbeitszeit:** Der Mitarbeiter hat eine gueltige,
  eingereichte Sollarbeitszeit (Weekly Working Hours), aber darin **keine
  Zeile** fuer diesen Wochentag -- bei MSW der Sonntag. Eine Zeile mit
  0 Stunden (Samstag) ist ein Eintrag: dort darf gestempelt werden.
  Hat der Mitarbeiter gar keine gueltige Sollarbeitszeit, wird nicht
  abgelehnt; die Stempelung waere sonst verloren, nur weil die
  Sollarbeitszeit noch nicht eingereicht ist.

Die Ablehnung ist ein eigener Ausnahmetyp: Frappe liefert HTTP 417 mit
``exc_type = "StempelungAbgelehnt"``. Daran erkennt die Stempeluhr, dass
eine Regel greift und nicht der Chip unbekannt ist, und zeigt die Meldung
aus den Einstellungen an.

Bestehende Stempelungen werden nicht geprueft -- nur neue.
"""

import frappe
from frappe.utils import formatdate, getdate

from hr_addon.msw_zeiterfassung import einstellungen
from hr_addon.msw_zeiterfassung.feiertage import get_holiday

AUSNAHME_ROLLEN = {"HR Manager", "System Manager"}

# Werte von Daily Hours Detail.day (englisch, unabhaengig von der Locale)
WOCHENTAGE = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WOCHENTAGE_DE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


class StempelungAbgelehnt(frappe.ValidationError):
	pass


def pruefe_neue_stempelung(doc, method=None):
	if not doc.employee or not doc.time:
		return  # hrms meldet das selbst

	feiertag_ablehnen = einstellungen.get("msw_feiertag_regel") == einstellungen.ABLEHNEN
	ohne_sollzeit_ablehnen = einstellungen.get("msw_ohne_sollzeit_regel") == einstellungen.ABLEHNEN
	if not feiertag_ablehnen and not ohne_sollzeit_ablehnen:
		return
	if einstellungen.get("msw_stempel_hr_ausnahme") and (AUSNAHME_ROLLEN & set(frappe.get_roles())):
		return

	datum = getdate(doc.time)

	if feiertag_ablehnen:
		feiertag = get_holiday(doc.employee, datum)
		if feiertag:
			_ablehnen(
				"msw_feiertag_meldung",
				einstellungen.MELDUNG_FEIERTAG,
				feiertag.beschreibung or formatdate(datum),
			)

	if ohne_sollzeit_ablehnen and hat_keinen_sollzeit_eintrag(doc.employee, datum):
		_ablehnen(
			"msw_ohne_sollzeit_meldung",
			einstellungen.MELDUNG_OHNE_SOLLZEIT,
			WOCHENTAGE_DE[datum.weekday()],
		)


def hat_keinen_sollzeit_eintrag(employee, datum) -> bool:
	"""True, wenn eine gueltige Sollarbeitszeit existiert, aber ohne Zeile
	fuer diesen Wochentag. Eine Zeile mit 0 Stunden zaehlt als Eintrag."""
	datum = getdate(datum)
	zeilen = frappe.db.sql(
		"""
		select w.name, d.day
		from `tabWeekly Working Hours` w
		left join `tabDaily Hours Detail` d
			on d.parent = w.name and d.parenttype = 'Weekly Working Hours'
		where w.employee = %(employee)s
			and w.docstatus = 1
			and w.valid_from <= %(datum)s
			and w.valid_to >= %(datum)s
		""",
		{"employee": employee, "datum": datum},
		as_dict=True,
	)
	if not zeilen:
		return False  # gar keine Sollarbeitszeit: nicht ablehnen
	wochentag = WOCHENTAGE[datum.weekday()]
	return not any(z.day == wochentag for z in zeilen)


def _ablehnen(feld, standard, tag):
	vorlage = einstellungen.get(feld) or standard
	frappe.throw(
		vorlage.replace("{tag}", tag),
		exc=StempelungAbgelehnt,
		title="Stempelung nicht möglich",
	)
