from . import __version__ as app_version

app_name = "hibiscus_connect"
app_title = "Hibiscus Connect"
app_publisher = "itsdave GmbH"
app_description = "Austausch zu der Onlinebanking-Software Hibiscus"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "dev@itsdave.de"
app_license = "MIT"

# Installation
# ------------

after_install = "hibiscus_connect.install.after_install"
after_migrate = "hibiscus_connect.install.after_migrate"

# Permissions
# -----------

permission_query_conditions = {
	"Hibiscus Connect Bank Account": "hibiscus_connect.permissions.bank_account_query_conditions",
	"Hibiscus Connect Transaction": "hibiscus_connect.permissions.transaction_query_conditions",
}

has_permission = {
	"Hibiscus Connect Bank Account": "hibiscus_connect.permissions.has_bank_account_permission",
	"Hibiscus Connect Transaction": "hibiscus_connect.permissions.has_transaction_permission",
}

# Document Events
# ---------------

doc_events = {
	"Sales Invoice": {
		"on_submit":"hibiscus_connect.tools.create_debit_charge"
	},
	"User": {
		"on_update": "hibiscus_connect.permissions.sync_bank_permissions_for_user"
	}
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"hourly": [
		"hibiscus_connect.tasks.fetch_transactions_from_active_accounts",
		"hibiscus_connect.tasks.refresh_lastschrift_cache",
		"hibiscus_connect.tasks.refresh_ueberweisung_cache"
	]
}

# Fixtures
# --------

fixtures = [
	"Hibiscus Connect Transaction Category",
	"GVCode Mapping",
	"Booking Category",
	{"dt": "Custom HTML Block", "filters": [["name", "=", "SEPA Lastschrift Dashboard"]]}
]
