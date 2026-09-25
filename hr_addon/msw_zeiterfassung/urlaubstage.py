"""Urlaub nur fuer Tage abziehen, an denen der Mitarbeiter Sollzeit hat.

Problem
-------
hrms zaehlt Urlaubstage als "Kalendertage minus Feiertage"
(``get_number_of_leave_days``; Feiertage nur, wenn die Abwesenheitsart
``include_holiday`` aus hat). Samstage stehen bei MSW bewusst nicht in der
Feiertagsliste -- dort wird gearbeitet, nur ohne Sollzeit. Zwei Wochen
Urlaub kosteten damit 12 statt 10 Tage.

Loesung
-------
``get_holidays`` in hrms' ``leave_application`` wird ersetzt: zusaetzlich zu
den Feiertagen zaehlt jeder Tag als frei, fuer den die gueltige
Sollarbeitszeit (Weekly Working Hours, eingereicht) 0 Stunden oder gar
keine Zeile fuer diesen Wochentag hat. Dieselbe Funktion nutzt hrms fuer
Antrag, Kontingentpruefung und Aufteilung auf mehrere Zuteilungen -- alle
Aufrufe liegen im selben Modul und schlagen den Namen zur Laufzeit nach.

Tage, fuer die der Mitarbeiter **gar keine** gueltige Sollarbeitszeit hat,
zaehlen wie bisher. Sonst waere Urlaub fuer Mitarbeiter ohne Zeiterfassung
kostenlos.

Schalter: ``msw_urlaub_nur_sollzeit`` in den HR Addon Settings.

Warum Ersetzen zur Laufzeit
---------------------------
hrms bietet dafuer keinen Hook. ``installieren()`` laeuft vor jeder
Anfrage und jedem Hintergrundjob (``before_request``/``before_job``) und
ist idempotent. Aendert hrms die Signatur von ``get_holidays``, bricht das
beim naechsten Update sichtbar (TypeError), nicht still.
"""

import datetime

import frappe
from frappe.utils import add_days, date_diff, getdate

from hr_addon.msw_zeiterfassung import einstellungen

_MARKE = "_msw_urlaub_nur_sollzeit"

# Werte von Daily Hours Detail.day; bewusst nicht strftime("%A"), das haengt
# von der Locale des Servers ab.
WOCHENTAGE = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def installieren(*args, **kwargs):
	try:
		from hrms.hr.doctype.leave_application import leave_application as la
	except ImportError:
		return
	if getattr(la.get_holidays, _MARKE, False):
		return

	original = la.get_holidays

	@frappe.whitelist()
	def get_holidays(employee, from_date, to_date, leave_application=None):
		anzahl = original(employee, from_date, to_date, leave_application=leave_application)
		if not einstellungen.get("msw_urlaub_nur_sollzeit"):
			return anzahl
		return anzahl + len(tage_ohne_sollzeit(employee, from_date, to_date))

	get_holidays.__doc__ = original.__doc__
	setattr(get_holidays, _MARKE, True)
	la.get_holidays = get_holidays


def tage_ohne_sollzeit(employee, from_date, to_date) -> list[datetime.date]:
	"""Tage ohne Sollzeit im Zeitraum, die nicht ohnehin Feiertage sind."""
	von, bis = getdate(from_date), getdate(to_date)
	if bis < von:
		return []

	zeilen = frappe.db.sql(
		"""
		select w.valid_from, w.valid_to, d.day, d.hours
		from `tabWeekly Working Hours` w
		left join `tabDaily Hours Detail` d
			on d.parent = w.name and d.parenttype = 'Weekly Working Hours'
		where w.employee = %(employee)s
			and w.docstatus = 1
			and w.valid_from <= %(bis)s
			and w.valid_to >= %(von)s
		""",
		{"employee": employee, "von": von, "bis": bis},
		as_dict=True,
	)
	if not zeilen:
		return []

	feiertage = set(_feiertage(employee, von, bis))
	ergebnis = []
	for i in range(date_diff(bis, von) + 1):
		tag = add_days(von, i)
		if tag in feiertage:
			continue  # zaehlt hrms schon
		gueltig = [z for z in zeilen if getdate(z.valid_from) <= tag <= getdate(z.valid_to)]
		if not gueltig:
			continue  # keine Sollarbeitszeit an diesem Tag: wie bisher zaehlen
		wochentag = WOCHENTAGE[tag.weekday()]
		stunden = sum((z.hours or 0) for z in gueltig if z.day == wochentag)
		if stunden <= 0:
			ergebnis.append(tag)
	return ergebnis


def _feiertage(employee, von, bis):
	from hrms.utils.holiday_list import get_holiday_dates_between_range

	return [
		getdate(d)
		for d in get_holiday_dates_between_range(
			employee, von, bis, raise_exception_for_holiday_list=False
		)
	]
