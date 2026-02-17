from pathlib import Path
import click
from urllib.parse import urlparse
from eqcli.project import Project
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


@click.group()
def cli():
    pass


## CLI UTILITIES ----
class URL(click.ParamType):
    """From https://github.com/pallets/click/blob/f67abc6fe7dd3d878879a4f004866bf5acefa9b4/examples/validation/validation.py#L12"""

    name = "url"

    def convert(self, value, param, ctx):
        if not isinstance(value, tuple):
            parsed = urlparse(value)
            if parsed.scheme not in ("http", "https"):
                self.fail(
                    f"invalid URL scheme ({parsed.scheme})",
                    param,
                    ctx,
                )
        return value


def check_nargs(label: str, *args, single_val: bool, flatten: bool = True):
    if flatten:
        valid = flatten_with_none(*args)
    else:
        valid = [a for a in args if a is not None]
    if single_val:
        if len(valid) != 1:
            raise click.BadParameter(
                f"Must supply exactly 1 value of {args}", param_hint=label
            )
        else:
            return valid[0]
    else:
        if len(valid) == 0:
            raise click.BadParameter(
                f"Must supply at least one value of {args}", param_hint=label
            )
        else:
            return valid


def flatten_with_none(*args):
    return [x for xs in args if xs is not None for x in xs]


## APP ----
### BATCH WRITE
@click.command()
@click.option("--project-name", "-p", help="Name of project", type=str)
@click.option(
    "--image",
    "-i",
    help="Name or URL of docker image",
    default="ghcr.io/ct-data-haven/regions:latest",
    show_default=True,
)
@click.option(
    "--config-file",
    "-c",
    help="Path to snakemake config yaml file",
    default=Path("config.yml"),
    show_default=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
)
@click.option(
    "--file-pattern",
    "-t",
    help="Template literal string to create filenames; can use values from config-file",
    default="{id}_equity_{doc_yr}.pdf",
    show_default=True,
    type=str,
)
@click.option(
    "--outdir",
    "-o",
    help="Path to output directory on the host machine",
    default=Path("to_distro"),
    show_default=True,
    type=click.Path(exists=False, file_okay=False, dir_okay=True),
)
@click.option(
    "--locfile",
    "-f",
    # default="locations.txt",
    help="Path to file of location names, one name per line",
    type=click.Path(exists=True, dir_okay=False),
    multiple=True,
)
@click.option(
    "--locurl",
    "-u",
    # default=None,
    help="URL to file of location names, one name per line",
    type=URL(),
    multiple=True,
)
@click.option(
    "--clean",
    "-X",
    is_flag=True,
    help="Clean output directory before writing new files",
)
@click.option("--print-logs", "-l", is_flag=True, help="Print logs from docker run")
@click.option("--print-quarto", "-q", is_flag=True, help="Print logs from quarto")
@click.option("--print-snakemake", "-s", is_flag=True, help="Print logs from snakemake")
@click.option(
    "--tag-rename", "-r", is_flag=True, help="Rename files based on version tag"
)
@click.option(
    "--version-file",
    "-v",
    help="Path to version file if tagging",
    default=Path("pyproject.toml"),
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    show_default=True,
)
@click.option(
    "--dry-run",
    "-n",
    is_flag=True,
    help="Dry run: print expected operations but do nothing",
)
def batch_write(
    project_name,
    image,
    config_file,
    file_pattern,
    outdir,
    locfile,
    locurl,
    clean,
    print_logs,
    print_quarto,
    print_snakemake,
    tag_rename,
    version_file,
    dry_run,
):
    """Write a batch set of reports using docker"""
    # combine all location files / urls
    location_lookups = check_nargs(
        "locfile or locurl", locfile, locurl, single_val=False, flatten=True
    )
    # location_lookups = locfile
    logger.debug(location_lookups)

    # create Project, use to create & deploy batches
    project = Project(
        name=project_name,
        image=image,
        config_file=config_file,
        file_pattern=file_pattern,
        outdir=outdir,
        version_file=version_file,
        print_quarto=print_quarto,
        print_snakemake=print_snakemake,
    )
    for lookup in location_lookups:
        project.add_batch(lookup, file_pattern)

    if dry_run:
        print(project)
        for batch in project.batches:
            print(batch)
        return None
    else:
        project.run_batches()
        if print_logs:
            click.secho(
                "\nRESULTS: ---------------------------", fg="yellow", bold=True
            )
            # refactor: should be Project methods
            for batch in project.batches:
                for log in batch.logs:
                    click.echo(log)


cli.add_command(batch_write)
if __name__ == "__main__":
    cli()
