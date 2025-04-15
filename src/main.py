import logging
import pynvml as nvml
import time

from device import Device
from utils.cmd_parser import cmd_parser
from utils.speed_profile import check_speed_profile
from utils.miscs import load_yaml
from utils.logging import init_root_logger, get_logger


def main():
  args = cmd_parser()

  config = load_yaml(args.config)

  init_root_logger(args.log_level == logging.DEBUG)
  logger = get_logger("main", args.log_level)
  logger.debug(args)

  logger.info(f"Expecting {len(config['gpus'])} GPUs.")

  # initialize nvidia management lib
  nvml.nvmlInit()

  # initialize devices
  logger.info(f"Driver Version: {nvml.nvmlSystemGetDriverVersion()}")
  gpus = []
  for i in range(nvml.nvmlDeviceGetCount()):
    if i not in config["gpus"]:
      logger.debug(f"GPU {i} is not in the config file.")
      continue

    try:
      device = Device(i, config["gpus"][i], args.temp_avg_cnt, args.log_level)
      gpus.append(device)
    except RuntimeError as e:
      logger.warning(f"GPU {i} initialization failed: {e}")
      continue


  # fan control service (reset to default upon exit)
  try:
    while True:
      for device in gpus:
        device.control()
      time.sleep(args.control_interval)

  finally:
    logger.info("Reset to the default fan control policy!")
    for device in gpus:
      device.reset_to_default_policy()

  # end nvidia management lib
  nvml.nvmlShutdown()


if __name__ == "__main__":
  main()
