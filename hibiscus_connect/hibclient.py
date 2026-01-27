"""
Hibiscus XML-RPC Client

This module provides a client for communicating with the Hibiscus Payment Server
via its XML-RPC interface.

Hibiscus is an open-source online banking application that supports HBCI/FinTS
protocols for German banks. This client allows fetching account information
and transactions from the Hibiscus server.

XML-RPC API Documentation:
- Accounts: hibiscus.xmlrpc.konto.find()
- Transactions: hibiscus.xmlrpc.umsatz.list(params)
- SEPA Direct Debit: hibiscus.xmlrpc.sepalastschrift.create(params)
"""

import xmlrpc.client as xc
import ssl
import socket
from datetime import datetime, timedelta


# Default timeout for XML-RPC requests (seconds)
DEFAULT_TIMEOUT = 30


class HibiscusError(Exception):
    """Base exception for Hibiscus client errors."""
    pass


class HibiscusConnectionError(HibiscusError):
    """Raised when connection to Hibiscus server fails."""
    pass


class HibiscusAPIError(HibiscusError):
    """Raised when Hibiscus API returns an error."""
    pass


class TimeoutTransport(xc.SafeTransport):
    """
    Custom XML-RPC transport with configurable timeout.

    The standard xmlrpc.client doesn't support timeouts directly,
    so we need to subclass the transport and set socket timeout.
    """

    def __init__(self, timeout=DEFAULT_TIMEOUT, use_datetime=False, context=None):
        super().__init__(use_datetime=use_datetime, context=context)
        self.timeout = timeout

    def make_connection(self, host):
        connection = super().make_connection(host)
        connection.timeout = self.timeout
        return connection


class Hibiscus:
    """
    Client for the Hibiscus Payment Server XML-RPC API.

    Usage:
        hib = Hibiscus("server.example.com", "8080", "password", ignore_cert=1)
        accounts = hib.get_accounts()
        transactions = hib.get_transactions(account_id, from_date, to_date)

    Args:
        server: Hibiscus server hostname or IP
        port: Server port (usually 8080)
        master_password: Hibiscus master password for authentication
        ignore_cert: Set to 1 to skip SSL certificate verification
        timeout: Request timeout in seconds (default: 30)
    """

    def __init__(self, server, port, master_password, ignore_cert=0, timeout=DEFAULT_TIMEOUT):
        self.server = server
        self.port = port
        self.timeout = timeout

        # Build the XML-RPC URL with authentication
        url = f"https://admin:{master_password}@{server}:{port}/xmlrpc"

        # Configure SSL context
        if ignore_cert == 1:
            ssl_context = ssl._create_unverified_context()
        else:
            ssl_context = ssl.create_default_context()

        # Create transport with timeout
        transport = TimeoutTransport(timeout=timeout, context=ssl_context)

        # Initialize XML-RPC client
        self.client = xc.ServerProxy(url, transport=transport)

    def get_accounts(self):
        """
        Fetch all bank accounts from Hibiscus server.

        Returns:
            list: List of account dictionaries with fields:
                - id: Hibiscus internal account ID
                - iban: Account IBAN
                - bic: Bank BIC/SWIFT code
                - name: Account holder name
                - bezeichnung: Account description
                - kontonummer: Account number
                - blz: German bank code (BLZ)
                - saldo: Current balance
                - saldo_datum: Balance date

        Raises:
            HibiscusConnectionError: If connection to server fails
            HibiscusAPIError: If API returns an error
        """
        try:
            accounts = self.client.hibiscus.xmlrpc.konto.find()
            return accounts
        except socket.timeout:
            raise HibiscusConnectionError(
                f"Connection to Hibiscus server timed out after {self.timeout}s"
            )
        except ConnectionRefusedError:
            raise HibiscusConnectionError(
                f"Connection refused by Hibiscus server at {self.server}:{self.port}"
            )
        except xc.Fault as e:
            raise HibiscusAPIError(f"Hibiscus API error: {e.faultString}")
        except Exception as e:
            raise HibiscusConnectionError(f"Failed to connect to Hibiscus server: {e}")

    def get_transactions(self, account_id, datum_min=None, datum_max=None):
        """
        Fetch transactions for a specific account from Hibiscus server.

        Args:
            account_id: Hibiscus internal account ID
            datum_min: Start date (datetime object, default: 30 days ago)
            datum_max: End date (datetime object, default: today)

        Returns:
            list: List of transaction dictionaries with fields:
                - id: Transaction ID in Hibiscus
                - konto_id: Account ID
                - betrag: Amount (decimal string, e.g., "123.45")
                - saldo: Balance after transaction
                - datum: Booking date (DD.MM.YYYY)
                - valuta: Value date
                - art: Transaction type
                - empfaenger_name: Counterparty name
                - empfaenger_konto: Counterparty IBAN
                - empfaenger_blz: Counterparty BIC
                - zweck: Purpose text (truncated)
                - zweck_raw: Full purpose text (list of strings)
                - endtoendid: SEPA End-to-End reference
                - primanota: Bank's internal reference
                - customer_ref: Customer reference (timestamp-based)
                - gvcode: German transaction type code

        Raises:
            HibiscusConnectionError: If connection to server fails
            HibiscusAPIError: If API returns an error
        """
        params = {"konto_id": account_id}

        # Set date range
        if datum_min:
            params["datum:min"] = datum_min.strftime("%d.%m.%Y")
        if datum_max:
            params["datum:max"] = datum_max.strftime("%d.%m.%Y")

        # Default to last 30 days if no date range specified
        if not datum_min and not datum_max:
            datum_min = datetime.now() - timedelta(days=30)
            params["datum:min"] = datum_min.strftime("%d.%m.%Y")

        try:
            transactions = self.client.hibiscus.xmlrpc.umsatz.list(params)
            return transactions
        except socket.timeout:
            raise HibiscusConnectionError(
                f"Connection to Hibiscus server timed out after {self.timeout}s"
            )
        except ConnectionRefusedError:
            raise HibiscusConnectionError(
                f"Connection refused by Hibiscus server at {self.server}:{self.port}"
            )
        except xc.Fault as e:
            raise HibiscusAPIError(f"Hibiscus API error: {e.faultString}")
        except Exception as e:
            raise HibiscusConnectionError(f"Failed to fetch transactions: {e}")

    def create_sepa_direct_debit(self, params):
        """
        Create a SEPA direct debit (Lastschrift) in Hibiscus.

        Args:
            params: Dictionary with direct debit parameters:
                - betrag: Amount (string with comma, e.g., "123,45")
                - termin: Execution date
                - konto: Creditor account ID
                - name: Debtor name
                - blz: Debtor BIC
                - kontonummer: Debtor IBAN
                - verwendungszweck: Purpose text
                - creditorid: SEPA Creditor ID
                - mandateid: Mandate reference
                - sigdate: Mandate signature date
                - sequencetype: FRST, RCUR, or FNAL
                - sepatype: SEPA type
                - targetdate: Target date

        Returns:
            Response from Hibiscus API

        Raises:
            HibiscusConnectionError: If connection to server fails
            HibiscusAPIError: If API returns an error
        """
        try:
            result = self.client.hibiscus.xmlrpc.sepalastschrift.create(params)
            return result
        except socket.timeout:
            raise HibiscusConnectionError(
                f"Connection to Hibiscus server timed out after {self.timeout}s"
            )
        except xc.Fault as e:
            raise HibiscusAPIError(f"Hibiscus API error: {e.faultString}")
        except Exception as e:
            raise HibiscusConnectionError(f"Failed to create SEPA direct debit: {e}")

    # Alias for backwards compatibility
    def get_debit_charge(self, params):
        """Deprecated: Use create_sepa_direct_debit instead."""
        return self.create_sepa_direct_debit(params)
