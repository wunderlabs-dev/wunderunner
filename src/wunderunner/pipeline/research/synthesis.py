"""Synthesize ResearchResult into markdown artifact."""

from wunderunner.pipeline.models import ResearchResult


def synthesize_research(result: ResearchResult) -> str:
    """Convert ResearchResult to markdown document.

    This produces the research.md artifact that becomes input to PLAN phase.

    Args:
        result: Combined findings from all specialists.

    Returns:
        Markdown string for research.md.
    """
    sections = ["# Project Research\n"]

    # Runtime section
    sections.append("## Runtime\n")
    sections.append(f"- **Language:** {result.runtime.language}")
    if result.runtime.version:
        sections.append(f"- **Version:** {result.runtime.version}")
    if result.runtime.framework:
        sections.append(f"- **Framework:** {result.runtime.framework}")
    if result.runtime.entrypoint:
        sections.append(f"- **Entrypoint:** {result.runtime.entrypoint}")
    sections.append("")

    # Dependencies section
    sections.append("## Dependencies\n")
    sections.append(f"- **Package Manager:** {result.dependencies.package_manager}")
    if result.dependencies.package_manager_version:
        sections.append(f"- **Version:** {result.dependencies.package_manager_version}")
    if result.dependencies.build_command:
        sections.append(f"- **Build Command:** `{result.dependencies.build_command}`")
    if result.dependencies.start_command:
        sections.append(f"- **Start Command:** `{result.dependencies.start_command}`")

    if result.dependencies.native_deps:
        sections.append("\n### Native Dependencies\n")
        for dep in result.dependencies.native_deps:
            sections.append(f"- `{dep.name}`: {dep.reason}")
    sections.append("")

    # Configuration section
    sections.append("## Configuration\n")
    if result.config.config_files:
        sections.append("### Config Files\n")
        for f in result.config.config_files:
            sections.append(f"- `{f}`")
        sections.append("")

    if result.config.env_vars:
        sections.append("### Environment Variables\n")
        sections.append("| Name | Required | Secret | Service | Default |")
        sections.append("|------|----------|--------|---------|---------|")
        for var in result.config.env_vars:
            req = "Yes" if var.required else "No"
            sec = "Yes" if var.secret else "No"
            service_name = var.service or "-"
            default = f"`{var.default}`" if var.default else "-"
            sections.append(
                f"| {var.name} | {req} | {sec} | {service_name} | {default} |"
            )
    else:
        sections.append("No environment variables detected.\n")
    sections.append("")

    # Services section
    sections.append("## Backing Services\n")
    if result.services.services:
        for svc in result.services.services:
            version = f" (v{svc.version})" if svc.version else ""
            env = f" → `{svc.env_var}`" if svc.env_var else ""
            sections.append(f"- **{svc.type}**{version}{env}")
    else:
        sections.append("No backing services detected.\n")

    return "\n".join(sections)
