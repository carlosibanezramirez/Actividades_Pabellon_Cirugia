import os
os.environ.setdefault('DJANGO_SECRET_KEY', 'test-only-key-not-for-deployment-12345678901234567890')
os.environ['DJANGO_DEBUG'] = 'true'
from .settings import *  # noqa: F403

if os.getenv('TEST_SQLITE') == '1':
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
