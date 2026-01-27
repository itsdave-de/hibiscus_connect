# Copyright (c) 2025, itsdave GmbH and contributors
# For license information, please see license.txt

"""SMB/CIFS client module for uploading files to network shares."""

import frappe
from frappe import _


class SMBConnectionError(Exception):
    """Raised when SMB connection fails."""
    pass


class SMBUploadError(Exception):
    """Raised when SMB upload fails."""
    pass


class SMBClient:
    """Client for SMB/CIFS network share operations.

    Uses smbprotocol for SMB2/SMB3 support.
    """

    def __init__(self, server, share, username, password, domain=None, port=445):
        """Initialize SMB client.

        Args:
            server: SMB server hostname or IP address
            share: Share name (e.g., "Banking")
            username: Username for authentication
            password: Password for authentication
            domain: Windows domain (optional)
            port: SMB port (default: 445)
        """
        self.server = server
        self.share = share
        self.username = username
        self.password = password
        self.domain = domain or ""
        self.port = port or 445
        self._session = None

    def _get_share_path(self):
        """Get the UNC-style share path."""
        return f"\\\\{self.server}\\{self.share}"

    def connect(self):
        """Establish connection to the SMB share.

        Raises:
            SMBConnectionError: If connection fails
        """
        try:
            from smbprotocol.connection import Connection
            from smbprotocol.session import Session
            from smbprotocol.tree import TreeConnect

            # Register the server credentials
            from smbclient import register_session
            register_session(
                self.server,
                username=self.username,
                password=self.password,
                port=self.port
            )

            self._session = True

        except ImportError:
            raise SMBConnectionError(_("smbprotocol library not installed. Please run: pip install smbprotocol"))
        except Exception as e:
            raise SMBConnectionError(_("Failed to connect to SMB share {0}: {1}").format(
                self._get_share_path(), str(e)
            ))

    def disconnect(self):
        """Close the SMB connection."""
        self._session = None

    def ensure_directory(self, path):
        """Ensure the directory exists on the SMB share, creating it if necessary.

        Args:
            path: Path within the share (e.g., "Exports/2025")
        """
        if not path or path == "/":
            return

        try:
            import smbclient

            # Build the full UNC path
            share_path = f"\\\\{self.server}\\{self.share}"

            # Normalize path separators
            path = path.replace("/", "\\").strip("\\")

            # Create directories one by one
            parts = path.split("\\")
            current_path = share_path

            for part in parts:
                if not part:
                    continue
                current_path = f"{current_path}\\{part}"
                try:
                    smbclient.mkdir(current_path)
                except OSError as e:
                    # Directory might already exist, which is fine
                    if "STATUS_OBJECT_NAME_COLLISION" not in str(e) and "already exists" not in str(e).lower():
                        # Check if it's actually a "file exists" error
                        try:
                            smbclient.stat(current_path)
                        except Exception:
                            raise

        except Exception as e:
            raise SMBUploadError(_("Failed to create directory {0}: {1}").format(path, str(e)))

    def upload_file(self, local_content, remote_path, filename):
        """Upload file content to the SMB share.

        Args:
            local_content: File content as bytes or string
            remote_path: Target directory within the share
            filename: Target filename

        Returns:
            Full path of uploaded file

        Raises:
            SMBUploadError: If upload fails
        """
        if not self._session:
            raise SMBUploadError(_("Not connected to SMB share. Call connect() first."))

        try:
            import smbclient

            # Ensure content is bytes
            if isinstance(local_content, str):
                local_content = local_content.encode('utf-8')

            # Ensure target directory exists
            if remote_path:
                self.ensure_directory(remote_path)

            # Build full path
            share_path = f"\\\\{self.server}\\{self.share}"
            if remote_path:
                remote_path = remote_path.replace("/", "\\").strip("\\")
                full_path = f"{share_path}\\{remote_path}\\{filename}"
            else:
                full_path = f"{share_path}\\{filename}"

            # Write the file
            with smbclient.open_file(full_path, mode='wb') as f:
                f.write(local_content)

            return full_path

        except Exception as e:
            raise SMBUploadError(_("Failed to upload file {0}: {1}").format(filename, str(e)))

    def test_connection(self):
        """Test the SMB connection by listing the share root.

        Returns:
            dict with success status and message
        """
        try:
            import smbclient

            # Register session
            from smbclient import register_session
            register_session(
                self.server,
                username=self.username,
                password=self.password,
                port=self.port
            )

            # Try to list the share root
            share_path = f"\\\\{self.server}\\{self.share}"
            entries = list(smbclient.scandir(share_path))

            return {
                "success": True,
                "message": _("Successfully connected to {0}. Found {1} entries in share root.").format(
                    share_path, len(entries)
                )
            }

        except ImportError:
            return {
                "success": False,
                "message": _("smbprotocol library not installed. Please run: pip install smbprotocol")
            }
        except Exception as e:
            return {
                "success": False,
                "message": _("Connection failed: {0}").format(str(e))
            }


def upload_to_smb(content, filename, server, share, path, username, password, domain=None, port=445):
    """Convenience function to upload a file to an SMB share.

    Args:
        content: File content (bytes or string)
        filename: Target filename
        server: SMB server hostname or IP
        share: Share name
        path: Target directory within the share
        username: Username for authentication
        password: Password for authentication
        domain: Windows domain (optional)
        port: SMB port (default: 445)

    Returns:
        Full path of uploaded file

    Raises:
        SMBConnectionError: If connection fails
        SMBUploadError: If upload fails
    """
    client = SMBClient(
        server=server,
        share=share,
        username=username,
        password=password,
        domain=domain,
        port=port
    )

    try:
        client.connect()
        return client.upload_file(content, path, filename)
    finally:
        client.disconnect()


def test_smb_connection(server, share, username, password, domain=None, port=445):
    """Test SMB connection with given credentials.

    Args:
        server: SMB server hostname or IP
        share: Share name
        username: Username for authentication
        password: Password for authentication
        domain: Windows domain (optional)
        port: SMB port (default: 445)

    Returns:
        dict with success status and message
    """
    client = SMBClient(
        server=server,
        share=share,
        username=username,
        password=password,
        domain=domain,
        port=port
    )

    return client.test_connection()
