# Future experiments (idea backlog)

Recorded 2026-08-30 from project discussion. Roughly ordered by how much
new machinery each needs on top of the existing tiers.

## 1. Running under altered gravity

Nearly free on the current formulation: `predict_gait_2d` already sets
the gravity vector (the slope trick), so a gravity sweep (Moon 0.17 g,
Mars 0.38 g, hypo/hypergravity) is a chain like the slope grid.
Questions: how do cost of transport, preferred cadence, flight fraction,
and the walk→run transition scale with g? Strong literature anchors:
the transition should track Froude number (Fr ≈ 0.5 → v* ~ sqrt(g·L);
Kram, Domingo & Ferris 1997), and low-g COT measurements exist (Farley &
McMahon 1992; Minetti's lunar-locomotion analyses). A clean validation
target for the metabolic objective outside its fitting regime.

## 2. Limits of running speed with superhuman muscle

Scale muscle capacities (max isometric force, Vmax, or activation
dynamics) by 1.5–5x and let the predictive solver find top speed.
Questions: what binds as strength rises — ground-force production
(Weyand 2000/2010: speed is limited by stance-phase force, not swing),
leg-swing power, contact time floor, or tendon/loading limits? Compare
the emergent limiting factor against the sprint-simulation literature
(Miller et al. 2012). Needs: a max-speed formulation (maximize average
speed instead of prescribing it) — small change to the objective; the
LaiArnold high-flexion model beyond ~7 m/s.

## 3. Optimal running over technical terrain

Extend the slope work from constant grade to irregular profiles: step
placement, cadence modulation, and energy cost over rough/uneven ground.
Hard part: the periodic one-step formulation no longer applies — needs a
finite-horizon, non-periodic Moco problem over a terrain segment (or a
receding-horizon chain), and a terrain representation in the contact
model (heightfield half-space or per-step contact plane). Tier 0/1
payoff: a "terrain roughness" cost multiplier calibrated from Tier-3,
analogous to the Kerdok surface model. Validation: trail-running
energetics literature (e.g. Voloshina & Ferris uneven-terrain treadmill
data).

## 4. Physiological limiting factors: simulation vs performance literature

Use the simulator as an in-silico experiment on *what actually
saturates* at performance limits, and compare against the known
physiology: VO2max / critical speed (Tier-0's endurance model), muscle
force-velocity limits, contact-time floors, elastic energy return.
Method: sensitivity sweeps at maximal effort — perturb one capacity at
a time (aerobic ceiling, muscle strength, tendon stiffness, mass
distribution) and measure the marginal speed/COT response; the binding
constraint is the one with the largest shadow price. Compare the
emergent hierarchy with the performance literature (Joyner's marathon
limits model; Weyand's force hypothesis; di Prampero's energetics).
This is the capstone experiment — it needs a validated 3D model and
ideally Tier-2 tissue limits to be honest about injury-bounded regimes.

## Notes

- 1 and 2 are Tier-3-ready today (2D), and become publication-grade
  after the 3D milestone validates.
- 3 needs formulation work (non-periodic horizon) before any solving.
- 4 depends on the others: it consumes the validated model plus the
  max-speed formulation from 2.
