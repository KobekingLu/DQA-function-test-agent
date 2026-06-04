#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import posixpath
import shlex
from datetime import datetime
from pathlib import Path
from typing import Any

import paramiko

REMOTE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run DQA live-check scripts on a remote Linux DUT over SSH."
    )
    parser.add_argument(
        "--config",
        default="config/target_system.local.json",
        help="Path to DUT SSH config JSON.",
    )
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Run only the read-only evidence collector.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run quick-check preflight only. Do not execute active checks.",
    )
    parser.add_argument(
        "--install-missing",
        action="store_true",
        help="Allow the remote quick check to install missing packages after confirmation.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm remote package installation without an interactive prompt.",
    )
    parser.add_argument(
        "--memory-seconds",
        type=int,
        default=0,
        help="Optional memory stress duration for remote quick check.",
    )
    parser.add_argument(
        "--storage-dir",
        default="",
        help="Optional remote directory for file-based storage smoke test.",
    )
    parser.add_argument(
        "--storage-mb",
        type=int,
        default=512,
        help="Storage smoke test size in MiB.",
    )
    parser.add_argument(
        "--network-server",
        default="",
        help="Optional iperf3 server used by the remote quick check.",
    )
    parser.add_argument(
        "--network-seconds",
        type=int,
        default=20,
        help="iperf3 duration for the remote quick check.",
    )
    parser.add_argument(
        "--local-output-dir",
        default="output/remote_runs",
        help="Base local output directory for downloaded DUT artifacts.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if args.install_missing and not args.yes:
        if not confirm_remote_install(args, config):
            print("Remote package installation was not confirmed. Aborting.")
            return 2

    label = sanitize_label(config.get("name") or config.get("host") or "dut")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    local_run_dir = Path(args.local_output_dir) / f"{label}_{timestamp}"
    local_run_dir.mkdir(parents=True, exist_ok=True)

    remote_base = config.get("remote_base_dir", "/tmp/dqa_live_checks").rstrip("/")
    remote_run_dir = f"{remote_base}/{label}_{timestamp}"

    local_script_dir = Path(__file__).resolve().parent
    local_collect = local_script_dir / "dqa_function_collect.py"
    local_quick = local_script_dir / "dqa_function_quick_check.py"

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        hostname=config["host"],
        port=int(config.get("port", 22)),
        username=config["username"],
        password=config["password"],
        timeout=15,
        look_for_keys=False,
        allow_agent=False,
    )

    sftp = ssh.open_sftp()
    try:
        exec_remote(ssh, f"mkdir -p {shlex.quote(remote_run_dir)}")
        sftp.put(str(local_collect), posixpath.join(remote_run_dir, "dqa_function_collect.py"))
        sftp.put(str(local_quick), posixpath.join(remote_run_dir, "dqa_function_quick_check.py"))

        remote_python = config.get("remote_python", "python3")
        remote_collect_cmd = (
            f"cd {shlex.quote(remote_run_dir)} && "
            f"{shlex.quote(remote_python)} dqa_function_collect.py "
            f"--label {shlex.quote(label)} "
            f"--output-dir {shlex.quote('run_output')}"
        )
        for tool_name in config.get("assume_tools", []):
            remote_collect_cmd += f" --assume-tool {shlex.quote(str(tool_name))}"
        collect_result = exec_remote(ssh, remote_collect_cmd, timeout=300)
        (local_run_dir / "collect_stdout.txt").write_text(collect_result["stdout"], encoding="utf-8")
        (local_run_dir / "collect_stderr.txt").write_text(collect_result["stderr"], encoding="utf-8")

        quick_result: dict[str, Any] | None = None
        if not args.collect_only:
            parts = [f"{shlex.quote(remote_python)} dqa_function_quick_check.py"]
            parts.append(f"--label {shlex.quote(label)}")
            parts.append(f"--output-dir {shlex.quote('run_output')}")
            if args.preflight_only:
                parts.append("--preflight-only")
            if args.install_missing:
                parts.append("--install-missing")
                parts.append("--yes")
            if args.memory_seconds > 0:
                parts.append(f"--memory-seconds {int(args.memory_seconds)}")
            if args.storage_dir:
                parts.append(f"--storage-dir {shlex.quote(args.storage_dir)}")
                parts.append(f"--storage-mb {int(args.storage_mb)}")
            if args.network_server:
                parts.append(f"--network-server {shlex.quote(args.network_server)}")
                parts.append(f"--network-seconds {int(args.network_seconds)}")
            topology = config.get("network_topology", {})
            for pair in topology.get("loopback_pairs", []):
                if len(pair) == 2:
                    parts.append(
                        f"--loopback-pair {shlex.quote(str(pair[0]))} {shlex.quote(str(pair[1]))}"
                    )
            for iface in topology.get("external_interfaces", []):
                parts.append(f"--external-interface {shlex.quote(str(iface))}")
            remote_quick_cmd = (
                f"cd {shlex.quote(remote_run_dir)} && " + " ".join(parts)
            )
            quick_result = exec_remote(ssh, remote_quick_cmd, timeout=max(300, args.memory_seconds + 180))
            (local_run_dir / "quick_stdout.txt").write_text(quick_result["stdout"], encoding="utf-8")
            (local_run_dir / "quick_stderr.txt").write_text(quick_result["stderr"], encoding="utf-8")

        remote_output_dir = posixpath.join(remote_run_dir, "run_output")
        if remote_exists(sftp, remote_output_dir):
            download_tree(
                sftp,
                remote_output_dir,
                local_run_dir / "downloaded",
            )

        summary = {
            "config_path": str(config_path),
            "target_host": config["host"],
            "target_name": config.get("name", ""),
            "remote_run_dir": remote_run_dir,
            "local_run_dir": str(local_run_dir),
            "collect_returncode": collect_result["returncode"],
            "quick_returncode": None if quick_result is None else quick_result["returncode"],
        }
        (local_run_dir / "remote_run_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Remote run completed. Artifacts saved to {local_run_dir}")
        return 0
    finally:
        sftp.close()
        ssh.close()


def confirm_remote_install(args: argparse.Namespace, config: dict[str, Any]) -> bool:
    packages = potential_install_packages(args, config)
    package_text = ", ".join(packages) if packages else "requested active-check packages"
    host = config.get("host", "unknown-host")

    print()
    print(f"Remote package installation requested for DUT {host}.")
    print(f"Potential packages: {package_text}")
    print("This requires the DUT to have network or package-mirror access.")
    print("It also requires root or passwordless sudo permission on the DUT.")
    print("Current automatic install support is intended for Ubuntu/Debian-like systems with apt-get.")
    try:
        answer = input("Install missing packages on the DUT if preflight detects gaps? Type Y to continue: ")
    except EOFError:
        return False
    return answer.strip().upper() == "Y"


def potential_install_packages(args: argparse.Namespace, config: dict[str, Any]) -> list[str]:
    packages: set[str] = set()
    topology = config.get("network_topology", {})

    if args.memory_seconds > 0:
        packages.add("stress-ng")
    if args.network_server or topology.get("loopback_pairs"):
        packages.add("iperf3")
    if topology.get("loopback_pairs") or topology.get("external_interfaces"):
        packages.add("ethtool")

    return sorted(packages)


def exec_remote(ssh: paramiko.SSHClient, command: str, timeout: int = 120) -> dict[str, Any]:
    shell_body = (
        f"export PATH={shlex.quote(REMOTE_PATH)}:$PATH; "
        "source /etc/profile >/dev/null 2>&1 || true; "
        "source ~/.bashrc >/dev/null 2>&1 || true; "
        f"{command}"
    )
    wrapped = f"bash -lc {shlex.quote(shell_body)}"
    stdin, stdout, stderr = ssh.exec_command(wrapped, timeout=timeout)
    out_text = stdout.read().decode("utf-8", errors="replace")
    err_text = stderr.read().decode("utf-8", errors="replace")
    returncode = stdout.channel.recv_exit_status()
    return {
        "command": wrapped,
        "stdout": out_text,
        "stderr": err_text,
        "returncode": returncode,
    }


def download_tree(sftp: paramiko.SFTPClient, remote_dir: str, local_dir: Path) -> None:
    local_dir.mkdir(parents=True, exist_ok=True)
    for entry in sftp.listdir_attr(remote_dir):
        remote_path = posixpath.join(remote_dir, entry.filename)
        local_path = local_dir / entry.filename
        if is_dir(entry.st_mode):
            download_tree(sftp, remote_path, local_path)
        else:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            sftp.get(remote_path, str(local_path))


def is_dir(mode: int) -> bool:
    return (mode & 0o170000) == 0o040000


def remote_exists(sftp: paramiko.SFTPClient, remote_path: str) -> bool:
    try:
        sftp.stat(remote_path)
        return True
    except OSError:
        return False


def sanitize_label(label: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in label.strip())
    return cleaned or "dut"


if __name__ == "__main__":
    raise SystemExit(main())
