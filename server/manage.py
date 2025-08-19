import django.conf
import sys
import pathlib
import os
from server.secrets import get_config

# Get configuration from Secrets Manager or .env fallback
config = get_config()

# Required for importing the server app (upper dir)
file = pathlib.Path(__file__).resolve()
root = file.parents[1]
sys.path.append(str(root))

INSTALLED_APPS = [
    'server'
]

DATABASES = {
    'default': {
        'ENGINE': config['DB_ENGINE'],
        'NAME': config['DB_NAME'],
        'USER': config['DB_USER'],
        'PASSWORD': config['DB_PASSWORD'],
        'HOST': config['DB_HOST'],
        'PORT': config['DB_PORT'],
    }
}

django.conf.settings.configure(
    INSTALLED_APPS=INSTALLED_APPS,
    DATABASES=DATABASES,
    DEFAULT_AUTO_FIELD='django.db.models.AutoField'
)

django.setup()


if __name__ == '__main__':
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)