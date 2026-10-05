"""Test a locally built image with no external network and a read-only root."""

import argparse
import json
import subprocess
import uuid


def run(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def verify(image):
    name = "plat-mcp-check-" + uuid.uuid4().hex[:10]
    network = name + "-internal"
    run("network", "create", "--internal", network)
    container = None
    try:
        container = run(
            "run",
            "-d",
            "--name",
            name,
            "--network",
            network,
            "--read-only",
            "--user",
            "65532:65532",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=64",
            "--memory=1g",
            "--cpus=2",
            "--init",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,exec,size=256m,uid=65532,gid=65532,mode=0700",
            image,
        )
        # Probe the running service from inside the network-isolated container.
        report = json.loads(
            run(
                "exec",
                container,
                "python",
                "-I",
                "-B",
                "-m",
                "platworks.verify_integrations",
                "--analysis",
                "--endpoint",
                "http://127.0.0.1:8000",
            )
        )
        run(
            "exec",
            container,
            "python",
            "-I",
            "-c",
            "import socket,pathlib; "
            "assert not list(pathlib.Path('/tmp').glob('plat-scenario-*')); "
            "s=socket.socket(); s.settimeout(2); "
            "assert s.connect_ex(('1.1.1.1',443)) != 0",
        )
        assert run("logs", container) == "", "Container emitted application logs"
        run(
            "exec",
            container,
            "python",
            "-I",
            "-c",
            "import os; assert os.statvfs('/').f_flag & os.ST_RDONLY",
        )
        # Docker may report mount-point preparation in diff even with a read-only
        # root. The kernel mount flag checks the runtime property directly.
        root_diff = run("diff", container)
        build = json.loads(run("exec", container, "cat", "/opt/platworks-build.json"))
        return {
            "status": "passed",
            "image_id": run("image", "inspect", image, "--format", "{{.Id}}"),
            "read_only_root": True,
            "docker_diff": root_diff,
            "unprivileged_user": 65532,
            "tmpfs_limit_mib": 256,
            "external_network_blocked": True,
            "logs_empty": True,
            "probe": report,
            "build": build,
        }
    finally:
        if container:
            run("rm", "-f", container)
        run("network", "rm", network)


if __name__ == "__main__":
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.image)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in {"build", "probe"}}))
