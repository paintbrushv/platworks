"""platworks CLI — thin click client over the catalog.

Rules:

- Thin client only: results come from ``platworks.catalog``, never
  re-implemented here (tests assert equality against the module).
- Exit codes are stable and documented: 0 success, 2 typed refusal.
- ``platworks-mcp`` console script and the ``mcp`` subcommand both run
  the stdio MCP server.
"""

import json

import click

from platworks import catalog


@click.group()
@click.version_option(package_name="platworks")
def main():
    """platworks — umbrella tooling for the plat CRE ecosystem."""


def _print_components(components):
    for c in components:
        click.echo(f"{c['name']}  [{c['category']}]")
        if c["public"]:
            click.echo(f"  {c['repo']}")
            click.echo(f"  {c['description']}")
        else:
            click.echo("  (private component — no public repository yet)")
        click.echo("")


@main.command(name="catalog")
@click.option("--category", default=None, help="Filter by category.")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
def catalog_list(category, as_json):
    """List ecosystem components (verified catalog)."""
    if category is not None and category not in catalog.CATEGORIES:
        click.echo(
            f"unknown category: {category}; valid categories: "
            + ", ".join(catalog.CATEGORIES),
            err=True,
        )
        raise SystemExit(2)
    components = catalog.list_components(category=category)
    if as_json:
        click.echo(json.dumps(components, indent=2))
        return
    _print_components(components)


@main.command()
@click.argument("name")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
def get(name, as_json):
    """Show one component by exact name."""
    try:
        component = catalog.get_component(name)
    except catalog.UnknownComponentError:
        click.echo(f"unknown component: {name}", err=True)
        raise SystemExit(2)
    if as_json:
        click.echo(json.dumps(component, indent=2))
        return
    _print_components([component])


@main.command()
def mcp():
    """Run the platworks MCP server over stdio."""
    from platworks import mcp_server

    mcp_server.main()


@main.command()
@click.argument("output_path", type=click.Path(), default="landing.html")
@click.option("--force", is_flag=True, help="Overwrite an existing file.")
def landing(output_path, force):
    """Render the standalone landing page to OUTPUT_PATH (default landing.html)."""
    from platworks import landing_page

    landing_page.render_page(output_path, overwrite=force)


@main.command()
@click.argument("output_dir", type=click.Path(), default="platworks-demo")
@click.option("--force", is_flag=True, help="Overwrite existing files.")
def demo(output_dir, force):
    """Write the synthetic demo fixtures to OUTPUT_DIR (default platworks-demo/)."""
    from platworks import demo

    demo.write_demo(output_dir, overwrite=force)


if __name__ == "__main__":
    main()