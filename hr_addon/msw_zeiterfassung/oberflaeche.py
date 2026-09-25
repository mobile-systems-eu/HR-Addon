"""Vereinfachte Oberflaeche fuer die Zeiterfassung (abschaltbar).

Schalter: ``msw_vereinfachte_oberflaeche`` in den HR Addon Settings.

Was er tut
----------
1. **Desktop und Seitenleiste:** blendet HR-Bereiche aus, die MSW nicht
   nutzt (Gehalt, Spesen, Recruiting, ...). "Leaves" und "Shift &
   Attendance" gehen ebenfalls weg -- ihr Inhalt steht im Bereich
   "Zeiterfassung". Umgesetzt im ``boot_session``-Hook, also ohne die
   Standard-Datensaetze von hrms zu aendern: ein ``bench migrate`` kann
   nichts zuruecksetzen, und Ausschalten wirkt sofort.
2. **Einstellungsseiten:** blendet ungenutzte Felder aus und ordnet die
   HR Addon Settings in Tabs. Umgesetzt mit Property Settern, die mit
   ``module = "MSW Zeiterfassung"`` markiert sind; beim Ausschalten werden
   genau diese wieder geloescht.

Direkte Links (z. B. /desk/payroll) funktionieren weiter -- es wird nur
aufgeraeumt, nicht gesperrt. Rechte regeln weiterhin die Rollen.

Bekannte Grenze: Hat ein Benutzer sich ein eigenes Desktop-Layout
gespeichert, zeigt frappe dieses statt der Boot-Liste (Vermutung aus
``desk/page/desktop/desktop.js``, nicht getestet).
"""

import json

import frappe

from hr_addon.msw_zeiterfassung import einstellungen

MODULE = einstellungen.MODULE
SCHALTER = "msw_vereinfachte_oberflaeche"

AUSGEBLENDETE_BEREICHE = (
	"Expenses",
	"Payroll",
	"Tax & Benefits",
	"Performance",
	"Recruitment",
	"Tenure",
	"Leaves",
	"Shift & Attendance",
)

VERSTECKTE_FELDER = {
	"HR Addon Settings": [
		"general_section",  # ICS-Kalenderexport
		"notification_section",  # Jubilaeums-Benachrichtigung
		"background_job_frequency",  # MSW laeuft taeglich
		"day",
		"swap_hours_worked_and_actual_working_hours",
		"workday_break_calculation_logic",  # englische Erklaerung aller Verfahren
	],
	"HR Settings": [
		"reminders_section",
		"auto_leave_encashment",
		"attendance_settings_section",  # Mobile App, Geolocation
		"expenses_tab",
		"expenses_settings_section",
		"tenure_tab",
		"employee_exit_settings_section",
		"recruitment_tab",
		"hiring_settings_section",
	],
}

FELDREIHENFOLGE = {
	"HR Addon Settings": [
		"msw_tab_arbeitstage",
		"scheduled_job_section",
		"enabled",
		"time",
		"generate_workdays_for_past_7_days_now",
		"background_job_frequency",
		"day",
		"column_break_jozi",
		"skip_workday_if_no_weekly_hours",
		"allow_workdays_on_holidays",
		"msw_sec_automatik",
		"msw_sofort_neu_berechnen",
		"msw_tagesabschluss_aktiv",
		"msw_tagesabschluss_tage",
		"msw_fehltage_buchen",
		"msw_sec_urlaub",
		"msw_urlaub_nur_sollzeit",
		"half_day_holidays_section_section",
		"half_day_holidays",
		"break_rules_tab",
		"workday_break_calculation_mechanism",
		"swap_hours_worked_and_actual_working_hours",
		"workday_break_calculation_logic",
		"minimum_break_rule",
		"overtime_ledger_tab",
		"enable_overtime_ledger_feature",
		"overtime_frozen",
		"select_employees",
		"repost_all_oles",
		"msw_tab_stempelregeln",
		"msw_sec_sonn_feiertag",
		"msw_sonn_feiertag_regel",
		"msw_sonn_feiertag_meldung",
		"msw_sonn_feiertag_hr_ausnahme",
		"msw_tab_oberflaeche",
		"msw_vereinfachte_oberflaeche",
		# ausgeblendet, nur der Vollstaendigkeit halber in der Reihenfolge
		"general_section",
		"name_of_calendar_export_ics_file",
		"ics_folder_path",
		"download_ics_file",
		"notification_section",
		"anniversary_notification_email_list",
		"enable_work_anniversaries_notification",
		"column_break_dvlg",
		"anniversary_notification_email_recipient_role",
		"notification_x_days_before",
		"enable_work_anniversaries_notification_for_leave_approvers",
	],
}


def ist_aktiv() -> bool:
	return bool(einstellungen.get(SCHALTER))


# -- Desktop und Seitenleiste ---------------------------------------------


def boot_session(bootinfo):
	if not ist_aktiv():
		return

	weg = set(AUSGEBLENDETE_BEREICHE)
	if bootinfo.get("desktop_icons"):
		bootinfo.desktop_icons = [i for i in bootinfo.desktop_icons if i.get("label") not in weg]

	sidebars = bootinfo.get("workspace_sidebar_item") or {}
	for key in [b.lower() for b in weg]:
		sidebars.pop(key, None)


# -- Einstellungsseiten ----------------------------------------------------


def anwenden():
	"""Property Setter passend zum Schalter anlegen oder entfernen."""
	frappe.db.delete("Property Setter", {"module": MODULE})

	if ist_aktiv():
		for doctype, felder in VERSTECKTE_FELDER.items():
			vorhanden = _feldnamen(doctype)
			for fieldname in felder:
				if fieldname in vorhanden:
					_setter(doctype, fieldname, "hidden", "1", "Check")

		for doctype, reihenfolge in FELDREIHENFOLGE.items():
			vorhanden = _feldnamen(doctype)
			# Felder, die ein Update neu mitbringt, haengen hinten an
			rest = [f for f in vorhanden if f not in reihenfolge]
			order = [f for f in reihenfolge if f in vorhanden] + rest
			_setter(doctype, None, "field_order", json.dumps(order), "Data", for_doctype=True)

	for doctype in set(VERSTECKTE_FELDER) | set(FELDREIHENFOLGE):
		frappe.clear_cache(doctype=doctype)


def _feldnamen(doctype):
	# Meta ohne Property Setter lesen waere schoener; die eigenen sind
	# oben schon geloescht, fremde (Customize Form) duerfen bleiben.
	frappe.clear_cache(doctype=doctype)
	return [df.fieldname for df in frappe.get_meta(doctype).fields]


def _setter(doctype, fieldname, prop, value, prop_type, for_doctype=False):
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	ps = make_property_setter(
		doctype,
		fieldname,
		prop,
		value,
		prop_type,
		for_doctype=for_doctype,
		validate_fields_for_doctype=False,
	)
	frappe.db.set_value("Property Setter", ps.name, "module", MODULE, update_modified=False)


# -- Hooks -----------------------------------------------------------------


def after_migrate():
	anwenden()
	frappe.cache.delete_key("bootinfo")


def nach_speichern(doc, method=None):
	"""HR Addon Settings gespeichert: bei geaendertem Schalter neu anwenden."""
	if not doc.has_value_changed(SCHALTER):
		return
	anwenden()
	# Boot neu aufbauen lassen, damit Desktop und Seitenleiste sofort passen
	frappe.cache.delete_key("bootinfo")
	frappe.cache.delete_key("desktop_icons")
