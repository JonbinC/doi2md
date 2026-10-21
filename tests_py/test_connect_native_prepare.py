"""Native build input checks and real supervised smoke logic, without a desktop claim."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('connect_native_prepare', ROOT / 'connect/native/prepare.py')
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


@pytest.mark.parametrize('system,machine,target', [
    ('Darwin', 'arm64', 'aarch64-apple-darwin'),
    ('Darwin', 'x86_64', 'x86_64-apple-darwin'),
    ('Windows', 'AMD64', 'x86_64-pc-windows-msvc'),
    ('Linux', 'aarch64', 'aarch64-unknown-linux-gnu'),
    ('Linux', 'x86_64', 'x86_64-unknown-linux-gnu'),
])
def test_only_matching_host_architecture_can_prepare(system, machine, target, monkeypatch):
    monkeypatch.setattr(prepare.platform, 'system', lambda: system)
    monkeypatch.setattr(prepare.platform, 'machine', lambda: machine)
    prepare.validate_host(target)
    for other in prepare.TARGETS:
        if other != target:
            with pytest.raises(ValueError, match='matching target'):
                prepare.validate_host(other)


@pytest.mark.parametrize('version,expected', [('v22.19.0\n', '22.19.0'), ('22.23.1', '22.23.1'), ('v24.0.0', '24.0.0')])
def test_supported_stable_node_versions(version, expected):
    assert prepare.parse_node_version(version) == expected


@pytest.mark.parametrize('version', ['v22.18.9', 'v20.99.0', 'v22.19.0-beta.1', 'v22.19', '../../LICENSE', 'v22.19.0\nprivate-output'])
def test_bad_node_versions_do_not_become_paths_or_supported_runtimes(version):
    with pytest.raises(ValueError, match='stable Node'):
        prepare.parse_node_version(version)


def test_windows_npm_runs_javascript_directly_without_a_shell(tmp_path, monkeypatch):
    # Spaces and shell punctuation must stay inside one subprocess argument.
    installation = tmp_path / 'Node runtime & tools'
    cli = installation / 'node_modules/npm/bin/npm-cli.js'
    cli.parent.mkdir(parents=True)
    cli.write_text('// npm entry')
    monkeypatch.setattr(prepare.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(prepare.shutil, 'which', lambda name: str(installation / 'npm.cmd'))
    node = installation / 'node.exe'
    assert prepare.npm_command(node) == [str(node), str(cli)]
    cli.unlink()
    with pytest.raises(ValueError, match='entry point is missing'):
        prepare.npm_command(node)


def test_bundled_node_keeps_complete_local_third_party_notices(tmp_path, monkeypatch):
    node = tmp_path / 'distribution/node'
    node.parent.mkdir()
    notices = b'Node.js notices\nPermission is hereby granted\nAdditional dependency license notices\n'
    (node.parent / 'LICENSE').write_bytes(notices)
    monkeypatch.setattr(prepare, 'urlopen', lambda *args, **kwargs: pytest.fail('Local notices should not need the network'))
    destination = tmp_path / 'bundled-NODE-LICENSE'
    prepare.bundle_node_license(node, '22.19.0', destination)
    assert destination.read_bytes() == notices


def test_smoke_environment_never_inherits_credentials_or_python_node_hooks(tmp_path, monkeypatch):
    for name in ['MDTERO_API_KEY', 'OPENAI_API_KEY', 'UNRECOGNIZED_PROVIDER_SECRET', 'HTTPS_PROXY',
                 'PYTHONPATH', 'PYTHONHOME', 'NODE_OPTIONS', 'MDTERO_CONFIG_DIR', 'PYTHON_KEYRING_BACKEND']:
        monkeypatch.setenv(name, 'synthetic-private-build-input')
    monkeypatch.setenv('PATH', '/trusted/tools')
    environment = prepare.smoke_environment(tmp_path)
    assert environment['PATH'] == '/trusted/tools'
    assert 'synthetic-private-build-input' not in json.dumps(environment)
    assert environment['MDTERO_CONFIG_DIR'] == str(tmp_path)
    assert environment['MDTERO_API_URL'] == 'http://127.0.0.1:9'
    assert environment['PYTHON_KEYRING_BACKEND'] == 'keyring.backends.null.Keyring'


def startup(**overrides):
    return {'status': 'running', 'product': 'mdtero-connect', 'protocol': 1, 'host': '127.0.0.1',
            'port': 12345, 'url': 'http://127.0.0.1:12345', 'mode': 'library', **overrides}


@pytest.mark.parametrize('overrides', [
    {'url': 'https://127.0.0.1:12345'}, {'url': 'http://127.0.0.1.evil.example:12345'},
    {'url': 'http://localhost:12345'}, {'url': 'http://127.0.0.1:54321'},
    {'url': 'http://user:secret@127.0.0.1:12345'}, {'url': 'http://127.0.0.1:12345/library'},
    {'url': 'http://127.0.0.1:12345?secret=value'}, {'url': 'http://127.0.0.1:12345#fragment'},
    {'port': True}, {'port': 0}, {'protocol': 2}, {'mode': 'full'}, {'status': 'error'},
])
def test_smoke_never_follows_an_untrusted_child_url(overrides):
    with pytest.raises(ValueError):
        prepare.validated_smoke_url(startup(**overrides), 'basic')


@pytest.fixture
def fake_bridge(tmp_path):
    """A real disposable HTTP/process fixture exercises smoke supervision itself."""
    script = tmp_path / 'fake_bridge.py'
    script.write_text('''import json, os, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        if self.path == '/':
            body = b"<title>Mdtero Connect</title><meta content=\\\"connect-src 'self'\\\">"
        else:
            full = '--full' in sys.argv
            payload = {'authenticated': bool(os.environ.get('MDTERO_API_KEY')),
                       'mode': 'full' if full else 'library', 'csrf': 'synthetic-csrf',
                       'agent': {'enabled': full, 'providers': [{'configured': bool(os.environ.get('OPENAI_API_KEY'))}],
                                 'dependencies': {'available': full, 'sdk_version': '1.3.0'}}}
            body = json.dumps(payload).encode()
        self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
port = server.server_port
print(json.dumps({'status': 'running', 'product': 'mdtero-connect', 'protocol': 1,
                  'host': '127.0.0.1', 'port': port, 'url': 'http://127.0.0.1:' + str(port),
                  'mode': 'full' if '--full' in sys.argv else 'library'}), flush=True)
assert sys.stdin.readline().strip() == 'shutdown'
server.shutdown(); server.server_close()
''')
    return script


@pytest.mark.parametrize('edition', ['basic', 'full'])
def test_smoke_checks_real_local_page_anonymous_session_and_shutdown(fake_bridge, tmp_path, monkeypatch, edition):
    monkeypatch.setenv('MDTERO_API_KEY', 'synthetic-account-key')
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-provider-key')
    result = prepare.smoke_bridge([sys.executable, str(fake_bridge)], tmp_path, edition, timeout=5)
    assert result == {'status': 'passed', 'packaged_ui': True, 'anonymous_session': True,
                      'parent_shutdown': True, 'pi_dependencies': edition == 'full'}


def test_smoke_child_failure_does_not_echo_its_private_output(tmp_path):
    script = tmp_path / 'bad_bridge.py'
    script.write_text("import sys\nprint('synthetic-sensitive-child-output', flush=True)\nsys.stdin.read()\n")
    with pytest.raises(RuntimeError) as caught:
        prepare.smoke_bridge([sys.executable, str(script)], tmp_path, 'basic', timeout=2)
    assert 'synthetic-sensitive-child-output' not in str(caught.value)


@pytest.mark.skipif(sys.platform == 'win32', reason='Windows child containment is exercised by the Job lifecycle tests')
def test_failed_unix_smoke_stops_bootloader_style_descendant_listener(tmp_path):
    import os
    import signal
    import socket
    import time

    marker = tmp_path / 'descendant.json'
    child = tmp_path / 'listener.py'
    child.write_text('''import json, os, socket, sys
from pathlib import Path
listener = socket.socket()
listener.bind(('127.0.0.1', 0)); listener.listen()
marker = Path(sys.argv[1]); temporary = marker.with_suffix('.tmp')
temporary.write_text(json.dumps({'port': listener.getsockname()[1], 'pid': os.getpid()})); temporary.replace(marker)
listener.accept()
''')
    parent = tmp_path / 'bootloader.py'
    parent.write_text(f'''import subprocess, sys, time
from pathlib import Path
subprocess.Popen([sys.executable, {str(child)!r}, {str(marker)!r}])
while not Path({str(marker)!r}).exists(): time.sleep(0.01)
print('invalid-startup-protocol', flush=True)
sys.stdin.read()
''')
    try:
        with pytest.raises(RuntimeError, match='smoke failed'):
            prepare.smoke_bridge([sys.executable, str(parent)], tmp_path, 'basic', timeout=5)
        descendant = json.loads(marker.read_text())
        deadline = time.monotonic() + 2
        while True:
            try:
                with socket.create_connection(('127.0.0.1', descendant['port']), timeout=0.1):
                    pass
            except OSError:
                break
            if time.monotonic() >= deadline:
                pytest.fail('Failed frozen smoke left its descendant listener alive')
            time.sleep(0.02)
    finally:
        if marker.exists():
            try:
                os.kill(json.loads(marker.read_text())['pid'], signal.SIGKILL)
            except ProcessLookupError:
                pass
