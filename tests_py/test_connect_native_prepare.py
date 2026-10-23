"""Native build input checks and real supervised smoke logic, without a desktop claim."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

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
from socketserver import TCPServer
class LoopbackServer(ThreadingHTTPServer):
    def server_bind(self):
        TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        if self.path == '/':
            body = b"<title>mdtero</title><meta content=\\\"connect-src 'self'\\\">"
        else:
            full = '--full' in sys.argv
            payload = {'authenticated': bool(os.environ.get('MDTERO_API_KEY')),
                       'mode': 'full' if full else 'library', 'csrf': 'synthetic-csrf',
                       'agent': {'enabled': full, 'providers': [{'configured': bool(os.environ.get('OPENAI_API_KEY'))}],
                                 'dependencies': {'available': full, 'sdk_version': '1.3.0'}}}
            body = json.dumps(payload).encode()
        self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
server = LoopbackServer(('127.0.0.1', 0), Handler)
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


def test_windows_directory_cleanup_retries_a_released_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare.sys, 'platform', 'win32')
    remove = Mock(side_effect=[PermissionError('synthetic-private-error'), None])
    monkeypatch.setattr(prepare.shutil, 'rmtree', remove)
    monkeypatch.setattr(prepare.time, 'sleep', lambda _: None)
    prepare.remove_smoke_directory(str(tmp_path), 'anonymous session and dependencies')
    assert remove.call_count == 2


def test_standalone_agent_probe_uses_no_ambient_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv('MDTERO_API_KEY', 'synthetic-private-account')
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-private-provider')
    def execute(command, **kwargs):
        assert command[-1] == '--check'
        assert 'MDTERO_API_KEY' not in kwargs['env'] and 'OPENAI_API_KEY' not in kwargs['env']
        assert Path(kwargs['cwd']).is_dir()
        return subprocess.CompletedProcess(command, 0, '{"available":true,"sdk_version":"1.3.0"}', '')
    monkeypatch.setattr(prepare.subprocess, 'run', execute)
    assert prepare.probe_bundled_agent(tmp_path) == {'available': True, 'sdk_version': '1.3.0'}


def test_standalone_agent_probe_never_exposes_dependency_error_bodies(tmp_path, monkeypatch):
    payload = {'probe_stage': 'sdk_import', 'probe_code': 'ERR_DLOPEN_FAILED',
               'error': {'message': 'synthetic-private-provider-response'}}
    monkeypatch.setattr(prepare.subprocess, 'run', lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, json.dumps(payload), 'synthetic-private-stderr'))
    with pytest.raises(RuntimeError) as caught:
        prepare.probe_bundled_agent(tmp_path)
    assert 'probe_code=ERR_DLOPEN_FAILED' in str(caught.value)
    assert 'synthetic-private' not in str(caught.value)


@pytest.mark.parametrize('platform_name', ['linux', 'win32'])
def test_directory_cleanup_preserves_safe_failure_phase(tmp_path, monkeypatch, platform_name):
    monkeypatch.setattr(prepare.sys, 'platform', platform_name)
    remove = Mock(side_effect=PermissionError('synthetic-private-error'))
    monkeypatch.setattr(prepare.shutil, 'rmtree', remove)
    with pytest.raises(RuntimeError) as caught:
        prepare.remove_smoke_directory(str(tmp_path), 'anonymous session and dependencies', timeout=0)
    assert 'anonymous session and dependencies' in str(caught.value)
    assert 'synthetic-private-error' not in str(caught.value)
    remove.assert_called_once()


def test_smoke_child_failure_does_not_echo_its_private_output(tmp_path):
    script = tmp_path / 'bad_bridge.py'
    script.write_text("import sys\nprint('synthetic-sensitive-child-output', flush=True)\nsys.stdin.read()\n")
    with pytest.raises(RuntimeError) as caught:
        prepare.smoke_bridge([sys.executable, str(script)], tmp_path, 'basic', timeout=2)
    assert 'synthetic-sensitive-child-output' not in str(caught.value)


@pytest.mark.parametrize('dependencies,expected', [
    ({'available': False, 'reason_code': 'agent_sdk_missing', 'probe_exit_code': -1073741515,
      'probe_stage': 'sdk_import', 'probe_code': 'ERR_DLOPEN_FAILED',
      'node_probe_exit_code': 0, 'sdk_probe_exit_code': 1,
      'stdout': 'synthetic-sensitive-probe-output', 'error': 'synthetic-sensitive-probe-output'},
     ['reason_code=agent_sdk_missing', 'probe_exit_code=-1073741515', 'probe_stage=sdk_import',
      'probe_code=ERR_DLOPEN_FAILED', 'node_probe_exit_code=0', 'sdk_probe_exit_code=1']),
    ({'available': False, 'reason_code': 'synthetic-sensitive-probe-output',
      'probe_stage': 'synthetic-sensitive-probe-output', 'probe_code': 'synthetic-sensitive-probe-output',
      'probe_exit_code': True, 'node_probe_exit_code': 'synthetic-sensitive-probe-output'}, []),
])
def test_failed_dependency_smoke_only_exposes_allowed_diagnostics(fake_bridge, tmp_path, dependencies, expected):
    source = fake_bridge.read_text()
    original = "'dependencies': {'available': full, 'sdk_version': '1.3.0'}"
    assert original in source
    fake_bridge.write_text(source.replace(original, "'dependencies': " + repr(dependencies)))
    with pytest.raises(RuntimeError) as caught:
        prepare.smoke_bridge([sys.executable, str(fake_bridge)], tmp_path, 'full', timeout=5)
    message = str(caught.value)
    assert 'anonymous session and dependencies' in message
    assert 'synthetic-sensitive-probe-output' not in message
    for fact in expected:
        assert fact in message
    if not expected:
        assert 'reason_code=' not in message and 'probe_' not in message


def test_failed_smoke_reaps_an_already_exited_parent_and_closes_its_pipes(tmp_path, monkeypatch):
    process = SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO('invalid-protocol\n'),
                              pid=123, poll=Mock(return_value=0), wait=Mock(return_value=0), kill=Mock())
    monkeypatch.setattr(prepare.subprocess, 'Popen', lambda *args, **kwargs: process)
    job = SimpleNamespace(name=None, assign=Mock(), close=Mock())
    monkeypatch.setattr(prepare, 'SmokeJob', lambda: job)
    if hasattr(prepare.os, 'killpg'):
        monkeypatch.setattr(prepare.os, 'killpg', lambda *_args: None)
    with pytest.raises(RuntimeError, match='startup protocol'):
        prepare.smoke_bridge(['synthetic-bridge'], tmp_path, 'basic')
    process.wait.assert_called_once_with(timeout=10)
    process.kill.assert_not_called()
    assert process.stdin.closed and process.stdout.closed


def test_uncertain_job_cleanup_never_removes_a_directory_that_descendants_may_hold(tmp_path, monkeypatch):
    temporary = tmp_path / 'smoke-cwd'
    temporary.mkdir()
    process = SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO('invalid-protocol\n'),
                              pid=123, poll=Mock(return_value=0), wait=Mock(return_value=0), kill=Mock())
    monkeypatch.setattr(prepare.subprocess, 'Popen', lambda *args, **kwargs: process)
    monkeypatch.setattr(prepare.tempfile, 'mkdtemp', lambda **_kwargs: str(temporary))
    job = SimpleNamespace(name=None, assign=Mock(), close=Mock(side_effect=RuntimeError('Job cleanup uncertain')))
    monkeypatch.setattr(prepare, 'SmokeJob', lambda: job)
    if hasattr(prepare.os, 'killpg'):
        monkeypatch.setattr(prepare.os, 'killpg', lambda *_args: None)
    remove = Mock()
    monkeypatch.setattr(prepare.shutil, 'rmtree', remove)
    with pytest.raises(RuntimeError, match='Job cleanup uncertain'):
        prepare.smoke_bridge(['synthetic-bridge'], tmp_path, 'basic')
    remove.assert_not_called()
    process.wait.assert_called_once_with(timeout=10)


class SyntheticJobApi:
    def __init__(self, counts=(2, 1, 0), failure=None):
        self.counts = iter(counts)
        self.failure = failure
        self.events = []

    def TerminateJobObject(self, handle, exit_code):
        self.events.append(('terminate', handle, exit_code))
        return self.failure != 'terminate'

    def QueryInformationJobObject(self, handle, kind, output, size, returned):
        assert kind == 1 and size == 48 and returned is None
        self.events.append(('query', handle))
        output._obj.ActiveProcesses = next(self.counts)
        return self.failure != 'query'

    def CloseHandle(self, handle):
        self.events.append(('close', handle))
        return True


def synthetic_job(api):
    job = prepare.SmokeJob.__new__(prepare.SmokeJob)
    job.name, job.handle, job.api = None, 123, api
    return job


def test_windows_job_requests_termination_and_waits_for_all_descendants_before_handle_close(monkeypatch):
    api = SyntheticJobApi()
    job = synthetic_job(api)
    monkeypatch.setattr(prepare.time, 'sleep', lambda _seconds: None)
    job.close()
    assert api.events == [('terminate', 123, 1), ('query', 123), ('query', 123), ('query', 123), ('close', 123)]
    assert job.handle is None
    job.close()
    assert len(api.events) == 5


def test_empty_job_still_uses_bounded_file_handle_release_cleanup(tmp_path, monkeypatch):
    directory = tmp_path / 'released-job-cwd'
    directory.mkdir()
    (directory / 'busy.txt').write_text('synthetic data')
    api = SyntheticJobApi(counts=(0,))
    job = synthetic_job(api)
    actual_remove = prepare.shutil.rmtree
    attempts = []

    def remove(path):
        # A directory must never be removed until containment is verified and
        # the owning Job handle has closed, even when filesystem retry is needed.
        assert job.handle is None and api.events[-1] == ('close', 123)
        attempts.append(path)
        if len(attempts) == 1:
            error = PermissionError(13, 'synthetic-private-sharing-violation')
            error.winerror = 32
            raise error
        actual_remove(path)

    monkeypatch.setattr(prepare.sys, 'platform', 'win32')
    monkeypatch.setattr(prepare.shutil, 'rmtree', remove)
    monkeypatch.setattr(prepare.time, 'sleep', lambda _seconds: None)
    job.close()
    prepare.remove_smoke_directory(str(directory), 'descendant handle release')
    assert len(attempts) == 2 and not directory.exists()


def test_persistent_post_job_file_lock_fails_within_the_same_cleanup_budget(tmp_path, monkeypatch):
    api = SyntheticJobApi(counts=(0,))
    job = synthetic_job(api)
    job.close()
    error = PermissionError(13, 'synthetic-private-sharing-violation')
    error.winerror = 32
    remove = Mock(side_effect=error)
    ticks = iter([0, 1, 6])
    monkeypatch.setattr(prepare.sys, 'platform', 'win32')
    monkeypatch.setattr(prepare.shutil, 'rmtree', remove)
    monkeypatch.setattr(prepare.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(prepare.time, 'sleep', lambda _seconds: None)
    with pytest.raises(RuntimeError, match='descendant handle release') as caught:
        prepare.remove_smoke_directory(str(tmp_path), 'descendant handle release')
    assert 'synthetic-private' not in str(caught.value)
    assert remove.call_count == 2 and tmp_path.exists()
    assert job.handle is None


@pytest.mark.parametrize('failure', ['terminate', 'query', 'timeout'])
def test_windows_job_cleanup_failures_are_bounded_and_always_close_the_handle(failure, monkeypatch):
    api = SyntheticJobApi(counts=(1, 1, 1), failure=failure)
    job = synthetic_job(api)
    ticks = iter([0, 0, 11])
    monkeypatch.setattr(prepare.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(prepare.time, 'sleep', lambda _seconds: None)
    with pytest.raises(RuntimeError, match='Windows smoke Job'):
        job.close()
    assert api.events[0] == ('terminate', 123, 1)
    assert api.events[-1] == ('close', 123)
    assert job.handle is None


@pytest.mark.skipif(sys.platform != 'win32', reason='Requires actual Windows Job termination and directory locking')
def test_windows_job_cleanup_releases_descendant_cwd_after_parent_already_exited(tmp_path):
    import time

    directory = tmp_path / 'held-cwd'
    directory.mkdir()
    marker = tmp_path / 'descendant-ready'
    child_code = "from pathlib import Path; import sys,time; held=open('busy.txt','w'); Path(sys.argv[1]).write_text('ready'); time.sleep(30)"
    parent_code = "import subprocess,sys; sys.stdin.readline(); subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)"
    job = prepare.SmokeJob()
    process = subprocess.Popen([sys.executable, '-c', parent_code, child_code, str(marker)], cwd=directory,
                               stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
    try:
        job.assign(process)
        process.stdin.write('go\n')
        process.stdin.flush()
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists(), 'The descendant did not reach its directory-locking checkpoint'
        assert process.wait(timeout=5) == 0
        job.close()
        prepare.remove_smoke_directory(str(directory), 'descendant handle release')
        assert not directory.exists()
    finally:
        job.close()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        process.stdin.close()


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
