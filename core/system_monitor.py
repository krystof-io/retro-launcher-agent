import psutil
from typing import Dict
import logging

logger = logging.getLogger(__name__)

class SystemMonitor:
    @staticmethod
    def get_system_stats() -> Dict:
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            temperature = None
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps and "cpu_thermal" in temps:
                    temperature = temps["cpu_thermal"][0].current

            return {
                "cpuUsage": cpu_percent,
                "memoryUsage": memory.percent,
                "temperature": temperature
            }
        except Exception as e:
            logger.error(f"Error getting system stats: {e}")
            return {}