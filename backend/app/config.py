# -*- coding: utf-8 -*-
"""后端建模参数配置。

所属模块：配置与参数层。

作用：集中定义多模式交通图和历史等时圈计算所使用的速度、候车、换乘与
等值面参数。这里的数值都是建模假设，不是实测数据，统一配置便于复现实验
口径。当前跑步路线自身的速度与回程惩罚参数在 ``running.py`` 中定义。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Params:
    """多模式交通图和历史等时圈计算的不可变参数集合。"""

    # 步行与站点接驳
    walk_speed_mps: float = 1.2          # 平均步行速度，约 4.3 km/h
    walk_access_max_m: float = 800.0     # 超过该距离的站点不再建立接驳边

    # 公交
    bus_speed_mps: float = 4.5           # 公交平均速度，约 16.2 km/h，包含信号延误
    bus_dwell_s: float = 25.0            # 每个中间站的平均停站时间
    bus_wait_s: float = 480.0            # 以发车间隔一半近似候车时间

    # 地铁
    metro_speed_mps: float = 9.5         # 地铁平均速度，约 34.2 km/h
    metro_dwell_s: float = 35.0          # 每个中间站的平均停站时间
    metro_wait_fallback_s: float = 240.0  # 缺少线路时刻时的后备候车时间

    # 换乘
    transfer_penalty_s: float = 90.0     # 换乘额外摩擦时间

    # 等时圈几何渲染
    hull_buffer_m: float = 60.0          # 等值面平滑与缓冲半径
    hull_simplify_m: float = 40.0        # 轮廓简化容差
    hull_max_points: int = 80_000        # 凹包计算使用的最大采样点数

    def ride_time(self, mode: str, distance_m: float) -> float:
        """计算一段公交或地铁行程的乘车时间，单位为秒。"""
        if mode == "bus":
            return distance_m / self.bus_speed_mps + self.bus_dwell_s
        if mode == "metro":
            return distance_m / self.metro_speed_mps + self.metro_dwell_s
        raise ValueError(f"unknown ride mode: {mode}")

    def to_dict(self) -> dict:
        """把参数转换为普通字典，供日志、文档或接口输出。"""
        return asdict(self)


# 全项目默认参数实例；调用方可以传入自定义 Params 覆盖默认值。
DEFAULT = Params()
