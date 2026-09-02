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
"""

import frappe
from frappe.utils import getdate

JOB_QUEUE = "short"
JOB_TIMEOUT = 600

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
            frappe.get_doc("Workday", name).save()
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
