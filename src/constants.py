import os
import pathlib


# Directory structure
REPO_NAME = "fan_control_nvidia-ml-py"
WORK_DIR = os.getcwd()
LOG_DIR = os.path.join(WORK_DIR, "logs")
DEFAULT_CONFIG_FILE = os.path.join(WORK_DIR, "config.yml")

# Fan control related
DEFAULT_CTRL_INTERVAL_SEC = 1.0  # seconds
DEFAULT_TEMP_AVG_CNT = 5  # number of samples to average

# Log related
LOG_FILENAME = "fan_speed.log"
LOG_SIZE_LIMIT_MB = 1  # MB
LOG_FMT_BOLD = '\033[1m'
LOG_FMT_END = '\033[0m'
