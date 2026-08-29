"""runsim: human running simulator.

Tiered architecture:
  Tier 0 (energetics)  - closed-form environment/gait cost models
  Tier 1 (mechanics)   - spring-mass / two-mass GRF surrogates
  Tier 2 (tissue)      - tissue-load surrogates + fatigue damage
  Tier 3 (msk)         - OpenSim Moco musculoskeletal inner loop
"""

__version__ = "0.1.0"
