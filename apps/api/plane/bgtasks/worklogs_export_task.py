# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import csv
import io
from io import BytesIO

import boto3
from botocore.client import Config
from celery import shared_task
from django.conf import settings
from openpyxl import Workbook

# Module imports
from plane.db.models import ExporterHistory, IssueWorkLog
from plane.utils.exception_logger import log_exception


def date_converter(time):
    if time:
        return time.strftime("%a, %d %b %Y")
    return ""


def create_csv_file(data):
    csv_buffer = io.StringIO()
    csv_writer = csv.writer(csv_buffer, delimiter=",", quoting=csv.QUOTE_ALL)
    for row in data:
        csv_writer.writerow(row)
    csv_buffer.seek(0)
    bytes_csv_buffer = io.BytesIO(csv_buffer.getvalue().encode("utf-8"))
    bytes_csv_buffer.seek(0)
    return bytes_csv_buffer


def create_xlsx_file(data):
    xlsx_buffer = io.BytesIO()
    workbook = Workbook()
    sheet = workbook.active
    for row in data:
        sheet.append(row)
    workbook.save(xlsx_buffer)
    xlsx_buffer.seek(0)
    return xlsx_buffer


def upload_to_s3(files, workspace_id, token_id, slug, provider):
    expires_in = 7 * 24 * 60 * 60
    file_name, file_obj = files[0]
    file_obj = BytesIO(file_obj.read())
    object_key = f"{workspace_id}/worklogs-export-{slug}-{token_id[:6]}.{provider}"

    if settings.USE_MINIO:
        upload_s3 = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
        )
        upload_s3.upload_fileobj(
            file_obj,
            settings.AWS_STORAGE_BUCKET_NAME,
            object_key,
            ExtraArgs={"ContentType": f"application/{provider}"},
        )
        presign_s3 = boto3.client(
            "s3",
            endpoint_url=(
                f"{settings.AWS_S3_URL_PROTOCOL}//"
                f"{str(settings.AWS_S3_CUSTOM_DOMAIN).replace('/uploads', '')}/"
            ),
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
        )
        presigned_url = presign_s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": object_key},
            ExpiresIn=expires_in,
        )
    else:
        if settings.AWS_S3_ENDPOINT_URL:
            s3 = boto3.client(
                "s3",
                endpoint_url=settings.AWS_S3_ENDPOINT_URL,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                config=Config(signature_version="s3v4"),
            )
        else:
            s3 = boto3.client(
                "s3",
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                config=Config(signature_version="s3v4"),
            )
        s3.upload_fileobj(
            file_obj,
            settings.AWS_STORAGE_BUCKET_NAME,
            object_key,
            ExtraArgs={"ContentType": f"application/{provider}"},
        )
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": object_key},
            ExpiresIn=expires_in,
        )

    exporter_instance = ExporterHistory.objects.get(token=token_id)
    if presigned_url:
        exporter_instance.url = presigned_url
        exporter_instance.status = "completed"
        exporter_instance.key = object_key
    else:
        exporter_instance.status = "failed"
    exporter_instance.save(update_fields=["status", "url", "key"])


def generate_table_row(worklog):
    return [
        worklog["project__name"],
        f"{worklog['project__identifier']}-{worklog['issue__sequence_id']} {worklog['issue__name']}",
        (
            f"{worklog['logged_by__first_name']} {worklog['logged_by__last_name']}".strip()
            if worklog.get("logged_by__first_name") or worklog.get("logged_by__last_name")
            else worklog.get("logged_by__display_name") or ""
        ),
        date_converter(worklog["created_at"]),
        worklog["duration"],
    ]


@shared_task
def worklogs_export_task(provider, workspace_id, user_id, token_id, slug, filters):
    try:
        exporter_instance = ExporterHistory.objects.get(token=token_id)
        exporter_instance.status = "processing"
        exporter_instance.save(update_fields=["status"])

        filters = filters or {}
        worklogs = (
            IssueWorkLog.objects.filter(
                project__project_projectmember__member_id=user_id,
                project__project_projectmember__is_active=True,
                project__archived_at__isnull=True,
                workspace__slug=slug,
            )
            .filter(**filters)
            .order_by("project__identifier", "issue__sequence_id")
            .select_related("logged_by", "issue", "project", "workspace")
            .values(
                "id",
                "duration",
                "project",
                "workspace",
                "logged_by__first_name",
                "logged_by__last_name",
                "logged_by__display_name",
                "issue__name",
                "issue__sequence_id",
                "project__identifier",
                "created_at",
                "project__name",
            )
            .distinct()
        )

        header = ["Project", "Issue", "Logged by", "Logged On", "Duration"]
        rows = [header] + [generate_table_row(w) for w in worklogs]

        files = []
        if provider == "csv":
            files.append((f"{workspace_id}.csv", create_csv_file(rows)))
        elif provider == "xlsx":
            files.append((f"{workspace_id}.xlsx", create_xlsx_file(rows)))
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        upload_to_s3(files, workspace_id, token_id, slug, provider)
    except Exception as e:
        exporter_instance = ExporterHistory.objects.get(token=token_id)
        exporter_instance.status = "failed"
        exporter_instance.reason = str(e)
        exporter_instance.save(update_fields=["status", "reason"])
        log_exception(e)
