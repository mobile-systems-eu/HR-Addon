from . import __version__ as app_version

app_name = "hr_addon"
app_title = "HR Addon"
app_publisher = "phamos.eu"
app_description = "Addon for Erpnext attendance and employee checkins"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "support@phamos.eu"
app_license = "MIT"

after_install = "hr_addon.hr_addon.doctype.workday.workday.create_background_job_for_workday_generation_after_install"
after_migrate = [
	"hr_addon.hr_addon.doctype.workday.workday.create_background_job_for_workday_generation_after_install",
	# MSW: Einstellungsfelder der Zeiterfassung, siehe msw_zeiterfassung/einstellungen.py
	"hr_addon.msw_zeiterfassung.einstellungen.setup",
	# MSW: vereinfachte Oberflaeche (abschaltbar), siehe msw_zeiterfassung/oberflaeche.py
	"hr_addon.msw_zeiterfassung.oberflaeche.after_migrate",
]

# MSW: HR-Bereiche ausblenden, die nicht genutzt werden (abschaltbar)
boot_session = "hr_addon.msw_zeiterfassung.oberflaeche.boot_session"

fixtures = [
	{"dt": "Custom Field", "filters": [
		["module", "=", "HR Addon"]
	]},
    {
        "dt": "DocType Link",
        "filters": [
            ["parenttype", "=", "DocType"],
            ["parent", "in", ["Employee","Attendance"]],
        ]
    },
]
doctype_js = {
	"HR Settings" : "public/js/hr_settings.js",
	"Employee": "public/js/employee.js",
	"Leave Application": "public/js/leave_application.js",
	"Attendance": "public/js/attendance.js",
}

required_apps = ["hrms"]

doc_events = {
	# MSW: Schalter "Vereinfachte Oberflaeche" sofort wirksam machen
	"HR Addon Settings": {
		"on_update": "hr_addon.msw_zeiterfassung.oberflaeche.nach_speichern",
	},
	"Leave Application": {
		"validate": "hr_addon.events.leave_application.validate_leave_application",
		"on_change": "hr_addon.hr_addon.doctype.hr_addon_settings.hr_addon_settings.export_calendar",
		"on_cancel": [
			"hr_addon.hr_addon.doctype.hr_addon_settings.hr_addon_settings.export_calendar",
			"hr_addon.events.leave_application.restore_overtime_on_leave_cancel",
		],
		"on_submit": "hr_addon.events.leave_application.reduce_overtime_on_leave_submit",
	},
	"Attendance": {
		"on_submit": "hr_addon.events.attendance.create_overtime_ledger_entry_on_attendance_submit",
		"on_cancel": [
			"hr_addon.events.attendance.cancel_overtime_ledger_entry_on_attendance_cancel",
			"hr_addon.events.attendance.clear_workday_reference_on_attendance_trash",
		],
		"on_trash": "hr_addon.events.attendance.clear_workday_reference_on_attendance_trash",
	},
	"Overtime Ledger Entry": {
		"after_insert": "hr_addon.events.overtime_ledger.after_insert_overtime_ledger_entry",
	},
	# MSW: Der geplante Auftrag arbeitet nur ueber Tage OHNE Workday
	# (get_unmarked_range). Eine Stempelung, die erst nach dem Lauf
	# ankommt -- Stempeluhr war offline, Zeit von Hand nachgetragen --
	# blieb damit unberuecksichtigt. Siehe events/employee_checkin.py.
	"Employee Checkin": {
		# MSW: Sonn-/Feiertag ablehnen, siehe msw_zeiterfassung/stempelregeln.py
		"before_insert": "hr_addon.msw_zeiterfassung.stempelregeln.pruefe_neue_stempelung",
		"after_insert": "hr_addon.events.employee_checkin.revalidate_workday_after_insert",
		"on_update": "hr_addon.events.employee_checkin.revalidate_workday_on_update",
		"on_trash": "hr_addon.events.employee_checkin.revalidate_workday_on_trash",
	},
}

scheduler_events = {
	"yearly": [
		"hr_addon.hr_addon.doctype.weekly_working_hours.weekly_working_hours.set_from_to_dates",
	],
	"daily": [
		"hr_addon.hr_addon.doctype.hr_addon_settings.hr_addon_settings.send_work_anniversary_notification",
		"hr_addon.hr_addon.doctype.hr_addon_settings.hr_addon_settings.repost_all_overtime_ledger_entries",
	],
	# MSW: Tagesabschluss nach dem Stempelfenster (Sa bis 24:00). Raeumt
	# Teilbuchungen von Tagen ab, die ungerade geendet haben. Siehe
	# events/employee_checkin.py, "Zwischenstand und Tagesabschluss".
	"cron": {
		"30 0 * * *": [
			"hr_addon.events.employee_checkin.close_past_workdays",
		],
	},
}

override_doctype_class = {
	"Leave Application": "hr_addon.overrides.custom_leave_application.HrAddonLeaveApplication",
}