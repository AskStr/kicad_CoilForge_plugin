# Linear motor thrust and speed design

Linear target mode uses thrust in newtons and translator speed in metres per second. With pole pitch `tau`, electrical frequency is estimated as `f = v / (2 tau)`. The phase back-EMF constant follows from the resolved linked area, flux density, winding factor and coils per phase. The power-consistent relation `F = 3 K_e I_phase` determines required RMS phase current.

The solver checks DC-bus utilization, hot resistance drop, inductive drop, trace current capacity and manufacturing limits while selecting integer turns. Linear pitch may be zero for automatic collision-safe spacing.

The model assumes a sinusoidal three-phase field and uniform effective air-gap flux. Validate force ripple, end effects, magnet coverage and thermal performance with simulation and a prototype.
