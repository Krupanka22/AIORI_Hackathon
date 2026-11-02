##
## AIORI - Zeek Configuration
## Local site policy for IPv6 IoT monitoring.
## Deploy to /usr/local/zeek/share/zeek/site/local.zeek on the WSL2 instance.
##

# Load base frameworks
@load base/frameworks/notice
@load base/protocols/conn
@load base/protocols/dns
@load base/protocols/http
@load base/protocols/ssl

# Load protocol analyzers relevant to IoT traffic
@load protocols/conn/known-hosts
@load protocols/conn/known-services

# Enable JSON output for structured log parsing
redef LogAscii::use_json = T;

# Connection logging settings
redef Conn::default_table_size = 100000;

# Focus on IPv6 traffic
redef ignore_checksums = T;

# Extend connection log with additional fields
redef record Conn::Info += {
    ## Track if this connection involves our ULA prefix
    is_aiori_traffic: bool &default=F &log;
};

# ULA prefix for AIORI virtual network
const aiori_prefix = fd00:a101::/64 &redef;

event connection_state_remove(c: connection) {
    if (c$id$orig_h in aiori_prefix || c$id$resp_h in aiori_prefix) {
        c$conn$is_aiori_traffic = T;
    }
}

# Log rotation settings
redef Log::default_rotation_interval = 1hr;

# Disable unneeded heavy-weight analyzers for lightweight operation
redef dpd_reassemble_first_packets = F;
