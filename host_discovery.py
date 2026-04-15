"""
Ryu controller for SDN host discovery and dynamic monitoring.

Features:
- OpenFlow 1.3 support
- Table-miss flow installation
- MAC learning switch behavior
- Host discovery and host database maintenance
- Dynamic flow installation for known destinations
- Optional blocking rule for a specific source MAC address
"""

from datetime import datetime

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.lib.packet import packet
from ryu.ofproto import ofproto_v1_3


class HostDiscoveryController(app_manager.RyuApp):
    """Learning-switch controller with host discovery and optional blocking."""

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    # Set this value to a host MAC address such as "00:00:00:00:00:01" to
    # block traffic from that host. Leave it as None to disable blocking.
    BLOCKED_SRC_MAC = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.host_db = {}

    def add_flow(self, datapath, priority, match, actions=None, buffer_id=None):
        """
        Install a flow entry on the switch.

        If actions is empty, the switch installs a drop rule. This is useful
        for the optional blocked-host demonstration.
        """
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        instructions = []
        if actions:
            instructions.append(
                parser.OFPInstructionActions(
                    ofproto.OFPIT_APPLY_ACTIONS,
                    actions,
                )
            )

        if buffer_id is not None:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                buffer_id=buffer_id,
                priority=priority,
                match=match,
                instructions=instructions,
            )
        else:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                priority=priority,
                match=match,
                instructions=instructions,
            )

        datapath.send_msg(mod)

    def _install_table_miss_flow(self, datapath):
        """Send unmatched packets to the controller."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(
                ofproto.OFPP_CONTROLLER,
                ofproto.OFPCML_NO_BUFFER,
            )
        ]
        self.add_flow(datapath, priority=0, match=match, actions=actions)

    def _install_block_rule(self, datapath, blocked_mac):
        """Install a high-priority drop rule for a blocked source MAC."""
        parser = datapath.ofproto_parser

        match = parser.OFPMatch(eth_src=blocked_mac)
        self.add_flow(datapath, priority=200, match=match, actions=[])
        self.logger.info(
            "Installed blocking rule on switch %016x for source MAC %s",
            datapath.id,
            blocked_mac,
        )

    def _current_timestamp(self):
        """Return a readable UTC timestamp for logging and host records."""
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    def _update_host_database(self, dpid, src_mac, in_port):
        """
        Track hosts discovered from PacketIn events.

        A host is considered newly discovered when its MAC address is seen for
        the first time. Host movement between ports is also detected and logged.
        """
        current_time = self._current_timestamp()
        existing_host = self.host_db.get(src_mac)

        if existing_host is None:
            self.host_db[src_mac] = {
                "dpid": dpid,
                "port": in_port,
                "first_seen": current_time,
                "last_seen": current_time,
            }
            self.logger.info(
                "New host discovered: MAC=%s switch=%016x port=%s",
                src_mac,
                dpid,
                in_port,
            )
            return

        if existing_host["dpid"] != dpid or existing_host["port"] != in_port:
            self.logger.info(
                "Host moved: MAC=%s old_switch=%016x old_port=%s new_switch=%016x new_port=%s",
                src_mac,
                existing_host["dpid"],
                existing_host["port"],
                dpid,
                in_port,
            )
            existing_host["dpid"] = dpid
            existing_host["port"] = in_port

        existing_host["last_seen"] = current_time

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """
        Configure the switch when it connects.

        This installs:
        - a table-miss rule to forward unknown packets to the controller
        - an optional high-priority drop rule for a blocked host
        """
        datapath = ev.msg.datapath
        self.mac_to_port.setdefault(datapath.id, {})

        self._install_table_miss_flow(datapath)
        self.logger.info(
            "Switch connected: datapath_id=%016x configured for OpenFlow 1.3",
            datapath.id,
        )

        if self.BLOCKED_SRC_MAC:
            self._install_block_rule(datapath, self.BLOCKED_SRC_MAC)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """
        Process packets sent to the controller.

        PacketIn handling performs three main tasks:
        1. Learn the source MAC to build switch forwarding state
        2. Discover or update host information in the host database
        3. Decide whether to flood, forward, or install a matching flow
        """
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth_pkt = pkt.get_protocol(ethernet.ethernet)

        if eth_pkt is None:
            return

        if eth_pkt.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        src_mac = eth_pkt.src
        dst_mac = eth_pkt.dst

        self.mac_to_port.setdefault(dpid, {})

        if msg.msg_len < msg.total_len:
            self.logger.info(
                "Packet truncated: received=%s expected=%s",
                msg.msg_len,
                msg.total_len,
            )

        # Host discovery logic updates the in-memory database whenever a host
        # sends traffic through the switch.
        self._update_host_database(dpid, src_mac, in_port)

        # MAC learning remembers where a source MAC was last observed.
        self.mac_to_port[dpid][src_mac] = in_port

        if self.BLOCKED_SRC_MAC and src_mac.lower() == self.BLOCKED_SRC_MAC.lower():
            self.logger.info(
                "Dropping packet from blocked host: MAC=%s switch=%016x port=%s",
                src_mac,
                dpid,
                in_port,
            )
            self._install_block_rule(datapath, src_mac)
            return

        if dst_mac in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst_mac]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # When the destination is known, install a flow so future packets are
        # forwarded in the data plane without involving the controller.
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_src=src_mac, eth_dst=dst_mac)
            self.add_flow(
                datapath=datapath,
                priority=10,
                match=match,
                actions=actions,
                buffer_id=msg.buffer_id if msg.buffer_id != ofproto.OFP_NO_BUFFER else None,
            )
            self.logger.info(
                "Installed flow: switch=%016x src=%s dst=%s in_port=%s out_port=%s",
                dpid,
                src_mac,
                dst_mac,
                in_port,
                out_port,
            )

            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                return

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None,
        )
        datapath.send_msg(out)

        forwarding_action = "FLOOD" if out_port == ofproto.OFPP_FLOOD else str(out_port)
        self.logger.info(
            "Packet forwarded: switch=%016x src=%s dst=%s in_port=%s out_port=%s",
            dpid,
            src_mac,
            dst_mac,
            in_port,
            forwarding_action,
        )
