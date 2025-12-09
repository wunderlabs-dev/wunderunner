"""Main containerize workflow."""

from wunderunner.activities import docker, dockerfile, project, services
from wunderunner.settings import get_settings
from wunderunner.workflows.base import (
    ContainerizeContext,
    Failure,
    Learning,
    Phase,
    Success,
)
from wunderunner.workflows.run import Retry, phase


async def containerize(ctx: ContainerizeContext) -> Success:
    """Analyze project and generate Docker configuration with retry on failures."""
    settings = get_settings()
    learnings: list[Learning] = []

    with phase(Phase.ANALYZE, learnings):
        analysis = await project.analyze(ctx.path, ctx.rebuild)

    for _ in range(settings.max_attempts):
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

    raise Failure
