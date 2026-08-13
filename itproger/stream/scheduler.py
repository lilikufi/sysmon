import os

from apscheduler.schedulers.background import BackgroundScheduler

from stream.views import check_hosts_status_back, check_nagios_stat


scheduler = BackgroundScheduler()
scheduler.add_job(check_hosts_status_back, 'interval', seconds=60)
if os.getenv('NAG_SERVER', '').strip():
    scheduler.add_job(check_nagios_stat, 'interval', seconds=60)

if not scheduler.running:
    scheduler.start()
