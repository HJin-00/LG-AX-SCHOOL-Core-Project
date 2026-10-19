"""Double-click entry point helper. Only standard-library modules are required."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser


class LaunchError(RuntimeError):
    pass


def find_app(root: Path) -> Path:
    matches = list(root.glob('*/app/run.py'))
    if len(matches) != 1:
        raise LaunchError('Extract the entire ZIP first; keep START_WINDOWS.cmd beside the project folder.')
    return matches[0].parent


def read_config(app: Path) -> Path:
    config = app / 'config/app.env'
    if not config.is_file():
        raise LaunchError('The shared config/app.env is missing. Use the ENV-included team ZIP. It is not replaced automatically.')
    text = config.read_text(encoding='utf-8-sig')
    values = {}
    for line in text.splitlines():
        key, sep, value = line.strip().partition('=')
        if sep and not key.startswith('#'):
            values[key.strip()] = value.strip().strip('\"\'')
    if values.get('CONSENT_BACKEND', 'mysql').lower() != 'mysql':
        raise LaunchError('This team package expects CONSENT_BACKEND=mysql. Check app.env; no DB setting was changed.')
    return config


def fingerprint(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(p.name.encode('utf-8'))
        h.update(p.read_bytes())
    return h.hexdigest()


def run(command: list[str], cwd: Path, label: str) -> None:
    print(label, flush=True)
    completed = subprocess.run(command, cwd=str(cwd), check=False)
    if completed.returncode:
        raise LaunchError(f'{label} failed (exit {completed.returncode}). Read the error above and run START_WINDOWS.cmd again.')


def available(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def ensure_port_free(port: int) -> None:
    if not available(port):
        raise LaunchError(f'Port {port} is already in use. Close the previously started project, then try again. No existing process was stopped.')


def wait_ready(url: str, process, timeout: float = 90, *, agent: bool = False) -> None:
    deadline = time.monotonic() + timeout
    # Loopback requests must not use the system HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise LaunchError('A server exited during startup. Check runtime/windows-launcher logs.')
        try:
            with opener.open(url, timeout=1) as response:
                if response.status == 200:
                    if agent and not json.load(response).get('agent_connected'):
                        raise LaunchError('API is running but the AI agent is not connected. Check app.env and api.log.')
                    return
        except (OSError, urllib.error.URLError, ValueError):
            pass
        time.sleep(.5)
    raise LaunchError('Startup timed out. Check network/MySQL settings and runtime/windows-launcher logs.')


def stop_process(process) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def setup(root: Path, app: Path) -> Path:
    if sys.version_info[:2] != (3, 12):
        raise LaunchError('Python 3.12 is required. Run INSTALL_WINDOWS.cmd first.')
    node = shutil.which('node')
    npm = shutil.which('npm.cmd')
    if not node or not npm:
        raise LaunchError('Node.js LTS was not found. Run INSTALL_WINDOWS.cmd, then reopen START_WINDOWS.cmd.')
    try:
        ver = tuple(int(v) for v in subprocess.check_output([node, '--version'], text=True).strip().lstrip('v').split('.'))
        if ver < (22, 12, 0):
            raise ValueError('old node')
    except (ValueError, subprocess.SubprocessError):
        raise LaunchError('Node.js 22.12+ is required. Install the current Node.js LTS release.')
    env = root / '.venv-win'
    python = env / 'Scripts/python.exe'
    if not python.is_file():
        if env.exists():
            raise LaunchError('.venv-win is incomplete. Move that folder elsewhere, then run START_WINDOWS.cmd again.')
        run([sys.executable, '-m', 'venv', str(env)], root, '[1/4] Creating a Windows Python environment')
    reqs = [app / 'requirements.txt', app / 'backend/ai/requirements-lock.txt',
            app / 'agent/requirements.txt', app / 'mcp/requirements.txt', app / 'requirements-windows-lock.txt']
    sig = fingerprint(reqs)
    marker = env / '.requirements-sha256'
    if not marker.is_file() or marker.read_text().strip() != sig:
        run([str(python), '-m', 'pip', 'install', '-r', str(app / 'requirements.txt'), '-c', str(app / 'requirements-windows-lock.txt')], root, '[2/4] Installing Python packages (first launch may take several minutes)')
        marker.write_text(sig)
    front = app / 'frontend'
    sig = fingerprint([front / 'package.json', front / 'package-lock.json'])
    marker = front / 'node_modules/.windows-launcher-sha256'
    if not marker.is_file() or marker.read_text().strip() != sig:
        run([npm, 'ci'], front, '[3/4] Installing frontend packages')
        marker.write_text(sig)
    # Build from current source so team edits are always reflected.
    run([npm, 'run', 'build'], front, '[4/4] Building the current frontend')
    return python


def serve(root: Path, app: Path, python: Path, config: Path) -> None:
    for port in (8000, 3001):
        ensure_port_free(port)
    logs = app / 'backend/ai/runtime/windows-launcher'
    logs.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(PYTHONUTF8='1', PYTHONUNBUFFERED='1', WATER_CONFIG_PATH=str(config),
               WEB_PORT='3001', FASTAPI_URL='http://127.0.0.1:8000')
    processes = []
    try:
        with (logs / 'api.log').open('w', encoding='utf-8') as api_log, (logs / 'web.log').open('w', encoding='utf-8') as web_log:
            api = subprocess.Popen([str(python), '-m', app.parent.name + '.app.run', 'api'], cwd=root, env=env, stdout=api_log, stderr=subprocess.STDOUT)
            processes.append(api)
            print('Starting FastAPI. Waiting for the AI agent...', flush=True)
            wait_ready('http://127.0.0.1:8000/health', api, agent=True)
            web = subprocess.Popen([shutil.which('node'), str(app / 'web/server.mjs')], cwd=root, env=env, stdout=web_log, stderr=subprocess.STDOUT)
            processes.append(web)
            wait_ready('http://127.0.0.1:3001/', web, timeout=20)
            webbrowser.open('http://127.0.0.1:3001')
            print('\nREADY: http://127.0.0.1:3001\nKeep this window open. Press Ctrl+C to stop both servers.\nLogs: ' + str(logs), flush=True)
            while all(p.poll() is None for p in processes):
                time.sleep(1)
            raise LaunchError('A server stopped. Check the API/web log files.')
    finally:
        for process in reversed(processes):
            stop_process(process)


def main() -> int:
    args = argparse.ArgumentParser()
    args.add_argument('--validate', action='store_true', help='Check package layout without installing/running servers')
    args.add_argument('--rag-index', action='store_true', help='Build public-document vectors after confirmation')
    opts = args.parse_args()
    root = Path(__file__).resolve().parent
    try:
        app = find_app(root)
        config = read_config(app)
        for rel in ('requirements.txt', 'frontend/package-lock.json', 'web/server.mjs'):
            if not (app / rel).is_file():
                raise LaunchError(f'Missing package file: {rel}. Extract the full ZIP again.')
        if opts.validate:
            print('Package layout and MySQL config type: OK (no secrets printed, no network calls)')
            return 0
        if os.name != 'nt':
            raise LaunchError('Use START_WINDOWS.cmd on Windows. The Mac launcher is separate.')
        python = setup(root, app)
        if opts.rag_index:
            print('This sends public knowledge documents to the configured OpenAI embedding API and may incur API usage. Private contracts are excluded.')
            if input('Build the public RAG index? Type YES: ').strip() != 'YES':
                print('Cancelled. No embedding request was sent.')
                return 0
            env = os.environ.copy()
            env['WATER_CONFIG_PATH'] = str(config)
            run_result = subprocess.run([str(python), '-m', app.parent.name + '.app.run', 'rag-index'], cwd=root, env=env)
            return run_result.returncode
        serve(root, app, python, config)
        return 0
    except KeyboardInterrupt:
        print('\nStopped. The servers started by this launcher were closed.')
        return 0
    except LaunchError as error:
        print('\nERROR: ' + str(error), flush=True)
        return 1
    except Exception as error:
        print('\nERROR: ' + type(error).__name__ + '. Check the launcher/server logs and the README.', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
