import pynvml as nvml
from operator import itemgetter
from typing import List, Tuple
import os

from utils.logging import get_logger

TEMP_MIN_VALUE = 20.0 # fan is around 30%
TEMP_MAX_VALUE = 60.0 # fan is at 100% onwards
TEMP_RANGE = TEMP_MAX_VALUE - TEMP_MIN_VALUE

def fanspeed_from_t(t):
  if t <= TEMP_MIN_VALUE: return 0.0
  if t >= TEMP_MAX_VALUE: return 1.0
  return (t - TEMP_MIN_VALUE) / TEMP_RANGE

class Device:
  """Device class for one GPU."""
  def __init__(self, index: int, config: dict, temp_avg_cnt: int, log_level: int) -> None:
    self.index = index
    self.logger = get_logger(self.__class__.__name__, log_level)

    self.handle = nvml.nvmlDeviceGetHandleByIndex(index)
    self.name = nvml.nvmlDeviceGetName(self.handle)
    self.logger.debug(f"GPU {index}: {self.name}")

    if config["mode"] == 0:
      self.mode = 0
      self.fan_count = nvml.nvmlDeviceGetNumFans(self.handle)

      if self.fan_count < 1:
        raise RuntimeError(f"GPU {index} has no fans!")

      self.fan_min, self.fan_max = self.get_device_min_max_fan_speed(self.handle)
    elif config["mode"] == 1:
      self.mode = 1
      self.fan_count = 1

      if type(config["pwm"]) is not dict or type(config["pwm"]["path"]) is not str or not os.path.exists(config["pwm"]["path"]):
        raise RuntimeError(f"Invalid PWM config for GPU {index}!")

      self.pwm_path = config["pwm"]["path"]
      self.fan_min = max(0, config["pwm"]["min"]) if config["pwm"]["min"] is not None else 0
      self.fan_max = min(100, config["pwm"]["max"]) if config["pwm"]["max"] is not None else 100

      with open(self.pwm_path + "_enable", "r") as f:
        self.restore_enable = int(f.read().strip())

      with open(self.pwm_path, "r") as f:
        self.restore_speed = int(f.read().strip())

      with open(self.pwm_path + "_enable", "w") as f:
        f.write("1")
    else:
      raise RuntimeError(f"Invalid mode {config.mode} for GPU {index}!")

    self.logger.debug(f"  Fan count: {self.fan_count}")
    self.logger.debug(f"  Fan speed range: {self.fan_min} - {self.fan_max}")

    self.speed_profile = list(config["profile"].items())
    sorted(self.speed_profile, key=itemgetter(0))  # sort by temp set points
    self.temp_avg_cnt = temp_avg_cnt
    self.temp_avg_idx = 0
    self.temp_history = [-1] * temp_avg_cnt

  def get_device_min_max_fan_speed(self, handle) -> Tuple[int, int]:
    """Fetch fan speed limit of a certain GPU, usually 0-100."""
    c_minSpeed = nvml.c_uint()
    c_maxSpeed = nvml.c_uint()
    fn = nvml._nvmlGetFunctionPointer("nvmlDeviceGetMinMaxFanSpeed")
    ret = fn(handle, nvml.byref(c_minSpeed), nvml.byref(c_maxSpeed))
    nvml._nvmlCheckReturn(ret)
    return c_minSpeed.value, c_maxSpeed.value

  def reset_to_default_policy(self) -> None:
    """Reset fan policy to default."""
    if self.mode == 0:
      for i in range(self.fan_count):
        nvml.nvmlDeviceSetDefaultFanSpeed_v2(self.handle, i)
    elif self.mode == 1:
      with open(self.pwm_path, "w") as f:
        f.write(str(self.restore_speed))

      with open(self.pwm_path + "_enable", "w") as f:
        f.write(str(self.restore_enable))

  def get_cur_temp(self) -> int:
    return nvml.nvmlDeviceGetTemperature(self.handle, nvml.NVML_TEMPERATURE_GPU)

  def get_cur_fan_speed(self) -> int:
    if self.mode == 0:
      speeds = [nvml.nvmlDeviceGetFanSpeed_v2(self.handle, i) for i in range(self.fan_count)]

      return round(sum(speeds)/len(speeds))
    elif self.mode == 1:
      with open(self.pwm_path, "r") as f:
        pwm = int(f.read().strip())

      return round(pwm * 100 / 255)

    return 0

  def set_fan_speed(self, percentage) -> None:
    """
    Manually set the new fan speed.
    WARNING: This function changes the fan control policy to manual.
    It means that YOU have to monitor the temperature and adjust the fan speed accordingly.
    If you set the fan speed too low you can burn your GPU!
    Use nvmlDeviceSetDefaultFanSpeed_v2 to restore default control policy.
    """
    if self.mode == 0:
      for i in range(self.fan_count):
        nvml.nvmlDeviceSetFanSpeed_v2(self.handle, i, percentage)
    elif self.mode == 1:
      with open(self.pwm_path, "w") as f:
        f.write(str(round(percentage * 255 / 100)))

  def calc_fan_speed(self, t: float, speed_profile: List[Tuple[int, int]]) -> float:
    """Calcute the desired speed given a temperature."""

    for i in range(len(speed_profile) - 1):
      if t <= speed_profile[i][0]:
        if i == 0:
          return speed_profile[i][1]
        else:
          l_t = speed_profile[i - 1][0]
          r_t = speed_profile[i][0]
          l_s = speed_profile[i - 1][1]
          r_s = speed_profile[i][1]

          slope = (r_s - l_s) / (r_t - l_t)

          return l_s + slope * (t - l_t)

    return speed_profile[-1][1]

  def control(self) -> None:
    """Calculate new speed and compare with old speed, set new speed if different"""
    t = self.get_cur_temp()

    self.temp_history[self.temp_avg_idx] = t
    self.temp_avg_idx = (self.temp_avg_idx + 1) % self.temp_avg_cnt

    if self.temp_history[self.temp_avg_idx] >= 0:
      t = sum(self.temp_history) / self.temp_avg_cnt
    elif self.temp_avg_idx > 1:
      return

    new_speed_f = self.calc_fan_speed(t, self.speed_profile)
    new_speed = round(new_speed_f)
    cur_speed = self.get_cur_fan_speed()

    if new_speed != cur_speed:
      self.logger.info(f"GPU {self.index} ({self.name}) T:{t:.2f} S:{cur_speed} N:{new_speed} ({new_speed_f:.2f})")
      self.set_fan_speed(new_speed)
