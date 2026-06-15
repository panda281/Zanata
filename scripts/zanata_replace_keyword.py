#!/usr/bin/env python3
"""
Replace a keyword in the Zanata source document `hellocash`.

Targets:
  Server:   https://zanata.vitabirr.com/zanata/rest
  Project:  hellocash
  Version:  hellocash_newussdmenu
  Document: hellocash

Authentication (required for writes):
  export ZANATA_USER="your-username"
  export ZANATA_TOKEN="your-api-key"

Usage:
  # Preview matches without changing anything
  python3 scripts/zanata_replace_keyword.py --find "VitaBirr" --replace "HelloCash" --dry-run

  # Apply changes
  python3 scripts/zanata_replace_keyword.py --find "VitaBirr" --replace "HelloCash"
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
from typing import Any


BASE_URL = "https://zanata.vitabirr.com/zanata/rest"
PROJECT = "hellocash"
VERSION = "hellocash_newussdmenu"
DOC_ID = "hellocash"


@dataclass
class Match:
    text_flow_id: str
    field: str
    index: int
    before: str
    after: str


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

    def get_source_document(self) -> dict[str, Any]:
        encoded_doc_id = urllib.parse.quote(DOC_ID, safe="")
        path = (
            f"/projects/p/{PROJECT}/iterations/i/{VERSION}/r/{encoded_doc_id}"
        )
        status, payload = self._request("GET", path)
        if status != 200:
            raise RuntimeError(f"GET source document failed ({status}): {payload}")
        return json.loads(payload)

    def put_source_document(self, resource: dict[str, Any]) -> None:
        encoded_doc_id = urllib.parse.quote(DOC_ID, safe="")
        path = (
            f"/projects/p/{PROJECT}/iterations/i/{VERSION}/r/{encoded_doc_id}"
        )
        status, payload = self._request("PUT", path, body=resource)
        if status not in (200, 201, 204):
            raise RuntimeError(f"PUT source document failed ({status}): {payload}")


def replace_in_value(value: str, find: str, replace: str) -> tuple[str, int]:
    count = value.count(find)
    if count == 0:
        return value, 0
    return value.replace(find, replace), count


def collect_matches(
    resource: dict[str, Any],
    find: str,
    replace: str,
) -> tuple[list[Match], dict[str, Any]]:
    updated = json.loads(json.dumps(resource))
    matches: list[Match] = []

    for text_flow in updated.get("textFlows", []):
        flow_id = text_flow.get("id", "<unknown>")

        if "content" in text_flow and isinstance(text_flow["content"], str):
            new_content, count = replace_in_value(text_flow["content"], find, replace)
            if count:
                matches.append(
                    Match(
                        text_flow_id=flow_id,
                        field="content",
                        index=0,
                        before=text_flow["content"],
                        after=new_content,
                    )
                )
                text_flow["content"] = new_content

        if "contents" in text_flow and isinstance(text_flow["contents"], list):
            for idx, item in enumerate(text_flow["contents"]):
                if not isinstance(item, str):
                    continue
                new_item, count = replace_in_value(item, find, replace)
                if count:
                    matches.append(
                        Match(
                            text_flow_id=flow_id,
                            field="contents",
                            index=idx,
                            before=item,
                            after=new_item,
                        )
                    )
                    text_flow["contents"][idx] = new_item

    return matches, updated


def print_report(matches: list[Match], find: str, replace: str, dry_run: bool) -> None:
    print(f"Document: {DOC_ID}")
    print(f"Project:  {PROJECT}")
    print(f"Version:  {VERSION}")
    print(f"Find:     {find!r}")
    print(f"Replace:  {replace!r}")
    print(f"Mode:     {'DRY RUN' if dry_run else 'APPLY'}")
    print()

    if not matches:
        print("No matches found.")
        return

    print(f"Matches: {len(matches)} text flow(s)")
    print("-" * 72)
    for i, match in enumerate(matches, start=1):
        field_label = (
            match.field
            if match.field == "content"
            else f"{match.field}[{match.index}]"
        )
        print(f"{i}. textFlow={match.text_flow_id} ({field_label})")
        print(f"   before: {match.before}")
        print(f"   after:  {match.after}")
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Search and replace a keyword in the Zanata source document "
            f"'{DOC_ID}'."
        )
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
        resource = client.get_source_document()
    except Exception as exc:  # noqa: BLE001 - surface clean CLI error
        print(f"Error fetching document: {exc}", file=sys.stderr)
        return 1

    matches, updated_resource = collect_matches(resource, args.find, args.replace)
    print_report(matches, args.find, args.replace, args.dry_run)

    if not matches:
        return 0

    if args.dry_run:
        print("Dry run complete. No changes were sent to Zanata.")
        return 0

    try:
        client.put_source_document(updated_resource)
    except Exception as exc:  # noqa: BLE001 - surface clean CLI error
        print(f"Error uploading document: {exc}", file=sys.stderr)
        return 1

    print("Upload complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
