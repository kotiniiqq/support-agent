---
id: server-lag
title: Fix server lag and low TPS
tags: [lag, tps, slow, performance, ram, memory, ticks]
---
## Summary
Most lag comes from too little memory for the number of players and mods, or from a few heavy plugins and entities.

## Steps
1. Open the Metrics tab and check memory use; if it stays above 90%, reduce mods or upgrade the plan.
2. Lower the view distance in server.properties to 6–8.
3. Install a profiler plugin such as Spark to find the plugin or entity that uses the most time.
