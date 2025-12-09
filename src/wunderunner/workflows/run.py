"""Phase execution utilities."""

from contextlib import contextmanager
from typing import Generator

from wunderunner.exceptions import WunderunnerError
from wunderunner.workflows.base import Learning, Phase


class Retry(Exception):
    """Raised to signal the workflow should retry from the beginning of the loop."""


@contextmanager
def phase(p: Phase, learnings: list[Learning]) -> Generator[None, None, None]:
    """Execute a phase, capturing failures as learnings.

    Usage:
        with phase(Phase.BUILD, learnings):
            await docker.build(path, dockerfile_content)

    Raises:
        Retry: If a WunderunnerError is caught, after appending to learnings.
    """
    try:
        yield
    except WunderunnerError as e:
        learnings.append(Learning(phase=p, error=e))
        raise Retry from e
