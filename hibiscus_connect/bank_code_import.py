# Copyright (c) 2025, itsdave GmbH and contributors
# For license information, please see license.txt

"""
Bank Code (BLZ) Import Module

This module handles downloading and importing the Bundesbank Bankleitzahlendatei (BLZ)
into Frappe for bank code lookup and validation.

The Bundesbank provides BLZ files in XML format at:
https://www.bundesbank.de/de/aufgaben/unbarer-zahlungsverkehr/serviceangebot/bankleitzahlen/download-bankleitzahlen-602592
"""

import frappe
import requests
import re
import zipfile
import io
import xml.etree.ElementTree as ET
from frappe.utils import now_datetime
from urllib.parse import urljoin
import json


# Default Bundesbank download page URL
DEFAULT_BUNDESBANK_URL = "https://www.bundesbank.de/de/aufgaben/unbarer-zahlungsverkehr/serviceangebot/bankleitzahlen/download-bankleitzahlen-602592"

# XML field mapping: Bundesbank XML element -> DocType field
XML_FIELD_MAPPING = {
    "blz": "blz",
    "merkmal": "merkmal",
    "bezeichnung": "bezeichnung",
    "plz": "plz",
    "ort": "ort",
    "kurzbezeichnung": "kurzbezeichnung",
    "pan": "pan",
    "bic": "bic",
    "pz": "pruefziffer_methode",
    "datensatz": "datensatz_nr",
    "aenderung": "aenderungskennzeichen",
    "loeschung": "blz_loesch",
    "nachfolgeblz": "nachfolge_blz",
    "ibanregel": "iban_regel"
}

# Date range pattern for finding validity period
DATE_RANGE_RE = re.compile(r"gültig vom\s+(\d{2}\.\d{2}\.\d{4})\s+bis\s+(\d{2}\.\d{2}\.\d{4})", re.IGNORECASE)


class BLZImportError(Exception):
    """Exception raised for BLZ import errors."""
    pass


def parse_ddmmyyyy(s):
    """Parse DD.MM.YYYY date string to sortable tuple (YYYY, MM, DD)."""
    dd, mm, yyyy = s.split(".")
    return (int(yyyy), int(mm), int(dd))


def scrape_xml_download_link(page_url=None):
    """
    Scrape the Bundesbank download page to find the XML file download link.

    Args:
        page_url: URL of the download page (uses default if not provided)

    Returns:
        tuple: (download_url, valid_from, valid_until) - URL and validity dates

    Raises:
        BLZImportError: If the download link cannot be found
    """
    if not page_url:
        settings = frappe.get_single("Hibiscus Connect Settings")
        page_url = settings.bundesbank_download_url or DEFAULT_BUNDESBANK_URL

    try:
        response = requests.get(
            page_url,
            timeout=30,
            headers={"User-Agent": "Hibiscus-Connect-BLZ-Importer/1.0"}
        )
        response.raise_for_status()
        html_content = response.text

        # Use BeautifulSoup if available, otherwise use regex
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, "html.parser")
            candidates = []

            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                text = " ".join(a.get_text(" ", strip=True).split())

                if not href.lower().endswith(".xml"):
                    continue
                if "bankleitzahlendateien" not in text.lower():
                    continue

                m = DATE_RANGE_RE.search(text)
                if not m:
                    continue

                start_s, end_s = m.group(1), m.group(2)
                start_key = parse_ddmmyyyy(start_s)

                abs_url = urljoin(page_url, href)
                candidates.append((start_key, abs_url, start_s, end_s))

            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                _, url, valid_from, valid_until = candidates[0]
                return url, valid_from, valid_until

        except ImportError:
            # BeautifulSoup not available, use regex fallback
            pass

        # Regex fallback - look for XML download links
        xml_patterns = [
            r'href="(https://www\.bundesbank\.de/resource/blob/[^"]+\.xml)"',
            r'href="(/resource/blob/[^"]+\.xml)"',
        ]

        for pattern in xml_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            if matches:
                url = matches[0]
                if url.startswith("/"):
                    url = "https://www.bundesbank.de" + url
                return url, None, None

        raise BLZImportError("Could not find XML download link on the Bundesbank page")

    except requests.exceptions.RequestException as e:
        raise BLZImportError(f"Error fetching download page: {e}")


def download_blz_file(download_url):
    """
    Download the BLZ file from the given URL.

    Args:
        download_url: Direct URL to the XML or ZIP file

    Returns:
        bytes: Content of the XML file

    Raises:
        BLZImportError: If download fails
    """
    try:
        response = requests.get(
            download_url,
            timeout=120,
            headers={"User-Agent": "Hibiscus-Connect-BLZ-Importer/1.0"}
        )
        response.raise_for_status()

        content = response.content

        # If it's a ZIP file, extract the XML
        content_type = response.headers.get("content-type", "")
        if download_url.lower().endswith(".zip") or "zip" in content_type.lower():
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                xml_files = [f for f in zf.namelist() if f.lower().endswith(".xml")]
                if not xml_files:
                    raise BLZImportError("No XML file found in the ZIP archive")
                content = zf.read(xml_files[0])

        return content

    except requests.exceptions.RequestException as e:
        raise BLZImportError(f"Error downloading BLZ file: {e}")
    except zipfile.BadZipFile as e:
        raise BLZImportError(f"Invalid ZIP file: {e}")


def parse_blz_xml(xml_content, valid_from=None, valid_until=None):
    """
    Parse the BLZ XML file and extract bank code records.

    Args:
        xml_content: XML content as bytes or string
        valid_from: Optional validity start date (DD.MM.YYYY)
        valid_until: Optional validity end date (DD.MM.YYYY)

    Returns:
        list: List of dictionaries with bank code data

    Raises:
        BLZImportError: If XML parsing fails
    """
    try:
        if isinstance(xml_content, bytes):
            # Try UTF-8 first, then ISO-8859-1 (Latin-1) as per Bundesbank spec
            try:
                xml_content = xml_content.decode("utf-8")
            except UnicodeDecodeError:
                xml_content = xml_content.decode("iso-8859-1")

        root = ET.fromstring(xml_content)
        records = []

        # Convert date strings to Frappe date format (YYYY-MM-DD)
        valid_from_date = None
        valid_until_date = None
        if valid_from:
            try:
                dd, mm, yyyy = valid_from.split(".")
                valid_from_date = f"{yyyy}-{mm}-{dd}"
            except (ValueError, AttributeError):
                pass
        if valid_until:
            try:
                dd, mm, yyyy = valid_until.split(".")
                valid_until_date = f"{yyyy}-{mm}-{dd}"
            except (ValueError, AttributeError):
                pass

        # Find all bank code records
        # Common patterns: <record>, <blz_eintrag>, <bankleitzahl>, <eintrag>, <datensatz>
        record_elements = []
        for elem_name in ["record", "blz_eintrag", "bankleitzahl", "eintrag", "datensatz"]:
            record_elements.extend(root.iter(elem_name))

        # If no named records found, try direct children of root
        if not record_elements:
            record_elements = list(root)

        for record_elem in record_elements:
            record = parse_blz_record(record_elem)
            if record and record.get("blz"):
                record["valid_from"] = valid_from_date
                record["valid_until"] = valid_until_date
                record["country"] = "Germany"
                records.append(record)

        return records

    except ET.ParseError as e:
        raise BLZImportError(f"Error parsing XML: {e}")


def parse_blz_record(element):
    """
    Parse a single BLZ record element.

    Args:
        element: XML element containing a bank code record

    Returns:
        dict: Parsed bank code data or None if invalid
    """
    record = {}

    for xml_field, doctype_field in XML_FIELD_MAPPING.items():
        value = None

        # Try as child element (case-insensitive)
        for child in element:
            if child.tag.lower() == xml_field.lower():
                value = child.text
                break

        # Try as attribute
        if value is None:
            for attr_name, attr_value in element.attrib.items():
                if attr_name.lower() == xml_field.lower():
                    value = attr_value
                    break

        if value is not None:
            value = value.strip() if isinstance(value, str) else value

            # Convert blz_loesch to boolean
            if doctype_field == "blz_loesch":
                value = 1 if value == "1" else 0

            record[doctype_field] = value

    return record if record.get("blz") else None


def import_blz_records(records, sync_log=None):
    """
    Import BLZ records into the database.

    Args:
        records: List of bank code dictionaries
        sync_log: Optional sync log document for progress tracking

    Returns:
        dict: Import statistics
    """
    stats = {
        "total": len(records),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "error_details": []
    }

    for i, record in enumerate(records):
        try:
            blz = record.get("blz")
            if not blz:
                stats["skipped"] += 1
                continue

            # Ensure BLZ is 8 digits
            blz = str(blz).zfill(8)
            record["blz"] = blz

            # Check if record exists
            if frappe.db.exists("Bank Code", blz):
                # Update existing record
                doc = frappe.get_doc("Bank Code", blz)
                for field, value in record.items():
                    if hasattr(doc, field) and value is not None:
                        setattr(doc, field, value)
                doc.save(ignore_permissions=True)
                stats["updated"] += 1
            else:
                # Create new record
                doc = frappe.get_doc({
                    "doctype": "Bank Code",
                    **record
                })
                doc.insert(ignore_permissions=True)
                stats["created"] += 1

            # Commit every 500 records for better performance
            if (i + 1) % 500 == 0:
                frappe.db.commit()
                if sync_log:
                    sync_log.reload()
                    sync_log.details = json.dumps({
                        "progress": f"{i + 1}/{len(records)}",
                        "created": stats["created"],
                        "updated": stats["updated"]
                    })
                    sync_log.save(ignore_permissions=True)
                    frappe.db.commit()

        except Exception as e:
            stats["errors"] += 1
            if len(stats["error_details"]) < 50:  # Limit error details
                stats["error_details"].append({
                    "blz": record.get("blz", "unknown"),
                    "error": str(e)
                })

    frappe.db.commit()
    return stats


@frappe.whitelist()
def import_bank_codes_now():
    """
    Manual trigger to import BLZ data.
    Called from Settings button.

    Returns:
        dict: Import result with statistics
    """
    # Create sync log for tracking
    sync_log = frappe.get_doc({
        "doctype": "Hibiscus Connect Sync Log",
        "status": "Running",
        "trigger_type": "Manual",
        "started_at": now_datetime(),
        "accounts_processed": 0,
        "transactions_fetched": 0,
        "errors_count": 0,
        "details": json.dumps({"type": "BLZ Import"})
    })
    sync_log.insert(ignore_permissions=True)
    frappe.db.commit()

    result = {
        "success": False,
        "message": "",
        "stats": {}
    }

    try:
        # Step 1: Find download link
        frappe.publish_progress(10, title="BLZ Import", description="Finding download link...")
        download_url, valid_from, valid_until = scrape_xml_download_link()

        # Step 2: Download the file
        frappe.publish_progress(30, title="BLZ Import", description="Downloading BLZ file...")
        xml_content = download_blz_file(download_url)

        # Step 3: Parse XML
        frappe.publish_progress(50, title="BLZ Import", description="Parsing XML file...")
        records = parse_blz_xml(xml_content, valid_from, valid_until)

        if not records:
            raise BLZImportError("No bank code records found in the file")

        # Step 4: Import records
        frappe.publish_progress(60, title="BLZ Import", description=f"Importing {len(records)} records...")
        stats = import_blz_records(records, sync_log)

        # Update settings with import info
        settings = frappe.get_single("Hibiscus Connect Settings")
        settings.last_blz_import = now_datetime()
        settings.blz_record_count = frappe.db.count("Bank Code")
        settings.save(ignore_permissions=True)

        # Update sync log
        sync_log.reload()
        sync_log.status = "Complete"
        sync_log.completed_at = now_datetime()
        sync_log.accounts_processed = stats["total"]
        sync_log.transactions_fetched = stats["created"] + stats["updated"]
        sync_log.errors_count = stats["errors"]
        sync_log.details = json.dumps(stats, indent=2)
        if stats["error_details"]:
            sync_log.error_log = "\n".join([
                f"{e['blz']}: {e['error']}" for e in stats["error_details"]
            ])
        sync_log.save(ignore_permissions=True)

        result["success"] = True
        result["message"] = f"Successfully imported {stats['created']} new and updated {stats['updated']} bank codes"
        result["stats"] = stats

        frappe.publish_progress(100, title="BLZ Import", description="Import complete!")

    except BLZImportError as e:
        sync_log.reload()
        sync_log.status = "Failed"
        sync_log.completed_at = now_datetime()
        sync_log.error_log = str(e)
        sync_log.save(ignore_permissions=True)

        result["message"] = str(e)

    except Exception as e:
        sync_log.reload()
        sync_log.status = "Failed"
        sync_log.completed_at = now_datetime()
        sync_log.error_log = str(e)
        sync_log.save(ignore_permissions=True)

        frappe.log_error(f"BLZ Import Error: {e}", "Bank Code Import")
        result["message"] = f"Import failed: {e}"

    frappe.db.commit()
    return result
