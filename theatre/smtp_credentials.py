import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings


def _cipher():
    key = hashlib.sha256(('surgeon-smtp-v1:' + settings.SMTP_CREDENTIAL_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_password(value):
    return _cipher().encrypt(value.encode()).decode() if value else ''


def decrypt_password(value):
    return _cipher().decrypt(value.encode()).decode() if value else ''
