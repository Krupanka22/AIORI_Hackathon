##
## AIORI - Zeek IPv6 Monitor Script
## Custom script for monitoring IPv6 address changes and traffic patterns.
##

module AioriIPv6;

export {
    ## Notice type for IPv6 address rotation detection
    redef enum Notice::Type += {
        IPv6_Address_Rotation,
        IPv6_New_Device_Seen,
        IPv6_Unusual_Traffic_Volume,
    };

    ## Track known IPv6 addresses (populated from AIORI backend)
    global known_ipv6_addrs: set[addr] = set() &redef;

    ## Track per-address byte counters
    global addr_bytes: table[addr] of count = table() &default=0;

    ## Threshold for unusual volume alert (bytes in 60 seconds)
    const volume_threshold: count = 10000000 &redef;  # 10 MB
}

event connection_state_remove(c: connection) {
    local orig = c$id$orig_h;
    local resp = c$id$resp_h;

    # Track bytes per address
    if (c$conn?$orig_bytes)
        addr_bytes[orig] += c$conn$orig_bytes;
    if (c$conn?$resp_bytes)
        addr_bytes[resp] += c$conn$resp_bytes;

    # Detect new addresses not in known set
    if (orig !in known_ipv6_addrs && is_v6_addr(orig)) {
        add known_ipv6_addrs[orig];
        NOTICE([
            $note=IPv6_New_Device_Seen,
            $msg=fmt("New IPv6 address observed: %s", orig),
            $src=orig,
            $identifier=cat(orig),
        ]);
    }

    if (resp !in known_ipv6_addrs && is_v6_addr(resp)) {
        add known_ipv6_addrs[resp];
        NOTICE([
            $note=IPv6_New_Device_Seen,
            $msg=fmt("New IPv6 address observed: %s", resp),
            $src=resp,
            $identifier=cat(resp),
        ]);
    }
}

# Periodic check for volume anomalies
event zeek_done() {
    for (a, bytes in addr_bytes) {
        if (bytes > volume_threshold) {
            NOTICE([
                $note=IPv6_Unusual_Traffic_Volume,
                $msg=fmt("High traffic volume from %s: %d bytes", a, bytes),
                $src=a,
                $identifier=cat(a),
            ]);
        }
    }
}
