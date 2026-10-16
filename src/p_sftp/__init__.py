# -*- coding: utf-8 -*-
# vim: ts=4:sw=4:expandtab:cuc:autoindent:ignorecase:colorcolumn=99


__author__ = 'Dieter Vansteenwegen'
__project__ = 'Panthyr SFTP library'
__project_link__ = 'https://waterhypernet.org/equipment/'


from p_sftp.__version__ import __version__
from p_sftp.p_sftp import (
    PsFTP,
    PsFTPAuthenticationError,
    PsFTPConfigError,
    PsFTPConnectionError,
    PsFTPError,
    PsFTPFileNotFoundError,
    PsFTPInvalidPathError,
    PsFTPNotConnectedError,
    PsFTPUploadError,
    PsFTPVerificationError,
)

__all__ = [
    '__version__',
    'PsFTP',
    'PsFTPError',
    'PsFTPConfigError',
    'PsFTPConnectionError',
    'PsFTPAuthenticationError',
    'PsFTPNotConnectedError',
    'PsFTPFileNotFoundError',
    'PsFTPInvalidPathError',
    'PsFTPUploadError',
    'PsFTPVerificationError',
]
