#!/usr/bin/env python3
r"""
Replace a keyword in the Zanata document `hellocash`.

Targets:
  Server:   https://zanata.vitabirr.com/zanata/rest
  Project:  hellocash
  Version:  hellocash_newussdmenu
  Document: hellocash

Use --locale-id to choose which language to edit:
  en-US  -> English source strings
  am-ET  -> Amharic translations

Authentication (required for writes):
  Linux/macOS:
    export ZANATA_USER="your-username"
    export ZANATA_TOKEN="your-api-key"

  Windows (CMD):
    set ZANATA_USER=your-username
    set ZANATA_TOKEN=your-api-key

  Windows (PowerShell):
    $env:ZANATA_USER = "your-username"
    $env:ZANATA_TOKEN = "your-api-key"

Usage:
  Linux/macOS:
    python3 scripts/zanata_replace_keyword.py --locale-id en-US --find "HelloCash" --replace "VitaBirr" --dry-run
    python3 scripts/zanata_replace_keyword.py --locale-id am-ET --find "HelloCash" --replace "VitaBirr" --dry-run

  Windows (CMD):
    scripts\zanata_replace_keyword.bat --locale-id am-ET --find "HelloCash" --replace "VitaBirr" --dry-run

  Windows (PowerShell):
    py scripts\zanata_replace_keyword.py --locale-id am-ET --find "HelloCash" --replace "VitaBirr" --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Literal


BASE_URL = "https://zanata.vitabirr.com/zanata/rest"
PROJECT = "hellocash"
VERSION = "hellocash_newussdmenu"
DOC_ID = "hellocash"
DEFAULT_SOURCE_LOCALE = "en-US"


@dataclass
class Match:
    entry_id: str
    field: str
    index: int
    before: str
    after: str


DocumentKind = Literal["source", "translation"]


class ZanataClient:
    def __init__(self, base_url: str, user: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.user = user
        self.token = token

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        accept: str = "application/json",
    ) -> tuple[int, str]:
        url = f"{self.base_url}{path}"
        headers = {
            "Accept": accept,
            "X-Auth-User": self.user,
            "X-Auth-Token": self.token,
        }
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request) as response:
                payload = response.read().decode("utf-8")
                return response.status, payload
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            return exc.code, payload

    def _document_path(self, locale_id: str, *, source_locale: str) -> str:
        encoded_doc_id = urllib.parse.quote(DOC_ID, safe="")
        base = f"/projects/p/{PROJECT}/iterations/i/{VERSION}/r/{encoded_doc_id}"
        if locale_id == source_locale:
            return base
        encoded_locale = urllib.parse.quote(locale_id, safe="")
        return f"{base}/translations/{encoded_locale}"

    def get_source_locale(self) -> str:
        path = self._document_path(DEFAULT_SOURCE_LOCALE, source_locale=DEFAULT_SOURCE_LOCALE)
        status, payload = self._request("GET", path)
        if status != 200:
            raise RuntimeError(f"GET source document failed ({status}): {payload}")
        resource = json.loads(payload)
        return resource.get("lang", DEFAULT_SOURCE_LOCALE)

    def get_document(self, locale_id: str, source_locale: str) -> tuple[dict[str, Any], DocumentKind]:
        path = self._document_path(locale_id, source_locale=source_locale)
        status, payload = self._request("GET", path)
        if status != 200:
            raise RuntimeError(
                f"GET document for locale {locale_id!r} failed ({status}): {payload}"
            )
        resource = json.loads(payload)
        kind: DocumentKind = "source" if locale_id == source_locale else "translation"
        return resource, kind

    def put_document(
        self,
        resource: dict[str, Any],
        locale_id: str,
        source_locale: str,
    ) -> None:
        path = self._document_path(locale_id, source_locale=source_locale)
        status, payload = self._request("PUT", path, body=resource)
        if status not in (200, 201, 204):
            raise RuntimeError(
                f"PUT document for locale {locale_id!r} failed ({status}): {payload}"
            )


def replace_in_value(value: str, find: str, replace: str) -> tuple[str, int]:
    count = value.count(find)
    if count == 0:
        return value, 0
    return value.replace(find, replace), count


def process_text_items(
    items: list[dict[str, Any]],
    *,
    id_key: str,
    find: str,
    replace: str,
) -> tuple[list[Match], list[dict[str, Any]]]:
    updated_items = json.loads(json.dumps(items))
    matches: list[Match] = []

    for item in updated_items:
        entry_id = item.get(id_key, "<unknown>")

        if "content" in item and isinstance(item["content"], str):
            new_content, count = replace_in_value(item["content"], find, replace)
            if count:
                matches.append(
                    Match(
                        entry_id=entry_id,
                        field="content",
                        index=0,
                        before=item["content"],
                        after=new_content,
                    )
                )
                item["content"] = new_content

        if "contents" in item and isinstance(item["contents"], list):
            for idx, value in enumerate(item["contents"]):
                if not isinstance(value, str):
                    continue
                new_value, count = replace_in_value(value, find, replace)
                if count:
                    matches.append(
                        Match(
                            entry_id=entry_id,
                            field="contents",
                            index=idx,
                            before=value,
                            after=new_value,
                        )
                    )
                    item["contents"][idx] = new_value

    return matches, updated_items


def collect_matches(
    resource: dict[str, Any],
    kind: DocumentKind,
    find: str,
    replace: str,
) -> tuple[list[Match], dict[str, Any]]:
    updated = json.loads(json.dumps(resource))

    if kind == "source":
        items_key = "textFlows"
        id_key = "id"
    else:
        items_key = "textFlowTargets"
        id_key = "resId"

    items = updated.get(items_key, [])
    if not isinstance(items, list):
        raise RuntimeError(f"Unexpected {items_key} format in document response.")

    matches, updated_items = process_text_items(
        items,
        id_key=id_key,
        find=find,
        replace=replace,
    )
    updated[items_key] = updated_items
    return matches, updated


def print_report(
    matches: list[Match],
    *,
    locale_id: str,
    kind: DocumentKind,
    find: str,
    replace: str,
    dry_run: bool,
) -> None:
    print(f"Document: {DOC_ID}")
    print(f"Project:  {PROJECT}")
    print(f"Version:  {VERSION}")
    print(f"Locale:   {locale_id} ({kind})")
    print(f"Find:     {find!r}")
    print(f"Replace:  {replace!r}")
    print(f"Mode:     {'DRY RUN' if dry_run else 'APPLY'}")
    print()

    if not matches:
        print("No matches found.")
        return

    label = "text flow(s)" if kind == "source" else "translation(s)"
    print(f"Matches: {len(matches)} {label}")
    print("-" * 72)
    for i, match in enumerate(matches, start=1):
        field_label = (
            match.field
            if match.field == "content"
            else f"{match.field}[{match.index}]"
        )
        print(f"{i}. entry={match.entry_id} ({field_label})")
        print(f"   before: {match.before}")
        print(f"   after:  {match.after}")
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Search and replace a keyword in the Zanata document "
            f"'{DOC_ID}' for a chosen locale."
        )
    )
    parser.add_argument(
        "--locale-id",
        required=True,
        help=(
            "Locale to edit. Use the source locale for English source strings "
            "(usually en-US), or a target locale such as am-ET for Amharic translations."
        ),
    )
    parser.add_argument(
        "--find",
        required=True,
        help="Keyword or phrase to search for (literal match).",
    )
    parser.add_argument(
        "--replace",
        required=True,
        help="Replacement text.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show matches only; do not upload changes.",
    )
    parser.add_argument(
        "--base-url",
        default=BASE_URL,
        help=f"Zanata REST base URL (default: {BASE_URL}).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.find == "":
        print("Error: --find cannot be empty.", file=sys.stderr)
        return 1

    user = os.environ.get("ZANATA_USER", "")
    token = os.environ.get("ZANATA_TOKEN", "")

    if not args.dry_run and (not user or not token):
        print(
            "Error: ZANATA_USER and ZANATA_TOKEN environment variables are "
            "required to upload changes.\n"
            "Use --dry-run to preview matches without credentials.",
            file=sys.stderr,
        )
        return 1

    client = ZanataClient(args.base_url, user, token)

    try:
        source_locale = client.get_source_locale()
        resource, kind = client.get_document(args.locale_id, source_locale)
    except Exception as exc:  # noqa: BLE001 - surface clean CLI error
        print(f"Error fetching document: {exc}", file=sys.stderr)
        return 1

    matches, updated_resource = collect_matches(
        resource,
        kind,
        args.find,
        args.replace,
    )
    print_report(
        matches,
        locale_id=args.locale_id,
        kind=kind,
        find=args.find,
        replace=args.replace,
        dry_run=args.dry_run,
    )

    if not matches:
        return 0

    if args.dry_run:
        print("Dry run complete. No changes were sent to Zanata.")
        return 0

    try:
        client.put_document(updated_resource, args.locale_id, source_locale)
    except Exception as exc:  # noqa: BLE001 - surface clean CLI error
        print(f"Error uploading document: {exc}", file=sys.stderr)
        return 1

    print("Upload complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
