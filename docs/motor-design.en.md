# Rotary and annular-sector motor design

The rotary solver enumerates manufacturable integer turns. Each candidate resolves PCB geometry, copper length, 20 °C and hot phase resistance, approximate phase inductance, linked area, back-EMF, required phase current, voltage demand and copper loss.

The available fundamental line RMS voltage is modelled as `Vdc / sqrt(2)`. Voltage demand includes back-EMF, hot resistance and inductive drop. Torque current is derived from the phase RMS back-EMF constant. Annular-sector flux linkage sums the actual area enclosed by each nested turn.

This is a preliminary sizing model. It excludes detailed magnet geometry, mutual inductance, leakage, cogging, eddy currents, inverter drops and the complete thermal path.
