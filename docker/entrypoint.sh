#!/bin/sh
set -eu

python itproger/manage.py migrate --noinput
python itproger/manage.py collectstatic --noinput --verbosity 0

exec "$@"
