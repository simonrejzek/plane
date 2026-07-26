import os


BUSINESS_FEATURE_FLAGS = {
    "ACTIVE_CYCLE_PRO": True,
    "ASANA_IMPORTER": True,
    "ASANA_ISSUE_PROPERTIES_IMPORTER": True,
    "BULK_OPS": True,
    "BULK_OPS_ADVANCED": True,
    "COLLABORATION_CURSOR": True,
    "ESTIMATE_WITH_TIME": True,
    "FILE_SIZE_LIMIT_PRO": True,
    "GITHUB_INTEGRATION": True,
    "GITLAB_INTEGRATION": True,
    "INTAKE_SETTINGS": True,
    "ISSUE_TYPE_DISPLAY": True,
    "ISSUE_TYPE_SETTINGS": True,
    "ISSUE_WORKLOG": True,
    "JIRA_IMPORTER": True,
    "JIRA_ISSUE_TYPES_IMPORTER": True,
    "LINEAR_IMPORTER": True,
    "LINEAR_TEAMS_IMPORTER": True,
    "PAGE_ISSUE_EMBEDS": True,
    "PAGE_PUBLISH": True,
    "PROJECT_GROUPING": True,
    "SILO_ASANA_INTEGRATION": True,
    "SILO_GITHUB_INTEGRATION": True,
    "SILO_GITLAB_INTEGRATION": True,
    "SILO_IMPORTERS": True,
    "SILO_INTEGRATION": True,
    "SILO_INTEGRATIONS": True,
    "SILO_JIRA_INTEGRATION": True,
    "SILO_LINEAR_INTEGRATION": True,
    "SLACK_INTEGRATION": True,
    "TIMELINE_DEPENDENCY": True,
    "VIEW_ACCESS_PRIVATE": True,
    "VIEW_LOCK": True,
    "VIEW_LOCKING": True,
    "VIEW_PUBLISH": True,
    "WORKSPACE_ACTIVE_CYCLES": True,
    "WORKSPACE_PAGES": True,
}


def is_contract_license_enabled():
    return os.environ.get("CONTRACT_LICENSE_ENABLED", "0") == "1"


def get_contract_feature_flags():
    return {"values": BUSINESS_FEATURE_FLAGS.copy()}


def get_contract_workspace_license():
    # Plane 0.23.1 predates the BUSINESS enum. ENTERPRISE is the compatibility
    # value that makes its commercial UI treat a contract workspace as paid.
    return {
        "current_period_end_date": "2099-12-31T23:59:59Z",
        "current_period_start_date": "2024-01-01T00:00:00Z",
        "free_seats": 100000,
        "has_activated_free_trial": False,
        "has_added_payment_method": True,
        "interval": "YEARLY",
        "is_cancelled": False,
        "is_offline_payment": True,
        "plan": "ENTERPRISE",
        "purchased_seats": 100000,
        "subscription": "contract-business",
        "trial_end_date": None,
    }
