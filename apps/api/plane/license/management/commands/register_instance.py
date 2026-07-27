# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import json
import secrets
import os
import requests

# Django imports
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


# Module imports
from plane.license.models import Instance, InstanceEdition
from plane.license.bgtasks.telemetry_metrics import push_instance_metrics


class Command(BaseCommand):
    help = "Check if instance in registered else register"

    def add_arguments(self, parser):
        # Positional argument
        parser.add_argument("machine_signature", type=str, help="Machine signature")

    def check_for_current_version(self):
        if os.environ.get("APP_VERSION", False):
            return os.environ.get("APP_VERSION")

        try:
            with open("package.json", "r") as file:
                data = json.load(file)
                return data.get("version", "v0.1.0")
        except Exception:
            self.stdout.write("Error checking for current version")
            return "v0.1.0"

    def check_for_latest_version(self, fallback_version):
        # Contract-licensed self-hosted instances do not need to contact
        # Plane's release service. Keep the normal community behavior intact.
        if os.environ.get("CONTRACT_LICENSE_ENABLED", "0") == "1":
            return fallback_version

        try:
            response = requests.get(
                "https://api.github.com/repos/makeplane/plane/releases/latest",
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("tag_name", fallback_version)
        except Exception:
            self.stdout.write("Error checking for latest version")
            return fallback_version

    def handle(self, *args, **options):
        # Check if the instance is registered
        instance = Instance.objects.first()

        current_version = self.check_for_current_version()
        latest_version = self.check_for_latest_version(current_version)

        contract_license_enabled = os.environ.get("CONTRACT_LICENSE_ENABLED", "0") == "1"
        configured_edition = os.environ.get(
            "CONTRACT_LICENSE_EDITION",
            InstanceEdition.PLANE_BUSINESS.value,
        )
        edition = (
            configured_edition
            if contract_license_enabled and configured_edition in {
                InstanceEdition.PLANE_BUSINESS.value,
                InstanceEdition.PLANE_COMMUNITY.value,
            }
            else InstanceEdition.PLANE_COMMUNITY.value
        )

        # If instance is None then register this instance
        if instance is None:
            machine_signature = options.get("machine_signature", "machine-signature")

            if not machine_signature:
                raise CommandError("Machine signature is required")

            instance = Instance.objects.create(
                instance_name="Plane Business Edition" if edition == InstanceEdition.PLANE_BUSINESS.value else "Plane Community Edition",
                instance_id=secrets.token_hex(12),
                current_version=current_version,
                latest_version=latest_version,
                last_checked_at=timezone.now(),
                is_test=os.environ.get("IS_TEST", "0") == "1",
                edition=edition,
            )

            self.stdout.write(self.style.SUCCESS("Instance registered"))
        else:
            self.stdout.write(self.style.SUCCESS("Instance already registered"))

            # Update the instance details
            instance.last_checked_at = timezone.now()
            instance.current_version = current_version
            instance.latest_version = latest_version
            instance.is_test = os.environ.get("IS_TEST", "0") == "1"
            instance.edition = edition
            instance.save()

        # Contract-licensed self-hosted instances are intentionally offline
        # from Plane-hosted telemetry and registration services.
        if not contract_license_enabled:
            push_instance_metrics.delay()

        return
