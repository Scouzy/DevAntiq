"""Refuse to enable the gateway while inventoried backends bind a public interface."""
import subprocess
import json
import ipaddress

ports = {3001, 3220, 3010, 5173, 3210, 3300, 8090, 5678, 20128, 9099, 9092}
output = subprocess.check_output(['ss', '-lntH'], text=True)
exposed = []
for line in output.splitlines():
    fields = line.split()
    if len(fields) < 4:
        continue
    address, _, port = fields[3].rpartition(':')
    if port.isdigit() and int(port) in ports and address.strip('[]') not in ('127.0.0.1', '::1'):
        exposed.append(fields[3])
# Docker NAT may publish ports without a listening userland-proxy socket.
containers = subprocess.check_output(['docker', 'ps', '-q'], text=True).split()
if containers:
    port_maps = subprocess.check_output(['docker', 'inspect', '--format', '{{json .NetworkSettings.Ports}}', *containers], text=True)
    for line in port_maps.splitlines():
        for bindings in (json.loads(line) or {}).values():
            for binding in bindings or []:
                address = binding.get('HostIp') or '0.0.0.0'
                if int(binding['HostPort']) in ports and not ipaddress.ip_address(address).is_loopback:
                    exposed.append(address + ':' + binding['HostPort'])
if exposed:
    raise SystemExit('Origines accessibles hors loopback : ' + ', '.join(exposed) + '. Restreindre ces ports avant activation des applications.')
print('Ports applicatifs inventoriÃ©s : aucune Ã©coute publique dÃ©tectÃ©e.')
