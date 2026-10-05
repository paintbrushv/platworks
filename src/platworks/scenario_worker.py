"""Isolated scenario process; only structured stdin/stdout, no network clients."""

import logging
import sys

from platworks.library import canonical
from platworks.local_review.common import decode
from platworks.scenarios import MAX_INPUT, MAX_OUTPUT, calculate, refusal


def main():
    logging.disable(sys.maxsize)

    def audit(event, args):
        if event in {
            "socket.connect",
            "socket.connect_ex",
            "socket.getaddrinfo",
            "socket.bind",
            "socket.sendto",
        }:
            raise PermissionError("Scenario network access is disabled")

    sys.addaudithook(audit)
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            result = refusal("INPUT_LIMIT")
        else:
            request = decode(raw)
            result = calculate(request["tool"], request["arguments"])
        output = canonical(result)
        if len(output) > MAX_OUTPUT:
            output = canonical(refusal("OUTPUT_LIMIT"))
    except Exception:
        output = canonical(refusal("INVALID_INPUT"))
    sys.stdout.buffer.write(output)


if __name__ == "__main__":
    main()
