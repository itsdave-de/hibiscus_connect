"""
Hibiscus Server REST API Client

This module provides access to the Hibiscus Payment Server REST API
for retrieving server status, scheduler information, and logs.

REST API Base: https://<server>:<port>/webadmin/rest/
"""

import requests
import ssl
from requests.auth import HTTPBasicAuth
from datetime import datetime


class HibiscusRestClient:
    """Client for Hibiscus Server REST API (webadmin)."""

    def __init__(self, server, port, master_password, ignore_cert=False):
        """
        Initialize the REST client.

        Args:
            server: Hostname or IP of the Hibiscus server
            port: Port number (typically 8080 or 443)
            master_password: Master password for authentication
            ignore_cert: If True, skip SSL certificate verification
        """
        self.base_url = f"https://{server}:{port}/webadmin/rest"
        self.auth = HTTPBasicAuth("admin", master_password)
        self.verify_ssl = not ignore_cert
        self.timeout = 10  # seconds

    def _get(self, endpoint):
        """
        Make a GET request to the REST API.

        Args:
            endpoint: API endpoint (without base URL)

        Returns:
            dict or list: Parsed JSON response

        Raises:
            HibiscusRestError: On connection or API errors
        """
        url = f"{self.base_url}/{endpoint}"
        try:
            response = requests.get(
                url,
                auth=self.auth,
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.SSLError as e:
            raise HibiscusRestError(f"SSL error connecting to {url}: {e}")
        except requests.exceptions.ConnectionError as e:
            raise HibiscusRestError(f"Connection error to {url}: {e}")
        except requests.exceptions.Timeout as e:
            raise HibiscusRestError(f"Timeout connecting to {url}: {e}")
        except requests.exceptions.HTTPError as e:
            raise HibiscusRestError(f"HTTP error from {url}: {e}")
        except ValueError as e:
            raise HibiscusRestError(f"Invalid JSON response from {url}: {e}")

    # ========== System Information ==========

    def get_system_uptime(self):
        """
        Get server uptime information.

        Returns:
            dict: {"started": "08.12.2025 13:25:57", "uptime": "3 Tag(e), 0:48 h"}
        """
        return self._get("system/uptime")

    def get_system_version(self):
        """
        Get Jameica/Hibiscus version information.

        Returns:
            dict: {"version": "2.12.0", "builddate": "", "buildnumber": ""}
        """
        return self._get("system/version")

    # ========== Plugin & Service Information ==========

    def get_plugins(self):
        """
        Get list of installed plugins.

        Returns:
            list: List of plugin dicts with name, version, description, etc.
        """
        return self._get("plugins/list")

    def get_plugin_services(self, plugin_name):
        """
        Get services for a specific plugin.

        Args:
            plugin_name: Name of the plugin (e.g., "hibiscus.server")

        Returns:
            list: List of service dicts with name, started, autostart, etc.
        """
        return self._get(f"plugins/{plugin_name}/services/list")

    def get_service_status(self, plugin_name, service_name):
        """
        Get status of a specific service.

        Args:
            plugin_name: Name of the plugin
            service_name: Name of the service

        Returns:
            dict: {"started": "true"} or {"started": "false"}
        """
        return self._get(f"plugins/{plugin_name}/services/{service_name}/status")

    # ========== Scheduler Status ==========

    def get_scheduler_status(self):
        """
        Get Hibiscus scheduler service status.

        Returns:
            dict: {
                "started": bool,
                "service_info": dict with full service details
            }
        """
        try:
            # Get scheduler service status
            status = self._get("plugins/hibiscus.server/services/scheduler/status")
            is_started = status.get("started", "false").lower() == "true"

            # Get full service info
            services = self.get_plugin_services("hibiscus.server")
            scheduler_info = None
            for svc in services:
                if svc.get("name") == "scheduler":
                    scheduler_info = svc
                    break

            return {
                "started": is_started,
                "service_info": scheduler_info
            }
        except HibiscusRestError:
            raise

    def get_all_services_status(self):
        """
        Get status of all hibiscus.server services.

        Returns:
            dict: {
                "scheduler": {"started": bool, ...},
                "execute": {"started": bool, ...},
                "tantest": {"started": bool, ...}
            }
        """
        services = self.get_plugin_services("hibiscus.server")
        result = {}
        for svc in services:
            result[svc.get("name")] = {
                "started": svc.get("started", False),
                "autostart": svc.get("autostart", False),
                "description": svc.get("description", ""),
                "class": svc.get("class", "")
            }
        return result

    # ========== Log Access ==========

    def get_logs(self, count=100):
        """
        Get recent log entries from the server.

        Args:
            count: Number of log entries to retrieve (default 100)

        Returns:
            list: List of log entry dicts with date, text, level, class, method
        """
        return self._get(f"log/last/{count}")

    def get_logs_filtered(self, count=100, level=None, contains=None):
        """
        Get filtered log entries.

        Args:
            count: Number of entries to fetch before filtering
            level: Filter by log level (ERROR, WARN, INFO, DEBUG)
            contains: Filter entries containing this text

        Returns:
            list: Filtered list of log entries
        """
        logs = self.get_logs(count)

        if level:
            logs = [l for l in logs if l.get("level") == level]

        if contains:
            contains_lower = contains.lower()
            logs = [l for l in logs if contains_lower in l.get("text", "").lower()]

        return logs

    def get_error_logs(self, count=100):
        """Get only ERROR level log entries."""
        return self.get_logs_filtered(count, level="ERROR")

    def get_sync_logs(self, count=200):
        """Get log entries related to synchronization."""
        logs = self.get_logs(count)
        sync_keywords = ["sync", "synchron", "hbci", "fints", "dialog"]
        return [
            l for l in logs
            if any(kw in l.get("text", "").lower() or kw in l.get("class", "").lower()
                   for kw in sync_keywords)
        ]

    # ========== Hibiscus-specific Endpoints ==========

    def get_accounts(self):
        """
        Get all bank accounts from Hibiscus.

        Returns:
            list: List of account dicts with iban, saldo, bezeichnung, etc.
        """
        return self._get("hibiscus/konto/list")

    def get_pending_jobs(self):
        """
        Get pending synchronization jobs.

        Returns:
            list: List of job dicts with name, konto, class
        """
        return self._get("hibiscus/jobs/list")

    # ========== Comprehensive Status ==========

    def get_server_health(self):
        """
        Get comprehensive server health status.

        Returns:
            dict: {
                "online": bool,
                "uptime": dict,
                "version": dict,
                "scheduler": dict,
                "services": dict,
                "pending_jobs_count": int,
                "recent_errors": list,
                "last_sync_logs": list
            }
        """
        result = {
            "online": False,
            "uptime": None,
            "version": None,
            "scheduler": None,
            "services": None,
            "pending_jobs_count": 0,
            "recent_errors": [],
            "last_sync_logs": [],
            "error": None
        }

        try:
            # Basic connectivity check via uptime
            result["uptime"] = self.get_system_uptime()
            result["online"] = True

            # Version info
            result["version"] = self.get_system_version()

            # Scheduler and services
            result["scheduler"] = self.get_scheduler_status()
            result["services"] = self.get_all_services_status()

            # Pending jobs
            jobs = self.get_pending_jobs()
            result["pending_jobs_count"] = len(jobs) if jobs else 0

            # Recent errors (last 50 entries, filter for errors)
            result["recent_errors"] = self.get_error_logs(50)[:10]  # Last 10 errors

            # Recent sync activity
            result["last_sync_logs"] = self.get_sync_logs(100)[:20]  # Last 20 sync entries

        except HibiscusRestError as e:
            result["error"] = str(e)

        return result


class HibiscusRestError(Exception):
    """Exception raised for Hibiscus REST API errors."""
    pass


def get_hibiscus_rest_client():
    """
    Create a HibiscusRestClient instance from Frappe settings.

    Returns:
        HibiscusRestClient: Configured client instance

    Raises:
        HibiscusRestError: If settings are not configured
    """
    import frappe

    settings = frappe.get_single("Hibiscus Connect Settings")

    if not settings.server or not settings.port or not settings.hibiscus_master_password:
        raise HibiscusRestError("Hibiscus connection settings not configured")

    return HibiscusRestClient(
        server=settings.server,
        port=settings.port,
        master_password=settings.get_password("hibiscus_master_password"),
        ignore_cert=bool(settings.ignore_cert)
    )
