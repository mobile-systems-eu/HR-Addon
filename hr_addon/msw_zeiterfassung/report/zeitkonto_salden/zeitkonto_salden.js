frappe.query_reports["Zeitkonto-Salden"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "stichtag",
			label: "Stichtag",
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "leave_type",
			label: "Resturlaub für",
			fieldtype: "Link",
			options: "Leave Type",
			default: "Urlaub",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (["saldo", "veraenderung", "saldo_monatsbeginn"].includes(column.fieldname) && data) {
			const zahl = data[column.fieldname];
			if (zahl < 0) value = `<span style="color: var(--red-600)">${value}</span>`;
		}
		return value;
	},
};
