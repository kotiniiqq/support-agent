---
id: custom-domain
title: Use your own domain name
tags: [domain, dns, srv, address, ip, cname]
---
## Summary
Players can join with your own domain instead of the IP. Point the domain at the server with an SRV record.

## Steps
1. In your DNS provider create an A record (for example play.example.com) pointing to the server IP.
2. Add an SRV record _minecraft._tcp.play.example.com with the server port.
3. DNS changes can take up to an hour to apply.
