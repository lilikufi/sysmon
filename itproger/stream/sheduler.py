import logging

from apscheduler.schedulers.background import BackgroundScheduler

from stream.views import check_hosts_status_back, check_nagios_stat

logger = logging.getLogger(__name__)

# Создаем планировщик
scheduler = BackgroundScheduler()

# Добавляем задачи
scheduler.add_job(check_hosts_status_back, 'interval', seconds=60)

scheduler.add_job(check_nagios_stat, 'interval', seconds=60)
#
# Задача для block_15 каждый день в 8:00 утра
# scheduler.add_job(
#     block_15,
#     trigger=CronTrigger(
#         day_of_week='*',  # Каждый день недели
#         hour=8,           # В 8 утра
#         minute=0,         # Начинать с начала часа
#     )
# )
#
# Запуск планировщика (если он еще не запущен)
if not scheduler.running:
    scheduler.start()
