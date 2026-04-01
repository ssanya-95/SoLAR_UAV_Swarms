# Globecom Evaluation Plan

This repository now has the machinery needed for a more credible Globecom-style evaluation, but the publication-grade workflow should remain disciplined:

1. Tune SLAR weights only on training scenarios and training seeds.
2. Freeze the chosen weights.
3. Evaluate the frozen protocol on held-out test seeds across a scenario matrix.
4. Report mean, standard deviation, and 95% confidence intervals for each metric.
5. Use paired statistical tests against the baselines because the same random seeds are shared across protocols.

Recommended scenario axes:

- Density: vary the number of UAVs while keeping the simulation volume fixed.
- Traffic load: vary the number of packet injections and arrival burstiness.
- Mobility: vary the speed range and maneuver intensity.
- Channel severity: vary shadowing variance and communication range.

Minimum figure/table set:

- Weight-tuning heatmap on training scenarios.
- PDR versus scenario family with confidence intervals.
- Delivery latency versus scenario family with confidence intervals.
- Transmission attempts or retry pressure versus scenario family.
- Overall ranking table with PDR, latency, hops, and queue pressure.
- Paired significance table comparing tuned SLAR against GPSR, AODV, and SLAR-default.

Important publication caveat:

- Do not claim general superiority from one tuned operating point alone.
- Keep the tuning/evaluation split explicit in the paper.
- If you later add more baselines or more realistic mobility/channel models, rerun the full suite instead of mixing old and new numbers.
