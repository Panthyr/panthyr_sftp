===============================
Panthyr SFTP Library Usage
===============================

The library uploads files with the system OpenSSH ``sftp`` client, using SSH key authentication.
It has no Python dependencies. Every operation runs in a new ``sftp`` process in batch mode.

Configuration
-------------

Settings are read from an env file, by default ``/home/panthyr/data/sftp.env``:

.. code-block:: text

    SFTP_SERVER=ftp.example.org
    SFTP_PORT=22
    SFTP_USER=user
    SFTP_KEY_FILE=/home/panthyr/data/sftp_key
    SFTP_REMOTE_DIR=TBBE

``SFTP_PORT`` is optional (default 22), all other keys are required. Comments (``#``), an
``export`` prefix and quoted values are supported.

Any setting can be overridden with a constructor argument. A different env file can be given with
``env_file``.

Basic Usage
-----------

.. code-block:: python

    from p_sftp import PsFTP

    with PsFTP() as client:
        # With SFTP_REMOTE_DIR=TBBE in 2026: /TBBE/2026/abc.db
        client.upload_file('/data/abc.db')

``SFTP_REMOTE_DIR`` is the station directory. Uploads use the local filename in
``/<SFTP_REMOTE_DIR>/<current local year>/`` and attempt to create missing directories.
Paths passed to ``delete_file`` are relative to the year directory. The local year is determined
separately for each upload or deletion.

The context manager calls ``connect()`` on entry, which checks that the ``sftp`` binary and key
file exist and that the server accepts the key. ``disconnect()`` is called on exit.

Manual Connection Management
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from p_sftp import PsFTP

    client = PsFTP(server='ftp.example.org', user='user', key_file='/path/to/key',
                   remote_dir='TBBE', port=2222)
    client.connect()
    try:
        client.upload_file('file.txt')
    finally:
        client.disconnect()

Limiting the Upload Speed
~~~~~~~~~~~~~~~~~~~~~~~~~

Throttling (``sftp -l``) is only applied when ``max_upload_speed_kb`` is set:

.. code-block:: python

    with PsFTP() as client:
        client.upload_file('file.csv', max_upload_speed_kb=100)

How an Upload Works
~~~~~~~~~~~~~~~~~~~

1. The file is uploaded as ``uploading.now`` in the target directory, so partial files are never
   visible under the final name.
2. The remote size is compared with the local size. A mismatch raises
   ``PsFTPVerificationError``.
3. Any existing target is removed and the temporary file is renamed. The OpenSSH client has no
   atomic overwrite, so there is a very short window without the target file.

Deleting a Remote File
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    with PsFTP() as client:
        client.delete_file('file.csv')

Testing the Configuration
-------------------------

The ``test_sftp`` command checks the configuration in the default env file. It logs in with the
configured key, uploads a 50 KB file with random data named ``test_upload``, reports the result and
removes the file again:

.. code-block:: console

    $ test_sftp
    Connecting to user@ftp.example.org:22 ...
    Uploading test_upload (51200 bytes) ...
    SUCCESS: upload completed and verified.
    Removed test_upload from the server.

The exit code is 0 on success and 1 on failure (including a failed removal).

Error Handling
--------------

All exceptions derive from ``PsFTPError``:

==================================  =============================================================
Exception                           Raised when
==================================  =============================================================
``PsFTPConfigError``                Env file unreadable, setting missing or invalid, ``sftp``
                                    binary or key file not found
``PsFTPConnectionError``            Server unreachable, timeout
``PsFTPAuthenticationError``        The server rejects the key
``PsFTPNotConnectedError``          Upload or delete without calling ``connect()``
``PsFTPFileNotFoundError``          The local file does not exist
``PsFTPInvalidPathError``           The local path is not a file
``PsFTPUploadError``                The upload or rename fails
``PsFTPVerificationError``          The remote size cannot be determined or does not match
==================================  =============================================================

.. code-block:: python

    from p_sftp import PsFTP, PsFTPAuthenticationError, PsFTPError

    try:
        with PsFTP() as client:
            client.upload_file('file.txt')
    except PsFTPAuthenticationError as e:
        print(f'Key rejected: {e}')
    except PsFTPError as e:
        print(f'SFTP error: {e}')

Logging
-------

The library uses the standard ``logging`` module (logger ``p_sftp.p_sftp``):

.. code-block:: python

    import logging

    logging.basicConfig(level=logging.INFO)

API Reference
-------------

``PsFTP(server=None, user=None, key_file=None, port=None, timeout=20, remote_dir=None, env_file='/home/panthyr/data/sftp.env')``
    Arguments left at ``None`` are read from the env file (``SFTP_SERVER``, ``SFTP_USER``,
    ``SFTP_KEY_FILE``, ``SFTP_PORT``, ``SFTP_REMOTE_DIR``). ``timeout`` (seconds) is used for
    connecting and for each ``sftp`` operation.

``connect()``
    Check that the server is reachable and the key is accepted.

``disconnect()``
    Mark the client as disconnected. No persistent session is kept.

``upload_file(local_path, max_upload_speed_kb=None)``
    Upload ``local_path`` (``str`` or ``Path``) to
    ``/<remote_dir>/<current local year>/<local filename>`` and verify the size.

``delete_file(remote_path)``
    Delete ``/<remote_dir>/<current local year>/<remote_path>`` from the server.
