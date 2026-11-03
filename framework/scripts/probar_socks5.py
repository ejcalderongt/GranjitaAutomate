"""Diagnóstico SOCKS5 autenticado con DNS remoto y TLS verificado."""
import argparse
from datetime import datetime, timezone
import http.client
import ipaddress
import json
from pathlib import Path
import socket
import ssl
import struct
import uuid

ROOT = Path(__file__).resolve().parents[1]


def exact(sock, count):
    data = b''
    while len(data) < count:
        part = sock.recv(count - len(data))
        if not part:
            raise ConnectionError('SOCKS truncated response')
        data += part
    return data


def parse_credentials(path):
    first = Path(path).read_text(encoding='utf-8-sig').splitlines()[0].strip()
    if '@' in first:
        auth, endpoint = first.rsplit('@', 1)
        user, password = auth.split(':', 1)
        host, port = endpoint.rsplit(':', 1)
    else:
        host, port, user, password = first.split(':', 3)
    return host, int(port), user, password


def fetch(config, host, path, events):
    endpoint, port, user, password = config
    sock = socket.create_connection((endpoint, port), timeout=20)
    try:
        sock.sendall(b'\x05\x01\x02')
        greeting = exact(sock, 2)
        events['socks_method'] = greeting.hex()
        if greeting != b'\x05\x02':
            raise ConnectionError('SOCKS authentication method rejected')
        username, secret = user.encode(), password.encode()
        if not 0 < len(username) <= 255 or not 0 < len(secret) <= 255:
            raise ValueError('SOCKS credential length invalid')
        sock.sendall(b'\x01' + bytes([len(username)]) + username + bytes([len(secret)]) + secret)
        auth = exact(sock, 2)
        events['authentication_status'] = auth[1]
        if auth != b'\x01\x00':
            raise ConnectionError('SOCKS authentication rejected')
        encoded = host.encode('idna')
        sock.sendall(b'\x05\x01\x00\x03' + bytes([len(encoded)]) + encoded + struct.pack('!H', 443))
        reply = exact(sock, 4)
        events['connect_reply'] = reply[1]
        if reply[0] != 5 or reply[1] != 0:
            raise ConnectionError('SOCKS CONNECT rejected')
        size = {1: 4, 4: 16}.get(reply[3])
        if reply[3] == 3:
            size = exact(sock, 1)[0]
        if size is None:
            raise ConnectionError('Invalid SOCKS address type')
        exact(sock, size + 2)
        tls = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        sock = tls
        tls.sendall(('GET ' + path + ' HTTP/1.1\r\nHost: ' + host + '\r\nUser-Agent: AGX-Network-Diagnostic/1\r\nConnection: close\r\n\r\n').encode())
        response = http.client.HTTPResponse(tls)
        response.begin()
        events['http_status'] = response.status
        if response.status != 200:
            raise ConnectionError('HTTPS response not successful')
        return json.loads(response.read(65536))
    finally:
        sock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('credentials', type=Path)
    args = parser.parse_args()
    report = {'protocol': 'SOCKS5', 'status': 'failed', 'ip_probe': {}, 'geo_probe': {},
              'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'SOCKS5 credentials and HTTPS; not a browser test'}
    try:
        config = parse_credentials(args.credentials)
        report['endpoint'] = config[0] + ':' + str(config[1])
        result = fetch(config, 'api.ipify.org', '/?format=json', report['ip_probe'])
        observed = str(ipaddress.ip_address(result['ip']))
        report['observed_ip'] = observed
        geo = fetch(config, 'ipapi.co', '/' + observed + '/json/', report['geo_probe'])
        report['continent_code'] = geo.get('continent_code')
        report['country_code'] = geo.get('country_code')
        report['region_verified'] = not geo.get('error') and geo.get('ip') == observed and geo.get('continent_code') == 'EU'
        report['status'] = 'passed' if report['region_verified'] else 'region_not_verified'
    except Exception as exc:
        report['error_type'] = type(exc).__name__
    destination = ROOT / 'runs' / ('socks5-preflight-' + uuid.uuid4().hex) / 'resultado.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    print('Reporte: ' + str(destination))
    return 0 if report['status'] == 'passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
