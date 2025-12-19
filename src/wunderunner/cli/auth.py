"""CLI commands for authentication."""

import asyncio
import webbrowser
from datetime import datetime

import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from wunderunner.auth.models import Provider
from wunderunner.auth.pkce import generate_pkce, generate_state
from wunderunner.auth.providers.anthropic import (
    AnthropicOAuth,
    build_auth_url,
    exchange_code_for_tokens,
)
from wunderunner.auth.storage import clear_tokens, load_store, save_tokens
from wunderunner.exceptions import OAuthCallbackError
from wunderunner.settings import get_settings

auth_app = typer.Typer(name="auth", help="Manage authentication.")
console = Console()


@auth_app.command()
def status() -> None:
    """Show authentication status for all providers."""
    asyncio.run(_status_async())


async def _status_async() -> None:
    """Async implementation of status command."""
    store = await load_store()
    settings = get_settings()

    table = Table(title="Authentication Status")
    table.add_column("Provider", style="cyan")
    table.add_column("Method", style="green")
    table.add_column("Status", style="yellow")

    # Anthropic
    anthropic_tokens = store.get_tokens(Provider.ANTHROPIC)
    if anthropic_tokens:
        if anthropic_tokens.is_expired():
            status_text = "Expired (run `wxr auth login`)"
        else:
            expires = datetime.fromtimestamp(anthropic_tokens.expires_at)
            status_text = f"Valid until {expires.strftime('%H:%M')}"
        table.add_row("Anthropic", "OAuth", status_text)
    elif settings.anthropic_api_key:
        table.add_row("Anthropic", "API Key (env)", "Configured")
    else:
        table.add_row("Anthropic", "-", "Not configured")

    # OpenAI
    if settings.openai_api_key:
        table.add_row("OpenAI", "API Key (env)", "Configured")
    else:
        table.add_row("OpenAI", "-", "Not configured")

    console.print(table)


@auth_app.command()
def login() -> None:
    """Authenticate with a provider."""
    console.print("\n[bold]Select provider:[/bold]")
    console.print("  [cyan]1[/cyan] Anthropic (OAuth - Claude Pro/Max subscription)")
    console.print("  [cyan]2[/cyan] Enter API key manually")

    choice = Prompt.ask("Choice", choices=["1", "2"], default="1")

    if choice == "1":
        asyncio.run(_login_anthropic_oauth())
    elif choice == "2":
        _login_api_key()


async def _login_anthropic_oauth() -> None:
    """Run Anthropic OAuth flow."""
    console.print("\n[dim]Starting OAuth flow...[/dim]")

    # Generate PKCE and state
    code_verifier, code_challenge = generate_pkce()
    state = generate_state()

    # Use Anthropic's hosted redirect (their client only allows this)
    redirect_uri = AnthropicOAuth.REDIRECT_URI

    # Build auth URL
    auth_url = build_auth_url(
        code_challenge=code_challenge,
        state=state,
        redirect_uri=redirect_uri,
    )

    console.print("\n[dim]Opening browser for authentication...[/dim]")
    console.print("[dim]If browser doesn't open, visit:[/dim]")
    console.print(f"[link={auth_url}]{auth_url[:80]}...[/link]\n")

    webbrowser.open(auth_url)

    # Anthropic's hosted redirect shows the code for user to copy
    console.print("[bold]After authenticating, copy the code and paste it here:[/bold]")
    code = Prompt.ask("Authorization code")

    if not code:
        console.print("[red]No code provided. Aborting.[/red]")
        return

    try:
        # Exchange code for tokens
        console.print("[dim]Exchanging code for tokens...[/dim]")
        tokens = await exchange_code_for_tokens(
            code=code.strip(),
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
        )

        # Save tokens
        await save_tokens(Provider.ANTHROPIC, tokens)
        console.print("\n[green bold]Successfully authenticated with Anthropic![/green bold]")

    except OAuthCallbackError as e:
        console.print(f"\n[red]Authentication failed: {e}[/red]")
    except Exception as e:
        console.print(f"\n[red]Error during authentication: {e}[/red]")


def _login_api_key() -> None:
    """Manual API key entry."""
    console.print("\n[bold]Select provider for API key:[/bold]")
    console.print("  [cyan]1[/cyan] Anthropic")
    console.print("  [cyan]2[/cyan] OpenAI")

    choice = Prompt.ask("Choice", choices=["1", "2"])

    if choice == "1":
        console.print("\nSet the ANTHROPIC_API_KEY environment variable:")
        console.print("  [dim]export ANTHROPIC_API_KEY='sk-ant-...'[/dim]")
    else:
        console.print("\nSet the OPENAI_API_KEY environment variable:")
        console.print("  [dim]export OPENAI_API_KEY='sk-...'[/dim]")


@auth_app.command()
def logout() -> None:
    """Remove stored authentication."""
    console.print("\n[bold]Select provider to logout:[/bold]")
    console.print("  [cyan]1[/cyan] Anthropic")
    console.print("  [cyan]2[/cyan] All providers")

    choice = Prompt.ask("Choice", choices=["1", "2"], default="1")

    if choice == "1":
        asyncio.run(clear_tokens(Provider.ANTHROPIC))
        console.print("[green]Logged out of Anthropic[/green]")
    else:
        asyncio.run(clear_tokens(Provider.ANTHROPIC))
        console.print("[green]Logged out of all providers[/green]")
