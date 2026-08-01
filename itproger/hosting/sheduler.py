import logging
import os
from logging.handlers import TimedRotatingFileHandler

from apscheduler.schedulers.background import BackgroundScheduler

# from .views import check_hosts_status_back, nagios_1111, get_snmp_info_and_save_to_file

# log_directory = './'
# log_filename = 'scheduler.log'
# log_path = os.path.join(log_directory, log_filename)
# handler = TimedRotatingFileHandler(log_path, when="midnight", interval=1, backupCount=7)
# handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
#
# logger = logging.getLogger()
# logger.setLevel(logging.INFO)
# logger.addHandler(handler)

#
# scheduler = BackgroundScheduler()
# scheduler.add_job(check_hosts_status_back, 'interval', seconds=60)
# if not scheduler.running:
#     scheduler.start()
# scheduler = BackgroundScheduler()
# scheduler.add_job(nagios_1111, 'interval', seconds=60)
# if not scheduler.running:
#     scheduler.start()

