"""Run the suite against disposable, password-authenticated PostgreSQL.

Requires the managed Docker daemon. No persistent DB or credentials are created.
The runner always removes only its own unique container and anonymous volumes.
"""
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import psycopg

IMAGE = "postgres:17-bookworm@sha256:839fbb5a4942a7758dd93e18b42ea5649807491a0545b5eeeb8f0b8bb11857a5"
DOCKER = ["docker", "--host=unix:///var/run/docker.sock"]


def main():
    root = Path(__file__).resolve().parents[1]
    environment = {k:v for k,v in os.environ.items() if k not in {
        'DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'}}
    environment['POSTGRES_PASSWORD'] = secrets.token_urlsafe(40)
    name = 'work4ce-tests-' + secrets.token_hex(6)
    started = False
    try:
        result = subprocess.run(DOCKER + ['run','-d','--name',name,
            '--label','work4ce.purpose=isolated-tests','--memory','512m','--cpus','2',
            '--tmpfs','/var/lib/postgresql/data:rw,size=256m',
            '-e','POSTGRES_PASSWORD','-e','POSTGRES_USER=work4ce','-e','POSTGRES_DB=work4ce_db',
            '-p','127.0.0.1::5432',IMAGE], env=environment, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError('Unable to start the isolated database container')
        started = True
        port_result = subprocess.run(DOCKER + ['inspect','--format',
            '{{json .NetworkSettings.Ports}}',name], env=environment,capture_output=True,text=True,check=True)
        port = json.loads(port_result.stdout)['5432/tcp'][0]['HostPort']
        connection = {'host':'127.0.0.1','port':port,'user':'work4ce','dbname':'work4ce_db',
                      'password':environment['POSTGRES_PASSWORD'],'connect_timeout':1}
        for attempt in range(80):
            try:
                with psycopg.connect(**connection) as db:
                    server = db.execute('SHOW server_version').fetchone()[0]
                break
            except psycopg.OperationalError:
                time.sleep(.1)
        else:
            raise RuntimeError('PostgreSQL readiness timed out')
        print(f'Running integration suite on PostgreSQL {server}', flush=True)
        # Only the test child receives the ephemeral DSN. Never print it.
        test_environment = dict(os.environ)
        test_environment['WORK4CE_TEST_POSTGRES_URL'] = (
            f"postgresql+psycopg://work4ce:{environment['POSTGRES_PASSWORD']}@127.0.0.1:{port}/work4ce_db")
        test_environment['PYTHONPATH'] = str(root/'src')
        return subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],
                              env=test_environment,cwd=root).returncode
    except Exception:
        print('PostgreSQL runner failed; check Docker availability and database readiness. Credentials are redacted.',file=sys.stderr)
        return 1
    finally:
        if started:
            cleanup = subprocess.run(DOCKER + ['rm','-f','-v',name],env=environment,capture_output=True)
            if cleanup.returncode:
                print(f'Cleanup failed for test container {name}; remove it after inspection.',file=sys.stderr)


if __name__ == '__main__':
    raise SystemExit(main())
