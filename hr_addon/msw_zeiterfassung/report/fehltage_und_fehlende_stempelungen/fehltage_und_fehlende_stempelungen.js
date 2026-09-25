frappe.query_reports["Fehltage und fehlende Stempelungen"] = {
	filters: [
		{
			fieldname: "from_date",
			label: "Von",
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -30),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: "Bis",
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "art",
			label: "Art",
			fieldtype: "Select",
			options: "\nFehlt\nStempelung fehlt",
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "art" && data) {
			const farbe = data.art === "Fehlt" ? "var(--red-600)" : "var(--orange-600)";
			value = `<span style="color: ${farbe}; font-weight: 600">${value}</span>`;
		}
		return value;
	},
};
