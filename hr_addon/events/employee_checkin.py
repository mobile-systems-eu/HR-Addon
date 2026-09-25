"""Workday nachziehen, wenn sich Employee Checkins aendern.

Warum das noetig ist
--------------------
Der geplante Auftrag ``generate_workdays_scheduled_job`` legt Workdays
einmal je Lauf an, arbeitet dabei aber ueber ``get_unmarked_range()`` --
also nur ueber Tage, fuer die **noch kein** Workday existiert. Ein Tag mit
Workday ist damit endgueltig abgeschlossen: kommt die Stempelung erst
spaeter (Stempeluhr war offline, Zeit von Hand nachgetragen), bleibt sie
unberuecksichtigt. Auch ``bulk_process_workdays`` ueberspringt bestehende
Workdays ("Already Exists"), und den Auftrag oefter laufen zu lassen
aendert daran nichts.

``Workday.validate()`` rechnet dagegen vollstaendig neu: ``set_actual_
employee_log()`` holt Stunden, Pausen, Sollzeit, ersten und letzten
Stempel sowie den Status frisch aus den aktuellen Checkins und baut die
Kindtabelle neu auf; danach aktualisiert ``create_attendace_record()`` die
Attendance und die Gleitzeitbuchung. Ein serverseitiges ``save()`` genuegt
also. Nur die Desk-Oberflaeche laesst ein Speichern ohne Aenderung nicht
zu -- das ist eine clientseitige Pruefung im Formular, serverseitig gibt
es sie nicht.

Wie es hier geloest ist
-----------------------
Der Checkin loest die Neuberechnung nicht selbst aus, sondern stellt einen
Hintergrundjob ein:

* **Nach dem Commit** (``enqueue_after_commit``). Die Stempelung ist damit
  festgeschrieben, bevor irgendetwas am Workday passiert. Ein Fehler in
  der Workday-Berechnung darf eine erfasste Arbeitszeit nie verlieren.
* **Als Hintergrundjob**, damit der API-Aufruf der Stempeluhr nicht auf
  Workday, Attendance und Gleitzeitbuchung wartet. Das Terminal hat ein
  Zeitlimit von wenigen Sekunden.
* **Als Administrator.** Das ist Systemarbeit, nicht die des Geraets: das
  Terminal bucht mit einem Service-User, der bewusst nur Rechte auf
  ``Employee Checkin`` hat. ``_create_new_attendance()`` in workday.py
  legt die Attendance ohne ``ignore_permissions`` an und wuerde mit den
  Rechten des Geraets scheitern. Der naechtliche Auftrag laeuft aus
  demselben Grund privilegiert.

Zwischenstand und Tagesabschluss
--------------------------------
Mit gestempelten Pausen ist die Anzahl der Stempel jeden Tag zeitweise
ungerade, der Workday steht dann auf ``Missing Checkin``. Tagsueber bleibt
die Buchung aus den vollstaendigen Paaren deshalb als Zwischenstand stehen;
der naechste gerade Stempel aktualisiert sie an Ort und Stelle. Storniert
wird erst, wenn der Tag vorbei ist -- sonst gaebe es jeden Tag eine
stornierte Attendance und eine Gegenbuchung.

Ist ein Tag danach immer noch ungerade (Gehen vergessen), raeumt
``close_past_workdays`` um 0:30 die Teilbuchung ab. Der Auftrag des Addons
kann das nicht: er schliesst ``heute`` in seinen Zeitraum ein, legt den
Workday um 0 Uhr fuer den neuen Tag an und fasst ihn danach nie wieder an.
"""

import frappe
from frappe.utils import add_days, getdate, today

from hr_addon.msw_zeiterfassung import einstellungen

JOB_QUEUE = "short"
JOB_TIMEOUT = 600

TAGE_RUECKWIRKEND = 7
"""Standard fuer die Einstellung ``msw_tagesabschluss_tage``: so weit schaut
der Tagesabschluss zurueck. Faellt ein Lauf aus (Server aus, Worker
haengt), holt der naechste ihn nach."""

STATUS_OHNE_BUCHUNG = ("Missing Checkin", "Absent")
"""Workday-Status, bei denen ``create_attendace_record()`` ohne jede
Aenderung zurueckkehrt (``else: return``). Eine Attendance, die der Workday
frueher am Tag angelegt hat, bliebe dann mit dem alten Wert stehen."""

REENTRY_FLAG = "hr_addon_workday_sync"
"""Schutz gegen Wiedereintritt. Derzeit kann keine Schleife entstehen --
``set_attendance_in_employee_checkins()`` speichert den Checkin voll
(``checkin_doc.save()``), was ``on_update`` ausloest, und dort filtern wir
auf eine tatsaechliche Aenderung von ``time``. Das Flag ist die zweite
Sicherung, falls jemand spaeter einen weiteren Hook ergaenzt."""


# -- Hooks -----------------------------------------------------------------


def revalidate_workday_after_insert(doc, method=None):
    """Neue Stempelung: Workday anlegen oder neu rechnen."""
    _enqueue(doc.employee, doc.time)


def revalidate_workday_on_trash(doc, method=None):
    """Geloeschte Stempelung: Workday ohne sie neu rechnen."""
    _enqueue(doc.employee, doc.time)


def revalidate_workday_on_update(doc, method=None):
    """Geaenderte Stempelung -- aber nur, wenn Zeit oder Mitarbeiter
    betroffen sind.

    Ohne diese Einschraenkung wuerde jeder Lauf sich selbst neu anstossen:
    ``create_attendace_record()`` schreibt das Feld ``attendance`` per
    vollem ``save()`` in die Checkins zurueck.
    """
    zeit_geaendert = doc.has_value_changed("time")
    mitarbeiter_geaendert = doc.has_value_changed("employee")
    if not zeit_geaendert and not mitarbeiter_geaendert:
        return

    if mitarbeiter_geaendert:
        # Der alte Mitarbeiter behaelt sonst eine Arbeitszeit, die ihm
        # nicht mehr gehoert.
        vorher = doc.get_doc_before_save()
        if vorher:
            _enqueue(vorher.employee, vorher.time)

    _enqueue(doc.employee, doc.time)


def _enqueue(employee, zeitpunkt):
    if not employee or not zeitpunkt:
        return
    if frappe.flags.get(REENTRY_FLAG):
        return
    if not einstellungen.get("msw_sofort_neu_berechnen"):
        return

    frappe.enqueue(
        "hr_addon.events.employee_checkin.sync_workday",
        queue=JOB_QUEUE,
        timeout=JOB_TIMEOUT,
        enqueue_after_commit=True,
        employee=employee,
        log_date=str(getdate(zeitpunkt)),
    )


# -- Die eigentliche Arbeit ------------------------------------------------


def sync_workday(employee: str, log_date: str) -> None:
    """Workday zu diesem Tag anlegen oder neu rechnen.

    Bewusst ohne Deduplizierung mehrerer Jobs: die Arbeit ist idempotent
    (es wird immer aus dem aktuellen Stand gerechnet), und ein
    uebersprungener Job waere genau der Datenverlust, den dieser Hook
    verhindern soll.
    """
    from hr_addon.hr_addon.doctype.workday.workday import (
        has_valid_weekly_working_hours,
    )

    # Denselben Schalter beachten wie der geplante Auftrag.
    if not frappe.db.get_single_value("HR Addon Settings", "enabled"):
        return

    datum = getdate(log_date)
    urspruenglicher_benutzer = frappe.session.user
    frappe.flags[REENTRY_FLAG] = True
    frappe.set_user("Administrator")
    try:
        name = frappe.db.get_value(
            "Workday", {"employee": employee, "log_date": datum}, "name"
        )
        if name:
            workday = frappe.get_doc("Workday", name)
            workday.save()
            if datum < getdate(today()):
                # Heute ist ein ungerader Stand der Normalfall (Pause
                # laeuft), siehe "Zwischenstand und Tagesabschluss".
                _cancel_stale_attendance(workday)
            frappe.db.commit()
            return

        if not has_valid_weekly_working_hours(employee, datum):
            # Ohne submittete Weekly Working Hours wuerde
            # Workday.validate() eine Ausnahme werfen. Kein Fehler,
            # sondern eine Konfigurationsfrage am Mitarbeiter.
            return

        workday = frappe.new_doc("Workday")
        workday.employee = employee
        workday.company = frappe.db.get_value("Employee", employee, "company")
        workday.log_date = datum
        workday.save()
        frappe.db.commit()
    finally:
        frappe.set_user(urspruenglicher_benutzer)
        frappe.flags.pop(REENTRY_FLAG, None)


def _cancel_stale_attendance(workday) -> None:
    """Attendance stornieren, die nach der Neuberechnung nicht mehr stimmt.

    Beispiel: Kommen 6:00, Pause 9:00 -- der Workday ist ``Present`` mit
    3 h, Attendance und Gleitzeitbuchung entstehen. Mit dem dritten Stempel
    (oder wenn einer geloescht wird) ist die Anzahl ungerade, der Workday
    steht auf ``Missing Checkin`` und null Stunden. ``create_attendace_
    record()`` laesst die Attendance dann unberuehrt, das Konto behielte
    die 3 h. Vergisst der Mitarbeiter das Gehen, bliebe diese Teilbuchung
    dauerhaft -- der naechtliche Auftrag fasst Tage mit Workday nicht an.

    Storniert wird wie beim Loeschen des Workdays (``on_trash`` ->
    ``cancel_attendance``): ``Attendance.cancel()`` bucht die Gleitzeit per
    Gegenbuchung zurueck und loest die Verknuepfung am Workday. Kommt der
    fehlende Stempel spaeter, legt der naechste Lauf eine neue Attendance
    an.

    Bewusst eng gefasst: nur Attendances, die dieser Workday selbst
    angelegt hat (``custom_workday``), und nur ``Present``. Urlaubs- und
    Halbtags-Attendances aus einer Leave Application bleiben unangetastet.
    """
    if workday.status not in STATUS_OHNE_BUCHUNG:
        return

    namen = frappe.get_all(
        "Attendance",
        filters={
            "custom_workday": workday.name,
            "docstatus": 1,
            "status": "Present",
        },
        pluck="name",
    )
    for name in namen:
        frappe.get_doc("Attendance", name).cancel()


# -- Tagesabschluss --------------------------------------------------------


def close_past_workdays() -> None:
    """Teilbuchungen vergangener Tage abraeumen (Cron 0:30).

    Sucht Workdays der letzten ``msw_tagesabschluss_tage`` Tage vor heute, die
    auf einem Status ohne Buchung stehen, aber noch eine eigene
    ``Present``-Attendance tragen -- typisch: Gehen vergessen. Fuer diese
    Tage laeuft ``sync_workday()``, rechnet neu und storniert, falls der
    Tag weiterhin ungerade ist. Ausserdem Fehltage (``Absent`` mit
    Sollzeit) ohne Anwesenheit: das Speichern bucht sie
    (``msw_zeiterfassung/fehltage.py``).

    Bewusst nicht jeden Workday neu speichern: die Checkin-Hooks halten
    sie ohnehin aktuell, und der Auftrag soll nur das Abschliessen
    nachholen, das tagsueber absichtlich unterbleibt.
    """
    if not frappe.db.get_single_value("HR Addon Settings", "enabled"):
        return
    if not einstellungen.get("msw_tagesabschluss_aktiv"):
        return

    tage = einstellungen.get("msw_tagesabschluss_tage") or TAGE_RUECKWIRKEND
    heute = getdate(today())
    workdays = frappe.get_all(
        "Workday",
        filters={
            "status": ["in", STATUS_OHNE_BUCHUNG],
            "log_date": ["between", [add_days(heute, -tage), add_days(heute, -1)]],
        },
        fields=["name", "employee", "log_date", "status", "target_hours"],
    )

    from hr_addon.msw_zeiterfassung import fehltage

    for wd in workdays:
        teilbuchung = frappe.db.exists(
            "Attendance",
            {"custom_workday": wd.name, "docstatus": 1, "status": "Present"},
        )
        # Fehltag ohne Buchung nachholen (msw_zeiterfassung/fehltage.py),
        # z. B. wenn der Workday vor dem Einschalten entstanden ist
        fehltag_offen = (
            fehltage.aktiv()
            and wd.status == "Absent"
            and (wd.target_hours or 0) > 0
            and not frappe.db.exists(
                "Attendance",
                {"employee": wd.employee, "attendance_date": wd.log_date, "docstatus": 1},
            )
        )
        if not teilbuchung and not fehltag_offen:
            continue
        try:
            sync_workday(wd.employee, str(wd.log_date))
        except Exception:
            # Ein Tag darf die uebrigen nicht blockieren, z.B. wenn er
            # inzwischen im eingefrorenen Zeitraum liegt.
            frappe.db.rollback()
            frappe.log_error(
                title="Tagesabschluss Workday",
                message=f"Workday {wd.name} ({wd.employee}, {wd.log_date})\n\n"
                + frappe.get_traceback(),
            )
