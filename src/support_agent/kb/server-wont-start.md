---
id: server-wont-start
title: Server does not start or crashes
tags: [crash, crashes, wont start, error, startup, logs, console]
---
## Summary
A server that stops right after starting usually has a broken mod, a wrong Java version or a corrupted config. The console log names the cause.

## Steps
1. Open the Console tab and read the last error lines before the crash.
2. If a mod is named, remove it from /mods via SFTP and start again.
3. If the log mentions Java, choose the Java version that matches your game version in Settings.
