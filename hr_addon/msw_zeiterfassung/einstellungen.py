"""MSW-Einstellungen als zusaetzliche Felder in den HR Addon Settings.

Warum keine eigene Einstellungsseite
------------------------------------
Alle Schalter der Zeiterfassung sollen auf **einer** Seite stehen. Die
HR Addon Settings bleiben dafuer die Seite; die MSW-Felder kommen als
Custom Fields dazu. So bleibt die Datei ``hr_addon_settings.json`` des
Addons unangetastet, und ``git merge upstream/version-15`` kann dort nicht
kollidieren.

Angelegt werden die Felder bei jedem ``bench migrate`` (``setup()`` haengt
an ``after_migrate``). ``module`` ist "MSW Zeiterfassung", damit die
Fixture-Regel des Addons (``Custom Field`` mit ``module = HR Addon``) sie
nicht exportiert.

Werte immer ueber ``get()`` lesen: ``frappe.db.get_single_value`` liefert
fuer ein nie gespeichertes Check-Feld 0 statt des Standardwerts. ``setup()``
schreibt deshalb die Standardwerte einmalig, ``get()`` faellt zusaetzlich
auf sie zurueck.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

SETTINGS = "HR Addon Settings"
MODULE = "MSW Zeiterfassung"

SONN_FEIERTAG_ABLEHNEN = "Stempelung ablehnen"
SONN_FEIERTAG_NICHT_WERTEN = "Annehmen, aber nicht werten"

MELDUNG_SONN_FEIERTAG = (
	"{tag}: An Sonn- und Feiertagen kann nicht gestempelt werden. "
	"Bitte im Büro melden."
)

FIELDS = [
	# Erster Tab, nur mit vereinfachter Oberflaeche sichtbar: dann ordnet
	# ein Property Setter (oberflaeche.FELDREIHENFOLGE) die Felder darunter.
	# Ohne Schalter stuende er leer am Ende.
	{
		"fieldname": "msw_tab_arbeitstage",
		"fieldtype": "Tab Break",
		"label": "Arbeitstage",
		"depends_on": "eval:doc.msw_vereinfachte_oberflaeche",
		"insert_after": "repost_all_oles",
	},
	# -- Stempelregeln -------------------------------------------------
	{
		"fieldname": "msw_tab_stempelregeln",
		"fieldtype": "Tab Break",
		"label": "Stempelregeln",
		"insert_after": "msw_tab_arbeitstage",
	},
	{
		"fieldname": "msw_sec_sonn_feiertag",
		"fieldtype": "Section Break",
		"label": "Sonn- und Feiertage",
		"description": (
			"Sonn- und Feiertage kommen aus der Feiertagsliste des Mitarbeiters "
			"(Feiertagsliste-Zuordnung). Ein Samstag zählt nur, wenn dort ein "
			"Feiertag eingetragen ist."
		),
		"insert_after": "msw_tab_stempelregeln",
	},
	{
		"fieldname": "msw_sonn_feiertag_regel",
		"fieldtype": "Select",
		"label": "Stempelung an Sonn- und Feiertagen",
		"options": f"{SONN_FEIERTAG_ABLEHNEN}\n{SONN_FEIERTAG_NICHT_WERTEN}",
		"default": SONN_FEIERTAG_ABLEHNEN,
		"description": (
			"„Stempelung ablehnen“: Die Stempeluhr zeigt die Meldung unten an, "
			"es wird nichts gespeichert. „Annehmen, aber nicht werten“: Die "
			"Stempelung wird gespeichert, zählt aber nicht als Arbeitszeit "
			"(solange „Allow Workdays on Holidays“ aus ist)."
		),
		"insert_after": "msw_sec_sonn_feiertag",
	},
	{
		"fieldname": "msw_sonn_feiertag_meldung",
		"fieldtype": "Small Text",
		"label": "Meldung an der Stempeluhr",
		"default": MELDUNG_SONN_FEIERTAG,
		"description": "{tag} wird durch den Namen des Feiertags ersetzt, z. B. „Sonntag“ oder „Ostermontag“.",
		"depends_on": f'eval:doc.msw_sonn_feiertag_regel=="{SONN_FEIERTAG_ABLEHNEN}"',
		"insert_after": "msw_sonn_feiertag_regel",
	},
	{
		"fieldname": "msw_sonn_feiertag_hr_ausnahme",
		"fieldtype": "Check",
		"label": "HR Manager und System Manager dürfen trotzdem Stempelungen erfassen",
		"default": "1",
		"description": "Zum Nachtragen genehmigter Sonntags- oder Feiertagsarbeit von Hand.",
		"depends_on": f'eval:doc.msw_sonn_feiertag_regel=="{SONN_FEIERTAG_ABLEHNEN}"',
		"insert_after": "msw_sonn_feiertag_meldung",
	},
	# -- Automatik -----------------------------------------------------
	{
		"fieldname": "msw_sec_automatik",
		"fieldtype": "Section Break",
		"label": "Automatische Berechnung",
		"insert_after": "allow_workdays_on_holidays",
	},
	{
		"fieldname": "msw_sofort_neu_berechnen",
		"fieldtype": "Check",
		"label": "Arbeitstag bei jeder Stempelung sofort neu berechnen",
		"default": "1",
		"description": (
			"Aus: Arbeitstage entstehen nur durch den nächtlichen Lauf, "
			"nachgetragene Stempelungen werden nicht mehr berücksichtigt."
		),
		"insert_after": "msw_sec_automatik",
	},
	{
		"fieldname": "msw_tagesabschluss_aktiv",
		"fieldtype": "Check",
		"label": "Tagesabschluss um 0:30",
		"default": "1",
		"description": (
			"Nimmt die vorläufige Buchung eines Tages zurück, an dem eine "
			"Stempelung fehlt (z. B. Gehen vergessen)."
		),
		"insert_after": "msw_sofort_neu_berechnen",
	},
	{
		"fieldname": "msw_tagesabschluss_tage",
		"fieldtype": "Int",
		"label": "Tagesabschluss: Tage rückwirkend prüfen",
		"default": "7",
		"non_negative": 1,
		"depends_on": "eval:doc.msw_tagesabschluss_aktiv",
		"insert_after": "msw_tagesabschluss_aktiv",
	},
	{
		"fieldname": "msw_fehltage_buchen",
		"fieldtype": "Check",
		"label": "Fehltage mit Minusstunden buchen",
		"default": "1",
		"description": (
			"Ein vergangener Arbeitstag mit Sollzeit, an dem der Mitarbeiter gar nicht "
			"gestempelt hat und keine Abwesenheit eingetragen ist, wird als „Fehlt“ "
			"gebucht: die Sollstunden gehen als Minusstunden ins Zeitkonto. Tage ohne "
			"Sollzeit (z. B. Samstag) ohne Stempelung gelten als „Kein Arbeitstag“."
		),
		"insert_after": "msw_tagesabschluss_tage",
	},
	# -- Urlaub --------------------------------------------------------
	{
		"fieldname": "msw_sec_urlaub",
		"fieldtype": "Section Break",
		"label": "Urlaub",
		"insert_after": "msw_fehltage_buchen",
	},
	{
		"fieldname": "msw_urlaub_nur_sollzeit",
		"fieldtype": "Check",
		"label": "Urlaub nur für Tage mit Sollzeit abziehen",
		"default": "1",
		"description": (
			"Tage, an denen die Sollarbeitszeit des Mitarbeiters 0 Stunden hat oder "
			"für den Wochentag keine Zeile enthält (z. B. Samstag), kosten keinen "
			"Urlaubstag. Gilt für Abwesenheitsarten, bei denen Feiertage nicht "
			"mitgezählt werden. Tage ganz ohne gültige Sollarbeitszeit zählen wie bisher. "
			"Wirkt auf neue und geänderte Anträge."
		),
		"insert_after": "msw_sec_urlaub",
	},
	# -- Oberflaeche ---------------------------------------------------
	{
		"fieldname": "msw_tab_oberflaeche",
		"fieldtype": "Tab Break",
		"label": "Oberfläche",
		"insert_after": "msw_sonn_feiertag_hr_ausnahme",
	},
	{
		"fieldname": "msw_vereinfachte_oberflaeche",
		"fieldtype": "Check",
		"label": "Vereinfachte Oberfläche für die Zeiterfassung",
		"default": "1",
		"description": (
			"Blendet auf dem Desktop die HR-Bereiche aus, die MSW nicht nutzt "
			"(Gehalt, Spesen, Recruiting, Leistung, Steuern, Betriebszugehörigkeit), "
			"ebenso „Abwesenheiten“ und „Schicht & Anwesenheit“ – deren Inhalt steht "
			"im Bereich „Zeiterfassung“. Blendet ungenutzte Einstellungen aus und "
			"ordnet diese Seite in Tabs. Ausschalten stellt den Standard wieder her; "
			"danach die Seite neu laden."
		),
		"insert_after": "msw_tab_oberflaeche",
	},
]

DEFAULTS = {f["fieldname"]: f["default"] for f in FIELDS if "default" in f}
_CASTS = {"Check": int, "Int": int, "Float": float}


def get(fieldname: str):
	"""Wert einer MSW-Einstellung, mit Standardwert als Rueckfall."""
	df = next(f for f in FIELDS if f["fieldname"] == fieldname)
	if not _is_stored(fieldname):
		value = DEFAULTS.get(fieldname)
	else:
		value = frappe.db.get_single_value(SETTINGS, fieldname)
	cast = _CASTS.get(df["fieldtype"])
	if cast and value not in (None, ""):
		return cast(value)
	return value


def _is_stored(fieldname: str) -> bool:
	return bool(
		frappe.db.sql(
			"select 1 from `tabSingles` where doctype=%s and field=%s",
			(SETTINGS, fieldname),
		)
	)


def ensure_module_def():
	"""Module Def fuer "MSW Zeiterfassung" anlegen, falls er fehlt.

	frappe legt Module Defs nur bei der Installation einer App an
	(``installer.add_module_defs``), nicht beim ``migrate``. Ein Modul, das
	spaeter in ``modules.txt`` dazukommt, fehlt damit in der Datenbank --
	Custom Fields mit ``module = MSW Zeiterfassung`` scheitern dann an der
	Link-Pruefung. Haengt an ``before_migrate``; ``setup()`` ruft es zur
	Sicherheit ebenfalls auf.
	"""
	if not frappe.db.exists("Module Def", MODULE):
		frappe.get_doc(
			{"doctype": "Module Def", "module_name": MODULE, "app_name": "hr_addon"}
		).insert(ignore_permissions=True)


def setup():
	"""Custom Fields anlegen/aktualisieren und Standardwerte einmalig setzen."""
	ensure_module_def()
	fields = [dict(f, module=MODULE) for f in FIELDS]
	create_custom_fields({SETTINGS: fields}, update=True)

	for fieldname, default in DEFAULTS.items():
		if not _is_stored(fieldname):
			frappe.db.set_single_value(SETTINGS, fieldname, default)
