#!/usr/bin/env python3
"""Worker-only local proxy/PostgreSQL/stub stack; no live route or cloud call."""
import argparse
import importlib.util
import json
import ipaddress
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
NAME = "portfolio-agent-local-postgres"
NETWORK = "portfolio-agent-local"
DOCKER_COMMAND = ["sudo", "docker"]
GATEWAY = "http://127.0.0.1:4001"
TENANTS = {"fixture-a": "11111111-1111-4111-8111-111111111111",
           "fixture-b": "22222222-2222-4222-8222-222222222222"}
POSTGRES_IMAGE = "postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652"


def write(path, value):
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")
    path.chmod(0o600)


def progress(state, code):
    (state / "progress.json").write_text(json.dumps({"stage": code}) + "\n")
    (state / "progress.json").chmod(0o600)


def command(args, log, *, env=None, input_data=None):
    with log.open("ab") as stream:
        result = subprocess.run(args, input=input_data, stdout=stream, stderr=stream,
                                env=env, timeout=240)
    log.chmod(0o600)
    if result.returncode:
        raise ValueError("local_stack:command_failed")


def http(path, *, key=None, data=None, timeout=10):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    request = urllib.request.Request(GATEWAY + path,
        data=None if data is None else json.dumps(data).encode(), headers=headers)
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
            body = response.read(1048577)
            if len(body) > 1048576:
                raise ValueError
            return response.status, json.loads(body)
    except urllib.error.HTTPError as error:
        # No response body, URL, header or exception message leaves this helper.
        return error.code, None


def spawn(args, state, name, environment):
    # Seal the creating supervisor's recipe, before libraries mutate their
    # environment or choose temporary Prisma paths. Recovery never bootstraps.
    write(state / (name+'-launch.json'), {'argv':args,'environment':environment,'cwd':str(ROOT)})
    log = (state / (name + ".log")).open("ab")
    process = subprocess.Popen(args, stdout=log, stderr=log, env=environment,
                               start_new_session=True, cwd=ROOT)
    log.close()
    start = Path(f"/proc/{process.pid}/stat").read_text().split()[21]
    return {"pid": process.pid, "start_ticks": start, "name": name}


def stop_process(record):
    path = Path(f"/proc/{record['pid']}")
    if not path.exists():
        return
    fields = path.joinpath("stat").read_text().split()
    if fields[21] != record["start_ticks"]:
        raise ValueError("local_stack:process_changed")
    if fields[2] == "Z":
        # An exited child has no command line and cannot be signalled safely.
        try:
            os.waitpid(record['pid'], os.WNOHANG)
        except ChildProcessError:
            pass
        return
    argv = path.joinpath("cmdline").read_bytes().split(b"\0")
    if not any(str(ROOT).encode() in item for item in argv):
        raise ValueError("local_stack:process_not_owned")
    if os.getpgid(record['pid']) != record['pid']:
        raise ValueError("local_stack:process_group_changed")
    os.killpg(record["pid"], signal.SIGTERM)
    until = time.monotonic() + 10
    while time.monotonic() < until:
        try:
            os.waitpid(record['pid'], os.WNOHANG)
        except ChildProcessError:
            pass
        if not path.exists() or path.joinpath('stat').read_text().split()[2] == 'Z':
            return
        time.sleep(.1)
    raise ValueError("local_stack:process_stop_timeout")


def require_free_ports(ports):
    for port in ports:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(('127.0.0.1', port))
            except OSError:
                raise ValueError('local_stack:port_in_use:' + str(port)) from None


def require_running(records):
    for record in records:
        path = Path('/proc') / str(record['pid']) / 'stat'
        if not path.exists():
            raise ValueError('local_stack:service_exited')
        fields = path.read_text().split()
        if fields[2] == 'Z' or fields[21] != record['start_ticks']:
            raise ValueError('local_stack:service_exited')


def require_listener(record, port):
    require_running([record])
    inodes = {row.split()[9] for row in Path('/proc/net/tcp').read_text().splitlines()[1:]
              if row.split()[1] == '0100007F:' + format(port, '04X') and row.split()[3] == '0A'}
    owned = set()
    for fd in (Path('/proc') / str(record['pid']) / 'fd').iterdir():
        try:
            target = os.readlink(fd)
        except FileNotFoundError:
            continue
        if target.startswith('socket:['):
            owned.add(target[8:-1])
    if not inodes or not inodes.issubset(owned):
        raise ValueError('local_stack:listener_not_owned')


def up(state, python, postgres_image, *, qualified_nonroot=False, gateway_port=4001, stub_port=8767):
    global GATEWAY
    if (type(gateway_port) is not int or type(stub_port) is not int
            or not all(1024 <= p <= 65535 for p in (gateway_port, stub_port))
            or gateway_port == stub_port or 8765 in (gateway_port, stub_port)):
        raise ValueError('local_stack:invalid_ports')
    GATEWAY = 'http://127.0.0.1:' + str(gateway_port)
    require_free_ports((gateway_port, stub_port))
    if state.exists():
        raise ValueError("local_stack:new_private_state_required")
    state.mkdir(mode=0o700, parents=False)
    operator = {"admin_key": "sk-" + secrets.token_hex(24),
                "salt_key": secrets.token_hex(32), "postgres_password": secrets.token_hex(24),
                "gateway_password": secrets.token_hex(24), "app_password": secrets.token_hex(24),
                "stub_key": secrets.token_hex(24), "run_id": secrets.token_hex(16)}
    write(state / "operator.json", operator)
    progress(state, "NETWORK_DATABASE_START")
    pg_env = state / "postgres.env"
    pg_env.write_text("POSTGRES_PASSWORD=" + operator["postgres_password"] + "\n"
                      + ("PGDATA=/var/lib/postgresql/data/pgdata\n" if qualified_nonroot else ""))
    pg_env.chmod(0o600)
    command(DOCKER_COMMAND + [ "network", "create", "--internal", "--label", "portfolio.task=local-agents",
             "--label", "portfolio.run=" + operator["run_id"], NETWORK], state / "docker.log")
    command(DOCKER_COMMAND + [ "run", "-d", "--name", NAME,
             "--label", "portfolio.task=local-agents", "--label", "portfolio.run=" + operator["run_id"], "--network", NETWORK,
             "--cpus", "1", "--memory", "512m",
             "--pids-limit", "128", "--env-file", str(pg_env),
             "--tmpfs", ("/var/lib/postgresql/data:rw,size=256m,uid=70,gid=70,mode=0700" if qualified_nonroot else "/var/lib/postgresql/data:rw,size=256m"),
             *(["--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--tmpfs", "/var/run/postgresql:rw,size=8m,uid=70,gid=70,mode=0700"] if qualified_nonroot else []), postgres_image], state / "docker.log")
    import psycopg
    from psycopg import sql
    inspected = json.loads(subprocess.check_output(DOCKER_COMMAND + [ "inspect", NAME]))[0]
    if inspected["Config"]["Labels"].get("portfolio.run") != operator["run_id"]:
        raise ValueError("local_stack:resource_not_owned")
    database_host = inspected["NetworkSettings"]["Networks"][NETWORK]["IPAddress"]
    if not ipaddress.ip_address(database_host).is_private:
        raise ValueError("local_stack:private_database_required")
    database_address = "@" + database_host + ":5432/"
    admin_url = "postgresql://postgres:" + operator["postgres_password"] + database_address + "postgres"
    ready = False
    for _ in range(60):
        try:
            with psycopg.connect(admin_url, connect_timeout=1, autocommit=True) as db:
                for role, password in (("portfolio_gateway", operator["gateway_password"]),
                                       ("portfolio_app", operator["app_password"])):
                    db.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}")
                               .format(sql.Identifier(role), sql.Literal(password)))
                db.execute("CREATE DATABASE litellm OWNER portfolio_gateway")
                db.execute("CREATE DATABASE portfolio_demo")
                db.execute("REVOKE CONNECT ON DATABASE litellm FROM PUBLIC")
                db.execute("GRANT CONNECT ON DATABASE litellm TO portfolio_gateway")
                db.execute("REVOKE CONNECT ON DATABASE portfolio_demo FROM PUBLIC")
                db.execute("GRANT CONNECT ON DATABASE portfolio_demo TO portfolio_app")
            ready = True
            break
        except psycopg.OperationalError:
            time.sleep(0.25)
    if not ready:
        raise ValueError("local_stack:database_not_ready")
    progress(state, "TENANT_SCHEMA")
    tenant_admin_url = "postgresql://postgres:" + operator["postgres_password"] + database_address + "portfolio_demo"
    with psycopg.connect(tenant_admin_url, autocommit=True) as db:
        db.execute((ROOT / "deploy/local-agents/tenant.sql").read_text())
        fixtures = json.loads((ROOT / "demo/fixtures/expenses.json").read_text())
        for tenant, rows in fixtures["tenants"].items():
            for row in rows:
                db.execute("INSERT INTO portfolio_demo.expenses(tenant_id,period,category,amount_minor_units) VALUES(%s,%s,%s,%s)",
                           (TENANTS[tenant], row["period"], row["category"], row["amount_minor_units"]))
    environment = {"PATH": str(python.parent) + ":/usr/bin:/bin", "HOME": str(state),
                   "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
                   "LITELLM_LOCAL_MODEL_COST_MAP": "True", "LITELLM_TELEMETRY": "False",
                   "DISABLE_ADMIN_UI": "True"}
    # Prepared operator toolchain lives outside application state/credentials.
    # Explicit cache paths prevent runtime downloads into ambient HOME.
    tooling = python.parent.parent.parent
    environment.update({"PRISMA_HOME_DIR": str(tooling),
                        "PRISMA_NODEENV_CACHE_DIR": str(tooling / "nodeenv"),
                        "LD_LIBRARY_PATH": str(tooling / "native-tools/extracted/usr/lib/x86_64-linux-gnu")})
    gateway_config = state / 'gateway-config.yaml'
    gateway_config.write_text((ROOT/'deploy/local-agents/litellm-stub.yaml').read_text()
                             .replace('127.0.0.1:8767', '127.0.0.1:' + str(stub_port)))
    gateway_config.chmod(0o600)
    (state/'service-control.lock').touch(mode=0o600, exist_ok=False)
    processes = []
    write(state / "processes.json", processes)
    try:
        progress(state, "PRISMA_MIGRATION")
        processes.append(spawn([str(python), str(ROOT / "scripts/local-agent-upstream.py"),
                                "--state", str(state), '--port', str(stub_port)], state, "stub", environment))
        (state / "processes.json").write_text(json.dumps(processes) + "\n")
        gateway_environment = environment | {
            "LITELLM_MASTER_KEY": operator["admin_key"], "LITELLM_SALT_KEY": operator["salt_key"],
            "LOCAL_STUB_UPSTREAM_KEY": operator["stub_key"],
            "DATABASE_URL": "postgresql://portfolio_gateway:" + operator["gateway_password"]
                            + database_address + "litellm",
            "DISABLE_SCHEMA_UPDATE": "true"}
        if qualified_nonroot:
            # Reuse the already hash-qualified executable. Prisma's temporary
            # extraction path is unsuitable for restoring a stopped service.
            verifier_spec=importlib.util.spec_from_file_location('generated_inputs',ROOT/'scripts/verify-agent-composition-build-inputs.py')
            verifier=importlib.util.module_from_spec(verifier_spec);verifier_spec.loader.exec_module(verifier);verifier.verify()
            engine=ROOT/'.qualified/query-engine'
            if not os.access(engine,os.X_OK):raise ValueError('local_stack:qualified_engine_not_executable')
            gateway_environment['PRISMA_QUERY_ENGINE_BINARY']=str(engine)
        # Schema provisioning is a separate operator-only step, before server boot.
        if qualified_nonroot:
            # Exact SQL generated offline from the locked official Prisma schema.
            # Provision as the bounded gateway DB owner before proxy startup.
            with psycopg.connect(gateway_environment["DATABASE_URL"], autocommit=True) as db:
                db.execute((ROOT / "deploy/local-agents/litellm-schema.sql").read_text())
        else:
            command([str(python), "-m", "prisma", "db", "push", "--skip-generate", "--schema",
                     str(python.parent.parent / "lib/python3.12/site-packages/litellm/proxy/schema.prisma")],
                    state / "migration.log", env=gateway_environment)
        progress(state, "GATEWAY_START")
        processes.append(spawn([str(python), str(ROOT / "scripts/local-agent-proxy.py"),
            "--config", str(gateway_config),
            "--host", "127.0.0.1", "--port", str(gateway_port)], state, "gateway", gateway_environment))
        (state / "processes.json").write_text(json.dumps(processes) + "\n")
        readiness_deadline = time.monotonic() + 60
        ready = False
        while time.monotonic() < readiness_deadline:
            require_running(processes)
            try:
                if http("/health/readiness", key=operator["admin_key"], timeout=2)[0] == 200:
                    require_running(processes)
                    require_listener(processes[0], stub_port)
                    require_listener(processes[1], gateway_port)
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(0.25)
        if not ready:
            raise ValueError("local_stack:proxy_not_ready")
        keys = {}
        progress(state, "SCOPED_CLIENT_ISSUANCE")
        for user in ("alpha", "beta"):
            keys[user] = {}
            for profile in ("infrastructure", "financial"):
                require_running(processes)
                status, response = http("/key/generate", key=operator["admin_key"], data={
                    "models": ["secure-financial-chat"], "duration": "1h", "max_budget": 0.5,
                    "allowed_routes": ["/chat/completions"], "max_parallel_requests": 1,
                    "rpm_limit": 32, "tpm_limit": 32768,
                    "metadata": {"agent_profile": profile, "fixture_subject": user,
                                 "fixture_only": True}})
                if status != 200 or type(response.get("key")) is not str:
                    progress(state, "SCOPED_CLIENT_HTTP_" + str(status))
                    raise ValueError("local_stack:key_issuance_failed")
                keys[user][profile] = response["key"]
        from cryptography.hazmat.primitives.asymmetric import rsa
        progress(state, "FIXTURE_IDENTITY_CONFIGURATION")
        from cryptography.hazmat.primitives import serialization
        from google.auth import crypt, jwt
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                   serialization.NoEncryption())
        cert = private.public_key().public_bytes(serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        now = int(time.time())
        tenant_reference_key = secrets.token_hex(32)
        for user, tenant in (("alpha", "fixture-a"), ("beta", "fixture-b")):
            subject = "local-fixture-" + user
            token = jwt.encode(crypt.RSASigner.from_string(pem, key_id="local-fixture"), {
                "iss": "https://fixture-issuer.invalid", "aud": "portfolio-local-composition",
                "sub": subject, "iat": now, "exp": now + 900, "tenant": tenant}).decode()
            write(state / ("application-" + user + ".json"), {
                "mode": "local_stub", "live_enabled": False,
                "gateway_url": GATEWAY, "client_keys": keys[user], "expires_at": now + 900,
                "certificates": {"local-fixture": cert}, "subject": subject,
                "tenant": tenant, "token": token, "tenant_reference_key": tenant_reference_key,
                "tenant_directory": TENANTS,
                "tenant_database_url": "postgresql://portfolio_app:" + operator["app_password"]
                                       + database_address + "portfolio_demo"})
            for kind in ("audit-tools", "audit-turns"):
                (state / (kind + "-" + user)).mkdir(mode=0o700)
        write(state / "local-subjects.json", {"postgres_image": postgres_image,
              "source_commit": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).decode().strip(),
              "external_model_calls": 0, "live_enabled": False})
        processes.append(spawn([str(python), str(ROOT / "scripts/local-agent-database-guard.py"),
                                "--state", str(state)], state, "database-guard", environment))
        (state / "processes.json").write_text(json.dumps(processes) + "\n")
        progress(state, "READY")
        print(json.dumps({"local_stack": "ready", "gateway": GATEWAY,
                          "upstream": "stub", "external_model_calls": 0, "live_enabled": False}))
    except Exception as error:
        import traceback
        trace = traceback.extract_tb(error.__traceback__)
        # Public code coordinates only; no driver messages, URLs or secrets.
        write(state / "sanitized-startup-failure.json", {
            "exception_type": type(error).__name__,
            "own_frames": [{"function": f.name, "line": f.lineno} for f in trace
                           if f.filename == str(Path(__file__).resolve())]})
        for process in reversed(processes):
            try:
                stop_process(process)
            except Exception:
                # The outer owner must finish cleanup; preserve the startup cause.
                pass
        raise


def down(state):
    failures = []
    records = json.loads((state / "processes.json").read_text()) if (state / "processes.json").exists() else []
    for record in reversed(records):
        try:
            stop_process(record)
        except Exception:
            failures.append('process')
    # Docker labels identify only resources owned by this launcher.
    operator = json.loads((state / "operator.json").read_text())
    expected_run = operator.get("run_id")
    probe = subprocess.run(DOCKER_COMMAND + [ "inspect", "--format",
                            '{{index .Config.Labels "portfolio.run"}}', NAME], capture_output=True)
    if probe.returncode == 0:
        if not expected_run or probe.stdout.strip().decode() != expected_run:
            raise ValueError("local_stack:resource_not_owned")
        command(DOCKER_COMMAND + [ "rm", "-f", NAME], state / "docker-cleanup.log")
    probe = subprocess.run(DOCKER_COMMAND + [ "network", "inspect", "--format",
                            '{{index .Labels "portfolio.run"}}', NETWORK], capture_output=True)
    if probe.returncode == 0:
        if not expected_run or probe.stdout.strip().decode() != expected_run:
            raise ValueError("local_stack:resource_not_owned")
        command(DOCKER_COMMAND + [ "network", "rm", NETWORK], state / "docker-cleanup.log")
    if failures:
        raise ValueError('local_stack:process_cleanup_incomplete')
    print(json.dumps({"local_stack": "stopped", "database_tmpfs_destroyed": True,
                      "private_state_retained": True}))


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("up", "down"))
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--postgres-image")
    args = parser.parse_args()
    if args.operation == "up":
        if args.postgres_image != POSTGRES_IMAGE:
            raise ValueError("local_stack:immutable_database_image_required")
        new_state = not args.state.exists()
        try:
            up(args.state, args.python, args.postgres_image)
        except Exception as error:
            if new_state and args.state.exists() and not (args.state / "sanitized-startup-failure.json").exists():
                import traceback
                trace = traceback.extract_tb(error.__traceback__)
                write(args.state / "sanitized-startup-failure.json", {
                    "exception_type": type(error).__name__,
                    "own_frames": [{"function": f.name, "line": f.lineno} for f in trace
                                   if f.filename == str(Path(__file__).resolve())]})
            if new_state and (args.state / "operator.json").exists():
                down(args.state)
            raise
    else:
        down(args.state)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("local_stack:blocked; inspect private operator evidence", file=sys.stderr)
        raise SystemExit(1) from None
