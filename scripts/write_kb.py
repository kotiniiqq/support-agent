"""Writes the synthetic knowledge base (src/support_agent/kb/*.md).

Kept as a script so the articles stay reviewable in one place and can be regenerated.
"""
from pathlib import Path

KB = Path(__file__).resolve().parent.parent / "src" / "support_agent" / "kb"

ARTICLES = {
    "restart-server": ("Restart your game server", "restart, reboot, stop, start, frozen", """
## Summary
You can restart a server yourself from the control panel. A restart takes about a minute and does not delete any files.

## Steps
1. Open the control panel and select your server.
2. Press Restart. If the server does not respond, press Stop, wait 30 seconds, then press Start.
3. Watch the console until it shows "Done" or "Server started".
"""),
    "change-game-version": ("Change the game version", "version, update, downgrade, minecraft, 1.20, 1.21", """
## Summary
The game version is chosen in the panel under Settings. Changing it reinstalls the server files but keeps your worlds; make a backup first.

## Steps
1. Create a backup (see "Create and restore backups").
2. Open Settings, choose the version from the Version list and press Save.
3. Restart the server. Plugins built for another version may need updating.
"""),
    "install-mods": ("Install mods and plugins", "mods, plugins, modpack, forge, fabric, spigot, paper", """
## Summary
Mods and plugins are installed from the Mods tab or uploaded through SFTP into the mods or plugins folder.

## Steps
1. For one-click installs open the Mods tab, search for the mod and press Install.
2. For your own files connect via SFTP and upload the .jar into /mods (Forge, Fabric) or /plugins (Spigot, Paper).
3. Restart the server and check the console for errors about missing dependencies.
"""),
    "backups": ("Create and restore backups", "backup, restore, rollback, lost world, deleted", """
## Summary
Automatic backups run every night and are kept for 7 days. You can also make a manual backup at any time.

## Steps
1. Open the Backups tab and press Create backup for a manual copy.
2. To restore, choose a backup from the list and press Restore. The server stops during the restore.
3. Restoring replaces the current files, so create a fresh backup first if you may need them.
"""),
    "sftp-access": ("Connect to your server with SFTP", "sftp, ftp, filezilla, files, upload, credentials", """
## Summary
Files are managed over SFTP. The host, port and username are shown in the panel under SFTP details; the password is your panel password.

## Steps
1. Open SFTP details in the panel and copy the host, port and username.
2. In FileZilla or WinSCP choose the SFTP protocol and enter these details.
3. If the connection is refused, check that you use SFTP and not plain FTP, and that the port is the one shown in the panel.
"""),
    "ddos-protection": ("DDoS protection and lag during attacks", "ddos, attack, flood, protection, packet loss", """
## Summary
All servers are behind always-on DDoS protection. During a large attack players can notice short lag spikes while traffic is filtered.

## Steps
1. Check the Network tab: an attack is shown as a red marker on the traffic graph.
2. Short spikes during filtering are expected and need no action.
3. If lag lasts more than 15 minutes, restart the server; if it continues, reply to this ticket with the time it started.
"""),
    "server-lag": ("Fix server lag and low TPS", "lag, tps, slow, performance, ram, memory, ticks", """
## Summary
Most lag comes from too little memory for the number of players and mods, or from a few heavy plugins and entities.

## Steps
1. Open the Metrics tab and check memory use; if it stays above 90%, reduce mods or upgrade the plan.
2. Lower the view distance in server.properties to 6–8.
3. Install a profiler plugin such as Spark to find the plugin or entity that uses the most time.
"""),
    "ports-firewall": ("Open additional ports", "port, ports, firewall, voice, dynmap, query", """
## Summary
Each server has one game port. Extra ports for voice chat, web maps or query can be added in the Network tab.

## Steps
1. Open the Network tab and press Add port.
2. Use the assigned port number in your plugin configuration.
3. Restart the server so the plugin binds to the new port.
"""),
    "upgrade-plan": ("Upgrade or downgrade your plan", "upgrade, downgrade, plan, more ram, slots", """
## Summary
You can move to a bigger or smaller plan from the panel; files and worlds are kept and the change takes effect after a restart.

## Steps
1. Open Plan in the panel and choose the new plan.
2. Confirm the change; the server restarts automatically.
3. Plan changes keep your IP address and files.
"""),
    "custom-domain": ("Use your own domain name", "domain, dns, srv, address, ip, cname", """
## Summary
Players can join with your own domain instead of the IP. Point the domain at the server with an SRV record.

## Steps
1. In your DNS provider create an A record (for example play.example.com) pointing to the server IP.
2. Add an SRV record _minecraft._tcp.play.example.com with the server port.
3. DNS changes can take up to an hour to apply.
"""),
    "server-wont-start": ("Server does not start or crashes", "crash, crashes, wont start, error, startup, logs, console", """
## Summary
A server that stops right after starting usually has a broken mod, a wrong Java version or a corrupted config. The console log names the cause.

## Steps
1. Open the Console tab and read the last error lines before the crash.
2. If a mod is named, remove it from /mods via SFTP and start again.
3. If the log mentions Java, choose the Java version that matches your game version in Settings.
"""),
    "sub-users": ("Give friends access to the panel", "subuser, sub-user, friend, access, permissions, admin", """
## Summary
You can invite other people to manage the server without sharing your password, with permissions you choose.

## Steps
1. Open Users in the panel and press Invite.
2. Enter their e-mail and tick the permissions they need, for example Console or Files.
3. They receive an invitation and log in with their own account.
"""),
    "upload-world": ("Upload an existing world", "world, upload, map, save, singleplayer", """
## Summary
A world from your computer or another host can be uploaded over SFTP.

## Steps
1. Stop the server.
2. Upload the world folder over SFTP and name it as level-name in server.properties (usually "world").
3. Start the server; the first start with a large world can take a few minutes.
"""),
}


def main() -> None:
    KB.mkdir(parents=True, exist_ok=True)
    for article_id, (title, tags, body) in ARTICLES.items():
        text = f"---\nid: {article_id}\ntitle: {title}\ntags: [{tags}]\n---\n{body.lstrip()}"
        (KB / f"{article_id}.md").write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {len(ARTICLES)} articles to {KB}")


if __name__ == "__main__":
    main()
