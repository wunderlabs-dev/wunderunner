"""Main containerize workflow."""

from wunderunner.activities import docker, dockerfile, project, services
from wunderunner.exceptions import AnalyzeError
from wunderunner.workflows.base import (
    ContainerizeContext,
    ContainerizeResult,
    Failure,
    Learning,
    Phase,
    Success,
)
from wunderunner.workflows.run import Retry, phase

MAX_ATTEMPTS = 3


async def containerize(ctx: ContainerizeContext) -> ContainerizeResult:
    """Analyze project and generate Docker configuration with retry on failures."""
    try:
        analysis = await project.analyze(ctx.path, ctx.rebuild)
    except AnalyzeError as e:
        return Failure(learnings=[Learning(phase=Phase.ANALYZE, error=e)])

    learnings: list[Learning] = []

    for _ in range(MAX_ATTEMPTS):
        try:
            with phase(Phase.DOCKERFILE, learnings):
                dockerfile_content = await dockerfile.generate(analysis, learnings)

            with phase(Phase.SERVICES, learnings):
                await services.generate(analysis, dockerfile_content, learnings)

            with phase(Phase.BUILD, learnings):
                await docker.build(ctx.path, dockerfile_content)

            with phase(Phase.START, learnings):
                container_ids = await services.start(ctx.path)

            with phase(Phase.HEALTHCHECK, learnings):
                await services.healthcheck(container_ids)

            return Success()
        except Retry:
            continue

    return Failure(learnings=learnings)
