# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract-license feature flag helpers used by GraphQL / mobile."""

import os


def is_contract_license_enabled() -> bool:
    return os.environ.get("CONTRACT_LICENSE_ENABLED", "0") == "1"


def get_contract_feature_flags() -> dict:
    """
    Return a single-workspace feature-flag map.
    When contract mode is on we enable core Business flags the mobile app expects.
    """
    enabled = is_contract_license_enabled()
    flags = {
        "BULK_OPS": enabled,
        "BULK_OPS_ADVANCED": enabled,
        "COLLABORATION_CURSOR": enabled,
        "EDITOR_AI_OPS": enabled,
        "ESTIMATE_WITH_TIME": enabled,
        "ISSUE_TYPE_DISPLAY": enabled,
        "ISSUE_TYPE_SETTINGS": enabled,
        "OIDC_SAML_AUTH": False,
        "PAGE_ISSUE_EMBEDS": enabled,
        "PAGE_PUBLISH": enabled,
        "VIEW_ACCESS_PRIVATE": enabled,
        "VIEW_LOCK": enabled,
        "VIEW_PUBLISH": enabled,
        "WORKSPACE_ACTIVE_CYCLES": enabled,
        "WORKSPACE_PAGES": enabled,
        "ISSUE_WORKLOG": enabled,
        "PROJECT_GROUPING": enabled,
        "ACTIVE_CYCLE_PRO": enabled,
        "NO_LOAD": False,
        "FILE_SIZE_LIMIT_PRO": enabled,
        "PI_CHAT": enabled,
        "PI_DEDUPE": enabled,
        "SILO_IMPORTERS": False,
        "SILO_INTEGRATIONS": False,
        "JIRA_IMPORTER": False,
        "JIRA_ISSUE_TYPES_IMPORTER": False,
        "LINEAR_IMPORTER": False,
        "LINEAR_TEAMS_IMPORTER": False,
        "ASANA_IMPORTER": False,
        "ASANA_ISSUE_PROPERTIES_IMPORTER": False,
        "GITHUB_INTEGRATION": False,
        "GITLAB_INTEGRATION": False,
        "SLACK_INTEGRATION": False,
        "PI_CHAT_MOBILE": enabled,
        "PI_DEDUPE_MOBILE": enabled,
        # Newer commercial mobile flags — off unless product enables them
        "TIMELINE_DEPENDENCY": False,
        "INBOX_STACKING": False,
        "EPICS": False,
        "NESTED_PAGES": False,
        "TEAMSPACES": False,
    }
    # Shape expected by GraphQL: iterable of one map (`.values()` used on dict of maps)
    return {"default": flags}
