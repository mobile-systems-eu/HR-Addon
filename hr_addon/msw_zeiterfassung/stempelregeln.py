"""Stempelungen an Sonn- und Feiertagen ablehnen.

Haengt an ``Employee Checkin.before_insert``. Die Ablehnung ist ein
eigener Ausnahmetyp: Frappe liefert dann HTTP 417 mit
``exc_type = "StempelungAbgelehnt"``. Daran erkennt die Stempeluhr, dass
nicht der Chip unbekannt ist, sondern eine Regel greift, und zeigt die
Meldung aus den Einstellungen an.

Bestehende Stempelungen werden nicht geprueft -- nur neue.
"""

import frappe
from frappe.utils import formatdate, getdate

from hr_addon.msw_zeiterfassung import einstellungen
from hr_addon.msw_zeiterfassung.feiertage import get_holiday

AUSNAHME_ROLLEN = {"HR Manager", "System Manager"}


class StempelungAbgelehnt(frappe.ValidationError):
	pass


def pruefe_neue_stempelung(doc, method=None):
	if einstellungen.get("msw_sonn_feiertag_regel") != einstellungen.SONN_FEIERTAG_ABLEHNEN:
		return
	if not doc.employee or not doc.time:
		return  # hrms meldet das selbst
	if einstellungen.get("msw_sonn_feiertag_hr_ausnahme") and (
		AUSNAHME_ROLLEN & set(frappe.get_roles())
	):
		return

	feiertag = get_holiday(doc.employee, doc.time)
	if not feiertag:
		return

	tag = feiertag.beschreibung or formatdate(getdate(doc.time))
	vorlage = einstellungen.get("msw_sonn_feiertag_meldung") or einstellungen.MELDUNG_SONN_FEIERTAG
	frappe.throw(
		vorlage.replace("{tag}", tag),
		exc=StempelungAbgelehnt,
		title="Stempelung nicht möglich",
	)
