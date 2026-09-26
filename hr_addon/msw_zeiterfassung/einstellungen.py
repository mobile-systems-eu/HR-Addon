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

ABLEHNEN = "Stempelung ablehnen"
ANNEHMEN = "Stempelung annehmen"

MELDUNG_FEIERTAG = "{tag}: An Feiertagen kann nicht gestempelt werden. Bitte im Büro melden."
MELDUNG_OHNE_SOLLZEIT = (
	"{tag}: Für diesen Tag ist keine Arbeitszeit vorgesehen. Bitte im Büro melden."
)

# Felder frueherer Staende; setup() loescht sie samt Wert.
OBSOLETE_FIELDS = (
	"msw_sec_sonn_feiertag",
	"msw_sonn_feiertag_regel",
	"msw_sonn_feiertag_meldung",
	"msw_sonn_feiertag_hr_ausnahme",
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
		"fieldname": "msw_sec_feiertag",
		"fieldtype": "Section Break",
		"label": "Feiertage",
		"description": (
			"Feiertage kommen aus der Feiertagsliste des Mitarbeiters "
			"(Feiertagsliste-Zuordnung)."
		),
		"insert_after": "msw_tab_stempelregeln",
	},
	{
		"fieldname": "msw_feiertag_regel",
		"fieldtype": "Select",
		"label": "Stempelung an Feiertagen",
		"options": f"{ABLEHNEN}\n{ANNEHMEN}",
		"default": ABLEHNEN,
		"description": (
			"„Stempelung ablehnen“: Die Stempeluhr zeigt die Meldung unten an, es wird "
			"nichts gespeichert. „Stempelung annehmen“: Die Stempelung wird gespeichert; "
			"als Arbeitszeit zählt sie nur, wenn „Arbeitstage an Feiertagen zulassen“ an ist."
		),
		"insert_after": "msw_sec_feiertag",
	},
	{
		"fieldname": "msw_feiertag_meldung",
		"fieldtype": "Small Text",
		"label": "Meldung an der Stempeluhr",
		"default": MELDUNG_FEIERTAG,
		"description": "{tag} wird durch den Namen des Feiertags ersetzt, z. B. „Ostermontag“.",
		"depends_on": f'eval:doc.msw_feiertag_regel=="{ABLEHNEN}"',
		"insert_after": "msw_feiertag_regel",
	},
	{
		"fieldname": "msw_sec_ohne_sollzeit",
		"fieldtype": "Section Break",
		"label": "Tage ohne Sollarbeitszeit",
		"description": (
			"Gemeint sind Wochentage, für die die Sollarbeitszeit des Mitarbeiters keine "
			"Zeile enthält (bei MSW der Sonntag). Eine Zeile mit 0 Stunden (Samstag) ist "
			"ein Eintrag: dort kann gestempelt werden. Mitarbeiter ohne gültige "
			"Sollarbeitszeit werden nicht abgelehnt."
		),
		"insert_after": "msw_feiertag_meldung",
	},
	{
		"fieldname": "msw_ohne_sollzeit_regel",
		"fieldtype": "Select",
		"label": "Stempelung an Tagen ohne Sollarbeitszeit",
		"options": f"{ABLEHNEN}\n{ANNEHMEN}",
		"default": ABLEHNEN,
		"description": (
			"„Stempelung annehmen“: Die Stempelung wird gespeichert, zählt aber nicht als "
			"Arbeitszeit, weil für den Tag kein Arbeitstag angelegt werden kann."
		),
		"insert_after": "msw_sec_ohne_sollzeit",
	},
	{
		"fieldname": "msw_ohne_sollzeit_meldung",
		"fieldtype": "Small Text",
		"label": "Meldung an der Stempeluhr",
		"default": MELDUNG_OHNE_SOLLZEIT,
		"description": "{tag} wird durch den Wochentag ersetzt, z. B. „Sonntag“.",
		"depends_on": f'eval:doc.msw_ohne_sollzeit_regel=="{ABLEHNEN}"',
		"insert_after": "msw_ohne_sollzeit_regel",
	},
	{
		"fieldname": "msw_sec_stempel_ausnahme",
		"fieldtype": "Section Break",
		"label": "Ausnahme",
		"insert_after": "msw_ohne_sollzeit_meldung",
	},
	{
		"fieldname": "msw_stempel_hr_ausnahme",
		"fieldtype": "Check",
		"label": "HR Manager und System Manager dürfen trotzdem Stempelungen erfassen",
		"default": "1",
		"description": "Gilt für beide Regeln. Zum Nachtragen genehmigter Sonntags- oder Feiertagsarbeit von Hand.",
		"insert_after": "msw_sec_stempel_ausnahme",
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
		"insert_after": "msw_stempel_hr_ausnahme",
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

	for fieldname in OBSOLETE_FIELDS:
		name = frappe.db.get_value("Custom Field", {"dt": SETTINGS, "fieldname": fieldname})
		if name:
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
		frappe.db.delete("Singles", {"doctype": SETTINGS, "field": fieldname})

	for fieldname, default in DEFAULTS.items():
		if not _is_stored(fieldname):
			frappe.db.set_single_value(SETTINGS, fieldname, default)
