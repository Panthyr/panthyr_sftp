# -*- coding: utf-8 -*-
# vim: ts=4:sw=4:expandtab:cuc:autoindent:ignorecase:colorcolumn=99

__author__ = 'Dieter Vansteenwegen'
__project__ = 'Panthyr SFTP library'
__project_link__ = 'https://waterhypernet.org/equipment/'

import logging
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Union

log = logging.getLogger(__name__)

DEFAULT_ENV_FILE = '/home/panthyr/data/sftp.env'
SFTP_BINARY = 'sftp'


# ============================================================================
# Custom Exceptions
# ============================================================================


class PsFTPError(Exception):
    """Base exception class for all PsFTP errors."""


class PsFTPConfigError(PsFTPError):
    """Exception raised when the configuration (env file) is missing or invalid."""


class PsFTPConnectionError(PsFTPError):
    """Exception raised when connection to SFTP server fails."""


class PsFTPAuthenticationError(PsFTPError):
    """Exception raised when authentication fails."""


class PsFTPNotConnectedError(PsFTPError):
    """Exception raised when attempting operations without an active connection."""


class PsFTPFileNotFoundError(PsFTPError):
    """Exception raised when a local file is not found."""


class PsFTPInvalidPathError(PsFTPError):
    """Exception raised when path is not a valid file."""


class PsFTPUploadError(PsFTPError):
    """Exception raised when file upload fails."""


class PsFTPVerificationError(PsFTPError):
    """Exception raised when upload verification fails."""


# ============================================================================
# Helpers
# ============================================================================


def _read_env_file(env_file: Union[str, Path]) -> Dict[str, str]:
    """Parse a simple KEY=VALUE file (comments with '#', optional quotes)."""
    path = Path(env_file)
    try:
        text = path.read_text(encoding='utf-8')
    except OSError as e:
        msg = f'Cannot read config file {path}: {e}'
        raise PsFTPConfigError(msg) from e

    values: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        if line.startswith('export '):
            line = line[len('export ') :].lstrip()
        key, _, value = line.partition('=')
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _quote(path: str) -> str:
    """Quote a path for use in an sftp batch command."""
    return '"' + path.replace('\\', '\\\\').replace('"', '\\"') + '"'


# ============================================================================
# Main SFTP Client Class
# ============================================================================


class PsFTP:
    """SFTP client that uploads files using the system OpenSSH ``sftp`` binary.

    Authentication is done with an SSH key. Connection settings are read from an env file
    (default ``/home/panthyr/data/sftp.env``) with the keys SFTP_SERVER, SFTP_PORT, SFTP_USER,
    SFTP_KEY_FILE and SFTP_REMOTE_DIR. Explicit constructor arguments override the file.

    Every upload runs in a new ``sftp`` process (batch mode); ``connect()`` verifies that the
    server can be reached and the key is accepted.

    Remote paths given to :meth:`upload_file` are relative to ``/<SFTP_REMOTE_DIR>/`` on the
    server. Missing directories are created.

    Example:
        >>> with PsFTP() as client:
        ...     client.upload_file('file.txt', '2026/file.txt', max_upload_speed_kb=100)
    """

    def __init__(
        self,
        server: Optional[str] = None,
        user: Optional[str] = None,
        key_file: Optional[str] = None,
        port: Optional[int] = None,
        timeout: int = 20,
        remote_dir: Optional[str] = None,
        env_file: Union[str, Path] = DEFAULT_ENV_FILE,
        verbose: bool = False,
    ) -> None:
        """Initialize PsFTP client.

        Args:
            server: Server hostname/IP (default: SFTP_SERVER from env file)
            user: Username (default: SFTP_USER)
            key_file: Path to the SSH private key (default: SFTP_KEY_FILE)
            port: Server port (default: SFTP_PORT, or 22)
            timeout: Connection timeout in seconds, also used per sftp operation (default: 20)
            remote_dir: Directory in the server root to upload into (default: SFTP_REMOTE_DIR)
            env_file: Path to the env file
            verbose: Run sftp with maximum verbosity (-vvv) and log its output at DEBUG level

        Raises:
            PsFTPConfigError: If a required setting is missing or invalid
        """
        env: Dict[str, str] = {}
        if None in (server, user, key_file, remote_dir):
            env = _read_env_file(env_file)

        self.server = self._require(server, env, 'SFTP_SERVER')
        self.user = self._require(user, env, 'SFTP_USER')
        self.key_file = self._require(key_file, env, 'SFTP_KEY_FILE')
        self.remote_dir = self._require(remote_dir, env, 'SFTP_REMOTE_DIR').strip('/')
        try:
            self.port = int(port if port is not None else env.get('SFTP_PORT', 22))
        except ValueError as e:
            msg = f'Invalid SFTP_PORT: {env.get("SFTP_PORT")}'
            raise PsFTPConfigError(msg) from e
        self.timeout = timeout
        self.verbose = verbose
        self._connected = False

    @staticmethod
    def _require(value: Optional[str], env: Dict[str, str], name: str) -> str:
        result = value if value is not None else env.get(name)
        if not result:
            msg = f'Missing setting {name} (not passed and not found in env file)'
            raise PsFTPConfigError(msg)
        return result

    def __enter__(self) -> 'PsFTP':
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.disconnect()
        return False

    # ========================================================================
    # Connection Management
    # ========================================================================

    def connect(self) -> None:
        """Check that the server is reachable and the key is accepted.

        Raises:
            PsFTPConfigError: If the sftp binary or key file is missing
            PsFTPAuthenticationError: If authentication fails
            PsFTPConnectionError: If connection to SFTP server fails
        """
        if shutil.which(SFTP_BINARY) is None:
            msg = f'"{SFTP_BINARY}" executable not found in PATH'
            raise PsFTPConfigError(msg)
        if not Path(self.key_file).is_file():
            msg = f'SSH key file not found: {self.key_file}'
            raise PsFTPConfigError(msg)

        log.info(f'Connecting to SFTP server {self.server}:{self.port} (timeout: {self.timeout}s)')
        try:
            result = self._run_batch(['pwd'])
        except subprocess.TimeoutExpired as e:
            msg = f'Connection to {self.server} timed out after {self.timeout}s'
            log.error(msg)
            raise PsFTPConnectionError(msg) from e
        except OSError as e:
            msg = f'Failed to run {SFTP_BINARY}: {e}'
            log.error(msg)
            raise PsFTPConnectionError(msg) from e

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if 'permission denied' in stderr.lower():
                msg = f'Authentication failed for {self.user}@{self.server}: {stderr}'
                log.error(msg)
                raise PsFTPAuthenticationError(msg)
            msg = f'Failed to connect to {self.server}: {stderr}'
            log.error(msg)
            raise PsFTPConnectionError(msg)

        self._connected = True
        log.info(f'Successfully connected to {self.server}')

    def disconnect(self) -> None:
        """Mark the client as disconnected (no persistent session is kept)."""
        self._connected = False

    # ========================================================================
    # Public Upload Method
    # ========================================================================

    def upload_file(
        self,
        local_path: Union[str, Path],
        remote_path: str,
        max_upload_speed_kb: Optional[int] = None,
    ) -> None:
        """Upload a file to ``/<remote_dir>/<remote_path>``.

        The file is first uploaded as 'uploading.now' in the target directory to avoid
        partial file visibility. After the size is verified, any existing target is removed
        and the temporary file is renamed (the OpenSSH sftp client has no atomic overwrite,
        so there is a very short window without the target file).

        Args:
            local_path: Path to the local file to upload
            remote_path: Destination path, relative to the remote directory
            max_upload_speed_kb: Maximum upload speed in KB/s (default: None, unlimited)

        Raises:
            PsFTPFileNotFoundError: If the local file does not exist
            PsFTPInvalidPathError: If the path is not a file
            PsFTPNotConnectedError: If not connected to SFTP server
            PsFTPUploadError: If file upload fails
            PsFTPVerificationError: If upload verification fails
        """
        local_path = Path(local_path)
        self._validate_local_file(local_path)
        self._ensure_connected()

        rel = PurePosixPath(remote_path.lstrip('/'))
        final_path = (PurePosixPath('/') / self.remote_dir / rel).as_posix()
        target_dir = PurePosixPath(final_path).parent
        temp_path = (target_dir / 'uploading.now').as_posix()

        speed_args: List[str] = []
        if max_upload_speed_kb:
            # sftp -l is in Kbit/s
            speed_args = ['-l', str(int(max_upload_speed_kb) * 8)]

        # A leading '-' makes sftp ignore the error (e.g. directory exists)
        mkdirs = []
        current = PurePosixPath('/')
        for part in target_dir.parts[1:]:
            current = current / part
            mkdirs.append(f'-mkdir {_quote(current.as_posix())}')

        log.info(
            f'Uploading {local_path} to temporary file {temp_path} with maximum speed '
            f'{max_upload_speed_kb or "unlimited"} KB/s'
        )
        self._run_checked(
            [*mkdirs, f'put {_quote(str(local_path))} {_quote(temp_path)}'],
            extra_args=speed_args,
            error_cls=PsFTPUploadError,
            what=f'upload of {local_path}',
            timeout=self._upload_timeout(local_path, max_upload_speed_kb),
        )

        self._verify_upload(local_path, temp_path)
        log.info('Upload verification successful')

        self._run_checked(
            [f'-rm {_quote(final_path)}', f'rename {_quote(temp_path)} {_quote(final_path)}'],
            error_cls=PsFTPUploadError,
            what=f'rename to {final_path}',
        )

    def delete_file(self, remote_path: str) -> None:
        """Delete ``/<remote_dir>/<remote_path>`` from the server.

        Raises:
            PsFTPNotConnectedError: If not connected to SFTP server
            PsFTPError: If the removal fails
        """
        self._ensure_connected()
        rel = PurePosixPath(remote_path.lstrip('/'))
        final_path = (PurePosixPath('/') / self.remote_dir / rel).as_posix()
        self._run_checked(
            [f'rm {_quote(final_path)}'],
            error_cls=PsFTPError,
            what=f'removal of {final_path}',
        )

    # ========================================================================
    # Internals
    # ========================================================================

    def _validate_local_file(self, local_path: Path) -> None:
        if not local_path.exists():
            err_msg = f'Local file not found: {local_path}'
            raise PsFTPFileNotFoundError(err_msg)
        if not local_path.is_file():
            err_msg = f'Path is not a file: {local_path}'
            raise PsFTPInvalidPathError(err_msg)

    def _ensure_connected(self) -> None:
        if not self._connected:
            err_msg = 'Not connected to SFTP server. Call connect() first.'
            raise PsFTPNotConnectedError(err_msg)

    def _upload_timeout(self, local_path: Path, max_speed_kb: Optional[int]) -> float:
        """Overall timeout: connection timeout + 2x expected transfer time."""
        size_kb = local_path.stat().st_size / 1024
        speed = max_speed_kb or 10  # assume at least 10 KB/s when unthrottled
        return self.timeout + 2 * size_kb / speed

    def _base_command(self, extra_args: Optional[List[str]] = None) -> List[str]:
        return [
            SFTP_BINARY,
            '-b',
            '-',
            '-i',
            self.key_file,
            '-P',
            str(self.port),
            '-o',
            'BatchMode=yes',
            '-o',
            'IdentitiesOnly=yes',
            '-o',
            'StrictHostKeyChecking=accept-new',
            '-o',
            f'ConnectTimeout={self.timeout}',
            '-o',
            'ServerAliveInterval=30',
            '-o',
            'ServerAliveCountMax=3',
            *(['-vvv'] if self.verbose else []),
            *(extra_args or []),
            f'{self.user}@{self.server}',
        ]

    def _run_batch(
        self,
        commands: List[str],
        extra_args: Optional[List[str]] = None,
        timeout: Optional[float] = None,
    ) -> 'subprocess.CompletedProcess[str]':
        result = subprocess.run(  # noqa: S603
            self._base_command(extra_args),
            input='\n'.join(commands) + '\n',
            capture_output=True,
            text=True,
            timeout=timeout if timeout is not None else self.timeout * 3,
            check=False,
        )
        if self.verbose:
            log.debug(f'sftp commands: {commands}')
            log.debug(f'sftp stdout:\n{result.stdout}')
            log.debug(f'sftp stderr:\n{result.stderr}')
        return result

    def _run_checked(
        self,
        commands: List[str],
        error_cls: type,
        what: str,
        extra_args: Optional[List[str]] = None,
        timeout: Optional[float] = None,
    ) -> 'subprocess.CompletedProcess[str]':
        try:
            result = self._run_batch(commands, extra_args, timeout)
        except subprocess.TimeoutExpired as e:
            msg = f'Timeout during {what}: {e}'
            log.error(msg)
            raise error_cls(msg) from e
        except OSError as e:
            msg = f'Failed to run {SFTP_BINARY} for {what}: {e}'
            log.error(msg)
            raise error_cls(msg) from e
        if result.returncode != 0:
            msg = f'Failed {what}: {result.stderr.strip() or result.stdout.strip()}'
            log.error(msg)
            raise error_cls(msg)
        return result

    def _verify_upload(self, local_path: Path, remote_path: str) -> None:
        """Verify that the remote file size matches the local file."""
        result = self._run_checked(
            [f'ls -ln {_quote(remote_path)}'],
            error_cls=PsFTPVerificationError,
            what=f'verification of {remote_path}',
        )
        local_size = local_path.stat().st_size
        remote_size = None
        for line in result.stdout.splitlines():
            fields = line.split()
            # "-rw-r--r-- 1 uid gid size Mon DD HH:MM name"
            if len(fields) >= 9 and fields[0].startswith('-') and fields[4].isdigit():
                remote_size = int(fields[4])
                break
        if remote_size is None:
            msg = f'Could not determine remote size of {remote_path}: {result.stdout.strip()}'
            log.error(msg)
            raise PsFTPVerificationError(msg)
        if local_size != remote_size:
            msg = f'File size mismatch: local={local_size}, remote={remote_size}'
            log.error(msg)
            raise PsFTPVerificationError(msg)
