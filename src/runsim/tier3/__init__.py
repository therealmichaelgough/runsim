"""Tier 3: predictive musculoskeletal simulation (OpenSim Moco).

Phase-3 scope: 2D muscle-driven gait prediction (10 DoF, 18 muscles,
DeGroote-Fregly muscles with smooth contact spheres), periodic single-step
formulation with average-speed and effort goals, gravity rotation for
slopes. The 3D LaiUhlrich/Lai-Arnold pipeline builds on the same interface.
"""
from runsim.tier3.predict2d import predict_gait_2d, solution_summary

__all__ = ["predict_gait_2d", "solution_summary"]
