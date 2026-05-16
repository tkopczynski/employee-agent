"""Config — the Sandbox image + resource/time limits are configuration.

ADR-0007 / Band-C Issue 04: the image tag and the CPU / memory / wall-clock
limits are read from configuration, never hardcoded — the same
everything-configurable, cost-bounded ethos as the recall/compaction caps.
Pure and Docker-free; this is the only Issue-04 behaviour provable without a
Docker daemon.
"""

from employee_agent.config import Config


def test_sandbox_image_and_resource_limits_default_and_are_overridable():
    c = Config()
    assert c.sandbox_image == "employee-agent-sandbox:1"
    assert c.sandbox_cpus == "1.0"
    assert c.sandbox_memory == "512m"
    # The wall-clock cap stays config-driven (unchanged from Issue 03).
    assert c.sandbox_command_timeout == 30

    c2 = Config(
        sandbox={
            "image": "custom-sandbox:9",
            "cpus": "2",
            "memory": "1g",
            "command_timeout": 5,
        }
    )
    assert c2.sandbox_image == "custom-sandbox:9"
    assert c2.sandbox_cpus == "2"
    assert c2.sandbox_memory == "1g"
    assert c2.sandbox_command_timeout == 5
