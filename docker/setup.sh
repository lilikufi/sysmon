#!/bin/sh
set -eu

python itproger/manage.py migrate --noinput
python itproger/manage.py setup_deployment
