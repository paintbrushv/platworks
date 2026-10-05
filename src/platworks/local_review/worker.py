"""Fixed local subprocess entry; computes only the approved base/downside inputs."""

import copy
import sys

from .common import MAX_BODY, ReviewError, decode, encode, refuse
from .producers import ensure_identity


def calculate(request):
    from engine.engine import run_underwriting
    from engine.modules.scenarios import ScenarioPresets, run_scenarios

    ensure_identity(request["identity"])
    effective = []

    def run(inputs):
        # Validate BOTH cases. The engine's default scenario runner skips the
        # second validation; reviewed local execution must refuse invalid deltas.
        effective.append(copy.deepcopy(inputs))
        return run_underwriting(inputs)

    results = run_scenarios(
        request["inputs"],
        presets={"downside": ScenarioPresets(name="Downside", **request["downside"])},
        engine_runner=run,
    )
    results["effective_inputs"] = dict(zip(("base", "downside"), effective, strict=True))
    ensure_identity(request["identity"])
    return {"status": "calculated", "result": results, "identity": request["identity"]}


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            refuse("INPUT_LIMIT", "Request too large.")
        result = calculate(decode(raw))
        output = encode(result)
    except Exception as error:
        code = error.code if isinstance(error, ReviewError) else "ENGINE_VALIDATION"
        sys.stdout.buffer.write(encode({"status": "refused", "code": code}))
        raise SystemExit(2) from None
    sys.stdout.buffer.write(output)


if __name__ == "__main__":
    main()
