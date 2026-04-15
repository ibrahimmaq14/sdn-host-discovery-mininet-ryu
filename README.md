# SDN Host Discovery and Dynamic Monitoring using Mininet and Ryu

## Description
An SDN academic project that uses a Ryu OpenFlow 1.3 controller to discover hosts, learn MAC-to-port mappings, install forwarding flows dynamically, and optionally block a host for monitoring and policy demonstration.

## Problem Statement
Traditional networks rely on distributed device logic, which makes centralized visibility and dynamic policy enforcement difficult. This project demonstrates how Software Defined Networking (SDN) can centrally discover hosts, monitor host attachment points, and install forwarding or blocking rules dynamically using a Ryu controller with Mininet.

## Features
- OpenFlow 1.3 controller built with Ryu
- Switch feature handling and table-miss flow installation
- MAC learning using `mac_to_port` mapping
- Host discovery using a controller-side host database
- New host join logging with switch and port information
- Host movement detection when a MAC appears on a different port
- Dynamic flow installation for known destinations
- Flooding for unknown destinations
- Optional blocked-host policy using a source MAC drop rule
- Clear controller logging using `self.logger.info()`

## Technologies Used
- Python 3
- Ryu SDN Framework
- OpenFlow 1.3
- Mininet
- Open vSwitch (OVS)
- Ubuntu VM for execution environment

## Project Structure
```text
sdn-host-discovery-mininet-ryu/
├── host_discovery.py
├── requirements.txt
├── README.md
└── screenshots/
```

## Setup Instructions (Ubuntu VM)
Use an Ubuntu virtual machine because Mininet and Open vSwitch are typically run on Linux.

### 1. Update the system
```bash
sudo apt update
sudo apt upgrade -y
```

### 2. Install Python and networking tools
```bash
sudo apt install -y python3 python3-pip mininet openvswitch-switch
```

### 3. Create a project directory and copy the project files
Place `host_discovery.py`, `requirements.txt`, and `README.md` inside the project folder.

### 4. Install Python dependencies
```bash
pip3 install -r requirements.txt
```

## How to Run
Open two terminals inside the Ubuntu VM.

### Terminal 1: Start the Ryu controller
```bash
cd sdn-host-discovery-mininet-ryu
ryu-manager host_discovery.py
```

### Terminal 2: Start Mininet
Required base command:
```bash
sudo mn --topo single,3 --controller remote
```

Recommended OpenFlow 1.3 compatible command:
```bash
sudo mn --topo single,3 --controller remote,ip=127.0.0.1,port=6633 --switch ovsk,protocols=OpenFlow13
```

If Mininet was already started without the protocol flag, configure OVS explicitly:
```bash
sudo ovs-vsctl set Bridge s1 protocols=OpenFlow13
```

## Mininet Commands for Testing
Inside the Mininet CLI:

```bash
pingall
```

```bash
iperf
```

## Test Scenarios

### 1. Normal communication (`pingall`)
1. Start the controller.
2. Start Mininet with three hosts connected to a single switch.
3. Run:
   ```bash
   pingall
   ```
4. Observe that the controller logs host discovery events, learns MAC addresses, floods unknown destinations initially, and then installs flows for known destinations.

### 2. Blocked host scenario
1. Open `host_discovery.py`.
2. Change:
   ```python
   BLOCKED_SRC_MAC = None
   ```
   to a host MAC such as:
   ```python
   BLOCKED_SRC_MAC = "00:00:00:00:00:01"
   ```
3. Restart the Ryu controller.
4. Start Mininet and run:
   ```bash
   pingall
   ```
5. Traffic sourced from the blocked MAC will be dropped because the controller installs a high-priority flow with no output action.

## Expected Output

### Controller log examples
The controller should display readable logs similar to:

```text
Switch connected: datapath_id=0000000000000001 configured for OpenFlow 1.3
New host discovered: MAC=00:00:00:00:00:01 switch=0000000000000001 port=1
New host discovered: MAC=00:00:00:00:00:02 switch=0000000000000001 port=2
Installed flow: switch=0000000000000001 src=00:00:00:00:00:01 dst=00:00:00:00:00:02 in_port=1 out_port=2
Packet forwarded: switch=0000000000000001 src=00:00:00:00:00:03 dst=ff:ff:ff:ff:ff:ff in_port=3 out_port=FLOOD
```

### Flow table inspection
Use OVS to inspect installed flow entries:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows s1
```

Expected observations:
- A table-miss rule with priority `0`
- Learned forwarding rules with priority `10`
- If blocking is enabled, a drop rule with priority `200`

## Notes on Controller Logic

### PacketIn handling
- Receives packets that do not match existing switch flow entries
- Extracts source and destination MAC addresses
- Learns source MAC to port mapping
- Updates the host database for discovery and movement tracking
- Decides whether to flood or forward the packet

### Flow installation
- Uses a reusable `add_flow()` function
- Installs a table-miss rule during switch feature negotiation
- Installs priority `10` forwarding rules for known destinations
- Installs priority `200` drop rules for blocked source MAC addresses

### Host discovery logic
- A host is discovered when its source MAC appears in a `PacketIn`
- The controller stores switch ID, ingress port, first seen, and last seen time
- If the same MAC appears on a different port, host movement is logged

## Screenshots
Add screenshots to the `screenshots/` folder.

Suggested placeholders:
- `screenshots/controller-output.png`
- `screenshots/mininet-pingall.png`
- `screenshots/flow-table.png`

## Conclusion
This project demonstrates how SDN enables centralized host discovery, visibility, and policy control. Using Mininet and Ryu, the controller dynamically learns hosts, installs forwarding rules, and can enforce a simple blocking policy, making it suitable for academic demonstrations of OpenFlow-based network control.
