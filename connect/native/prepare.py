"""Build and smoke-test trusted native debug resources on the matching host.

This prepares local/CI artifacts only. It never publishes or contacts the Mdtero
backend, and its frozen-process smoke test cannot inherit account/provider keys.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import queue
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen

ROOT = Path(__file__).resolve().parents[2]
NATIVE = Path(__file__).resolve().parent
TAURI = NATIVE / 'src-tauri'
PYINSTALLER_VERSION = '6.19.0'
TARGETS = {
    'aarch64-apple-darwin': ('Darwin', 'arm64'),
    'x86_64-apple-darwin': ('Darwin', 'x86_64'),
    'x86_64-pc-windows-msvc': ('Windows', 'x86_64'),
    'aarch64-unknown-linux-gnu': ('Linux', 'arm64'),
    'x86_64-unknown-linux-gnu': ('Linux', 'x86_64'),
}
PI_SDK_VERSION = '1.3.0'
SMOKE_DEPENDENCY_REASONS = frozenset({
    'agent_node_missing', 'agent_node_unavailable', 'agent_node_version',
    'agent_runtime_missing', 'agent_sdk_missing', 'agent_dependency_version_mismatch',
    'agent_dependencies_missing',
})
SMOKE_PROBE_STAGES = frozenset({'sdk_import', 'catalog'})
SMOKE_PROBE_CODES = frozenset({
    'ENOENT', 'ERR_MODULE_NOT_FOUND', 'ERR_DLOPEN_FAILED', 'MODULE_NOT_FOUND',
    'EPERM', 'EACCES', 'dependency_error',
})


def run(args: list[str], *, cwd: Path = ROOT) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def host_arch() -> str:
    machine = platform.machine().lower()
    return {'aarch64': 'arm64', 'amd64': 'x86_64', 'x64': 'x86_64'}.get(machine, machine)


def validate_host(target: str) -> None:
    if target not in TARGETS or TARGETS[target] != (platform.system(), host_arch()):
        raise ValueError('Native debug resources must be built on the matching target OS and architecture.')


def parse_node_version(value: str) -> str:
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)\s*', value)
    if not match or tuple(map(int, match.groups())) < (22, 19, 0):
        raise ValueError('A stable Node 22.19+ runtime is required.')
    return '.'.join(match.groups())


def npm_command(node: Path) -> list[str]:
    """Avoid executing a .cmd file, or interpolating a Windows path in a shell."""
    npm = shutil.which('npm.cmd' if platform.system() == 'Windows' else 'npm')
    if not npm:
        raise ValueError('npm is required to prepare the pinned Pi runtime.')
    if platform.system() == 'Windows':
        cli = Path(npm).parent / 'node_modules' / 'npm' / 'bin' / 'npm-cli.js'
        if not cli.is_file():
            raise ValueError('The npm JavaScript entry point is missing from the Node installation.')
        return [str(node), str(cli)]
    return [npm]


def bundle_node_license(node: Path, version: str, destination: Path) -> None:
    """Ship Node's complete third-party notices alongside the copied binary.

    Official Node distributions include LICENSE. Package-manager installations
    may store it under share/doc instead; the fixed official version is the
    fallback source, never a caller-provided URL.
    """
    version = parse_node_version(version)
    candidates = [node.parent / 'LICENSE', node.parent.parent / 'LICENSE',
                  node.parent.parent / 'share' / 'doc' / 'nodejs' / 'LICENSE',
                  Path('/usr/share/doc/nodejs/LICENSE')]
    data = next((path.read_bytes() for path in candidates if path.is_file()), None)
    if data is None:
        request = Request(f'https://raw.githubusercontent.com/nodejs/node/v{version}/LICENSE',
                          headers={'User-Agent': 'mdtero-connect-debug-builder'})
        with urlopen(request, timeout=30) as response:
            data = response.read(4 * 1024 * 1024 + 1)
    if not data or len(data) > 4 * 1024 * 1024 or b'Node.js' not in data or b'Permission is hereby granted' not in data:
        raise ValueError('The complete Node license notices could not be verified for bundling.')
    destination.write_bytes(data)


def smoke_environment(config_dir: Path) -> dict[str, str]:
    # An allow-list also excludes unknown provider keys and shell startup hooks.
    allowed = ('PATH', 'SystemRoot', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT',
               'TMP', 'TEMP', 'TMPDIR', 'LANG', 'LC_ALL', 'TZ')
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env.update({'MDTERO_CONFIG_DIR': str(config_dir), 'MDTERO_API_URL': 'http://127.0.0.1:9',
                'MDTERO_SITE_URL': 'http://127.0.0.1:9',
                # Smoke builds must not read or prompt for the builder's keychain.
                'PYTHON_KEYRING_BACKEND': 'keyring.backends.null.Keyring',
                'XDG_CONFIG_HOME': str(config_dir), 'XDG_DATA_HOME': str(config_dir / 'data')})
    return env


def validated_smoke_url(summary: object, edition: str) -> str:
    if not isinstance(summary, dict) or summary.get('protocol') != 1 or summary.get('status') != 'running' or summary.get('product') != 'mdtero-connect':
        raise ValueError('Frozen bridge did not return its expected startup protocol.')
    port = summary.get('port')
    expected_mode = 'full' if edition == 'full' else 'library'
    if type(port) is not int or not 0 < port < 65536 or summary.get('host') != '127.0.0.1' or summary.get('mode') != expected_mode:
        raise ValueError('Frozen bridge did not start in its expected loopback mode.')
    url = summary.get('url')
    parsed = urlparse(url) if isinstance(url, str) else None
    if not parsed or parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.port != port or parsed.path not in ('', '/') or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Frozen bridge returned an unsafe startup URL.')
    return f'http://127.0.0.1:{port}'


def dependency_smoke_phase(dependencies: object) -> str:
    """Expose fixed diagnostic enums and integer exits, never child payloads."""
    phase = 'anonymous session and dependencies'
    if not isinstance(dependencies, dict):
        return phase
    facts = []
    for field, allowed in (('reason_code', SMOKE_DEPENDENCY_REASONS),
                           ('probe_stage', SMOKE_PROBE_STAGES), ('probe_code', SMOKE_PROBE_CODES)):
        value = dependencies.get(field)
        if isinstance(value, str) and value in allowed:
            facts.append(field + '=' + value)
    for field in ('probe_exit_code', 'node_probe_exit_code', 'sdk_probe_exit_code'):
        value = dependencies.get(field)
        if type(value) is int:
            facts.append(field + '=' + str(value))
    return phase + (' (' + ', '.join(facts) + ')' if facts else '')


class SmokeJob:
    """Own a kill-on-close Windows Job before the onefile bootloader starts.

    The frozen Python child joins this named Job before starting any listener.
    Owning the outer process too covers failed startup/bootloader cleanup. On
    other operating systems this helper is intentionally inert.
    """

    def __init__(self) -> None:
        self.name: str | None = None
        self.handle = None
        self.api = None
        if sys.platform != 'win32':
            return
        import ctypes
        from ctypes import wintypes

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in (
                'ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

        class BasicLimits(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong),
                        ('PerJobUserTimeLimit', ctypes.c_longlong),
                        ('LimitFlags', wintypes.DWORD),
                        ('MinimumWorkingSetSize', ctypes.c_size_t),
                        ('MaximumWorkingSetSize', ctypes.c_size_t),
                        ('ActiveProcessLimit', wintypes.DWORD),
                        ('Affinity', ctypes.c_size_t),
                        ('PriorityClass', wintypes.DWORD),
                        ('SchedulingClass', wintypes.DWORD)]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', BasicLimits), ('IoInfo', IoCounters),
                        ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                        ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        api.CreateJobObjectW.restype = wintypes.HANDLE
        api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        api.SetInformationJobObject.restype = wintypes.BOOL
        api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        api.AssignProcessToJobObject.restype = wintypes.BOOL
        api.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        api.TerminateJobObject.restype = wintypes.BOOL
        api.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
        api.QueryInformationJobObject.restype = wintypes.BOOL
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.CloseHandle.restype = wintypes.BOOL
        self.name = 'Local\\MdteroConnect-Smoke-' + uuid.uuid4().hex
        handle = api.CreateJobObjectW(None, self.name)
        if not handle:
            raise RuntimeError('Could not create the supervised Windows smoke Job.')
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not api.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            api.CloseHandle(handle)
            raise RuntimeError('Could not configure the supervised Windows smoke Job.')
        self.api, self.handle = api, handle

    def assign(self, process: subprocess.Popen) -> None:
        if self.handle is not None and not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise RuntimeError('Could not assign the frozen process to the Windows smoke Job.')

    def close(self) -> None:
        if self.handle is not None:
            handle = self.handle
            try:
                if not self.api.TerminateJobObject(handle, 1):
                    raise RuntimeError('Could not terminate the supervised Windows smoke Job.')
                deadline = time.monotonic() + 10
                while self._active_processes(handle):
                    if time.monotonic() >= deadline:
                        raise RuntimeError('The supervised Windows smoke Job did not stop within its cleanup limit.')
                    time.sleep(0.05)
            finally:
                self.api.CloseHandle(handle)
                self.handle = None

    def _active_processes(self, handle) -> int:
        import ctypes

        class BasicAccounting(ctypes.Structure):
            _fields_ = [(name, ctypes.c_int64) for name in (
                'TotalUserTime', 'TotalKernelTime', 'ThisPeriodTotalUserTime', 'ThisPeriodTotalKernelTime')]
            _fields_ += [(name, ctypes.c_uint32) for name in (
                'TotalPageFaultCount', 'TotalProcesses', 'ActiveProcesses', 'TotalTerminatedProcesses')]

        accounting = BasicAccounting()
        if not self.api.QueryInformationJobObject(handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None):
            raise RuntimeError('Could not verify Windows smoke Job process cleanup.')
        return int(accounting.ActiveProcesses)

    def __enter__(self) -> 'SmokeJob':
        return self

    def __exit__(self, *_args) -> None:
        self.close()


def smoke_bridge(command: list[str], runtime: Path, edition: str, *, timeout: float = 60) -> dict:
    """Check the actual frozen executable, packaged UI, dependencies and shutdown.

    Only safe success facts are returned; child stdout/stderr or session data are
    never printed. No login, document API, model request, or credential check runs.
    """
    process = None
    completed = False
    job = SmokeJob()
    temporary = None
    phase = 'temporary directory'
    try:
        temporary = tempfile.mkdtemp(prefix='mdtero-native-smoke-')
        args = [*command, '--port', '0', '--runtime-dir', str(runtime.resolve())]
        if edition == 'full':
            args.append('--full')
        if job.name is not None:
            args.extend(['--job-name', job.name])
        phase = 'process launch'
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                                   cwd=temporary, env=smoke_environment(Path(temporary) / 'config'),
                                   start_new_session=os.name != 'nt')
        job.assign(process)
        phase = 'startup protocol'
        lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=lambda: lines.put(process.stdout.readline(8193)), daemon=True).start()
        line = lines.get(timeout=timeout)
        if len(line) > 8192:
            raise ValueError('Frozen bridge startup protocol exceeded its size limit.')
        url = validated_smoke_url(json.loads(line), edition)
        opener = build_opener(ProxyHandler({}))
        phase = 'packaged UI'
        with opener.open(url + '/', timeout=timeout) as response:
            page = response.read(2 * 1024 * 1024 + 1)
        if len(page) > 2 * 1024 * 1024 or b'Mdtero Connect' not in page or b"connect-src 'self'" not in page:
            raise ValueError('Frozen bridge did not serve its packaged Connect UI.')
        phase = 'anonymous session and dependencies'
        with opener.open(url + '/connect/v1/session', timeout=timeout) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('Frozen session exceeded its size limit.')
        session = json.loads(raw)
        if not isinstance(session, dict):
            raise ValueError('Frozen session did not return an object.')
        if session.get('authenticated') is not False or session.get('mode') != ('full' if edition == 'full' else 'library') or not isinstance(session.get('csrf'), str) or not session['csrf']:
            raise ValueError('Frozen session did not preserve the isolated anonymous mode.')
        agent = session.get('agent') or {}
        if not isinstance(agent, dict):
            raise ValueError('Frozen session did not return a valid agent status.')
        if agent.get('enabled') is not (edition == 'full'):
            raise ValueError('Frozen session did not expose the expected agent mode.')
        if edition == 'full':
            dependencies = agent.get('dependencies') or {}
            phase = dependency_smoke_phase(dependencies)
            if not isinstance(dependencies, dict):
                raise ValueError('Frozen session did not return valid dependency status.')
            providers = agent.get('providers', [])
            if not isinstance(providers, list) or any(not isinstance(provider, dict) for provider in providers):
                raise ValueError('Frozen session did not return valid provider status.')
            if dependencies.get('available') is not True or dependencies.get('sdk_version') != PI_SDK_VERSION or any(provider.get('configured') for provider in providers):
                raise ValueError('The frozen full runtime dependency or credential isolation check failed.')
        phase = 'parent shutdown'
        process.stdin.write('shutdown\n')
        process.stdin.flush()
        process.stdin.close()
        if process.wait(timeout=10) != 0:
            raise ValueError('Frozen bridge did not shut down cleanly.')
        phase = 'listener release'
        # A successful process exit must also release its loopback listener.
        try:
            with socket.create_connection(('127.0.0.1', urlparse(url).port), timeout=2):
                pass
        except OSError:
            pass
        else:
            raise ValueError('Frozen bridge left a listener after shutdown.')
        completed = True
        return {'status': 'passed', 'packaged_ui': True, 'anonymous_session': True,
                'parent_shutdown': True, 'pi_dependencies': edition == 'full'}
    except (OSError, ValueError, queue.Empty, subprocess.SubprocessError):
        # Do not echo child output, HTTP bodies, environment or credential paths.
        raise RuntimeError(f'Frozen bridge smoke failed during {phase}; inspect the local bundle and supervised startup protocol.') from None
    finally:
        # Keep the owning Job handle until all descendants have actually exited.
        # Closing a kill-on-close Job alone only requests asynchronous cleanup.
        try:
            job.close()
        finally:
            if process is not None:
                try:
                    if not completed and os.name != 'nt':
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    if process.poll() is None:
                        try:
                            process.kill()
                        except ProcessLookupError:
                            pass
                    # Reap even when poll already observed an exit.
                    process.wait(timeout=10)
                except (OSError, subprocess.SubprocessError):
                    raise RuntimeError('Frozen bridge smoke cleanup could not reap its parent process.') from None
                finally:
                    for pipe in (process.stdin, process.stdout):
                        if pipe is not None and not pipe.closed:
                            pipe.close()
        # If containment or reaping failed, leave the isolated directory alone:
        # rmtree must not race descendants that may still hold it as their cwd.
        if temporary is not None:
            try:
                shutil.rmtree(temporary)
            except OSError:
                raise RuntimeError('Frozen bridge smoke cleanup could not release its temporary directory.') from None


def prepare(target: str, edition: str) -> dict:
    validate_host(target)
    if edition not in ('basic', 'full'):
        raise ValueError('Choose the basic or full native debug edition.')
    if importlib.metadata.version('pyinstaller') != PYINSTALLER_VERSION:
        raise ValueError(f'Use PyInstaller {PYINSTALLER_VERSION} for this debug build.')
    # Full debug clients ship a supported OS keyring, not a silent session-only fallback.
    importlib.metadata.version('keyring')
    exe = '.exe' if platform.system() == 'Windows' else ''
    runtime = TAURI / 'resources' / 'runtime'
    build = NATIVE / '.build' / target
    binaries = TAURI / 'binaries'
    for path in (runtime, build):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
    binaries.mkdir(parents=True, exist_ok=True)
    # Build the existing public bridge; no private backend or site is vendored.
    data_arg = str(ROOT / 'connect' / 'app') + os.pathsep + 'mdtero/connect/static'
    run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
         '--name', 'mdtero-connect-bridge', '--distpath', str(build / 'dist'),
         '--workpath', str(build / 'work'), '--specpath', str(build),
         '--paths', str(ROOT / 'src'), '--add-data', data_arg,
         '--collect-submodules', 'keyring.backends',
         '--copy-metadata', 'mdtero', '--copy-metadata', 'keyring',
         str(ROOT / 'src' / 'mdtero' / 'connect' / 'native_entry.py')])
    sidecar = binaries / f'mdtero-connect-bridge-{target}{exe}'
    shutil.copy2(build / 'dist' / ('mdtero-connect-bridge' + exe), sidecar)
    files = {str(sidecar.relative_to(TAURI)): digest(sidecar)}
    node_version = None
    if edition == 'full':
        found_node = shutil.which('node')
        if not found_node:
            raise ValueError('Node 22.19+ is required to prepare the full debug runtime.')
        node = Path(found_node).resolve()
        node_version = parse_node_version(subprocess.check_output([str(node), '--version'], text=True, timeout=10))
        agent_src = ROOT / 'connect' / 'agent'
        agent_dest = runtime / 'agent'
        agent_dest.mkdir()
        for name in ('worker.mjs', 'package.json', 'package-lock.json', 'README.md', 'THIRD_PARTY_NOTICES.md'):
            shutil.copy2(agent_src / name, agent_dest / name)
        # Lifecycle scripts are never executed when preparing bundled JS dependencies.
        run([*npm_command(node), 'ci', '--prefix', str(agent_dest), '--ignore-scripts', '--omit=dev'])
        (runtime / 'node').mkdir()
        shutil.copy2(node, runtime / 'node' / ('node' + exe))
        bundle_node_license(node, node_version, runtime / 'node' / 'LICENSE')
    # Reuse the existing Relay binary. The shell never installs a background service.
    relay_dest = runtime / 'relay' / ('mdtero-relay' + exe)
    relay_dest.parent.mkdir()
    run(['go', 'build', '-trimpath', '-o', str(relay_dest), './cmd/mdtero-relay'], cwd=ROOT / 'relay')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    smoke = smoke_bridge([str(sidecar)], runtime, edition)
    for path in sorted(runtime.rglob('*')):
        if path.is_file() and 'node_modules' not in path.parts:
            files[str(path.relative_to(TAURI))] = digest(path)
    manifest = {
        'protocol': 1, 'product': 'mdtero-connect-debug', 'target': target,
        'edition': edition, 'commit': commit, 'pyinstaller': PYINSTALLER_VERSION,
        'node_version': node_version, 'pi_sdk_version': PI_SDK_VERSION if edition == 'full' else None,
        'relay_included': True, 'relay_auto_started': False,
        'signed_release': False, 'human_acceptance': 'pending', 'smoke': smoke,
        'sha256_scope': 'Sidecar and direct runtime files; dependency trees are covered by final artifact SHA256SUMS.',
        'sha256': files,
    }
    (runtime / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, choices=sorted(TARGETS))
    parser.add_argument('--edition', choices=['basic', 'full'])
    args = parser.parse_args()
    edition = args.edition or ('basic' if 'linux' in args.target else 'full')
    result = prepare(args.target, edition)
    print(json.dumps({'status': 'prepared', 'target': args.target, 'edition': edition, 'commit': result['commit'], 'smoke': result['smoke']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
