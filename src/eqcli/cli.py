import logging
import click
from pathlib import Path
from urllib.parse import urlparse
from eqcli.utils import read_proj_name
from eqcli.release import Release
from eqcli.project import Project

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG, format="%(levelname)s - %(module)s: %(message)s"
)


@click.group()
def cli():
    """Tools for creating equity reports in docker and writing release notes"""


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
    """Check for correct number of arguments supplied, optionally returning a flattened list

    Parameters
    ----------
    label : str
        Label to use for referencing args
    *args :
        One or more arguments to check
    single_val : bool
        If True, only 1 value is allowed across arguments
    flatten : bool, optional
        Flatten nested values into a single list, by default True

    Examples
    --------
    >>> check_nargs('a or b', a, b, single_val=False)
    """
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


def check_project_name(project_name, version_file) -> str:
    if project_name is None:
        if version_file is None:
            raise click.BadParameter(
                "must supply either `project_name` or `version_file` from which to extract a project name"
            )
        else:
            try:
                project_name = read_proj_name(version_file)
            except ValueError:
                logger.error("Cannot read project name from `version_file`")
    return project_name


# common options between commands
# from https://stackoverflow.com/a/50061489/5325862
def common_opts(func):
    func = click.option(
        "--dry-run",
        "-n",
        is_flag=True,
        help="Dry run: print expected operations but do nothing",
    )(func)
    func = click.option(
        "--version-file",
        "-V",
        help="Path to version file if tagging",
        # default=Path("pyproject.toml"),
        type=click.Path(exists=True, file_okay=True, dir_okay=False),
        show_default=True,
    )(func)
    func = click.option(
        "--version",
        "-v",
        help="Version if tagging; takes precedence over version-file",
        type=str,
    )(func)
    func = click.option(
        "--outdir",
        "-o",
        help="Path to output directory on the host machine",
        default=Path("to_distro"),
        show_default=True,
        type=click.Path(exists=False, file_okay=False, dir_okay=True),
    )(func)
    func = click.option("--project-name", "-p", help="Name of project", type=str)(func)
    return func


## APP ----
### BATCH WRITE ----
@click.command(short_help="Write batches of reports using docker")
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
    "--locations-file",
    "-f",
    # default="locations.txt",
    help="Path or URL to file of location names, one name per line. Can be given multiple times for multiple files.",
    type=str,
    multiple=True,
)
@click.option(
    "--clean",
    "-X",
    is_flag=True,
    help="Clean output directory before writing new files",
)
@click.option(
    "--clean-glob",
    "-G",
    help="Glob to use for deleting files",
    type=str,
    default=None,
    show_default=True,
)
@click.option("--print-logs", "-l", is_flag=True, help="Print logs from docker run")
@click.option("--print-quarto", "-q", is_flag=True, help="Print logs from quarto")
@click.option("--print-snakemake", "-s", is_flag=True, help="Print logs from snakemake")
@click.option(
    "--tag-rename", "-r", is_flag=True, help="Rename files based on version tag"
)
@common_opts
def batch_write(
    project_name,
    image,
    config_file,
    file_pattern,
    outdir,
    version,
    version_file,
    # locfile,
    # locurl,
    locations_file,
    clean,
    clean_glob,
    print_logs,
    print_quarto,
    print_snakemake,
    tag_rename,
    dry_run,
):
    """Write one or more batches of reports using snakemake running in a docker container. This creates a [`Project`][eqcli.project.Project] instance which, in turn, creates [`Batch`][eqcli.batch.Batch] objects for each option supplied to `--locfile` and/or `--locurl`. Then reports are generated for each batch inside the docker container and written out to `outdir`. The `--print-quarto` and `--print-snakemake` flags will provide some feedback as the containers run, but the `Batch` objects will try to parse logs from their containers and print running counts of successful and failed attempts to write reports.

    Todo
    ----
    - Reimplement progress bar for interactive use
    - Develop more robust log parsing
    """
    # if no name given, try to extract from project files
    project_name = check_project_name(project_name, version_file)
    logger.debug(f"project name: {project_name}")
    # combine all location files / urls
    location_lookups = check_nargs(
        # "locfile or locurl",
        # locfile, locurl,
        "locations-file",
        locations_file,
        single_val=False,
        flatten=True,
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
        rename=tag_rename,
        clean=clean,
        clean_glob=clean_glob,
        version=version,
        version_file=version_file,
        print_quarto=print_quarto,
        print_snakemake=print_snakemake,
    )
    for lookup in location_lookups:
        project.add_batch(lookup, append=True)

    if dry_run:
        project.print_overview()
        return None
    else:
        project.run_batches()
        if print_logs:
            click.secho(
                "\nRESULTS: ---------------------------", fg="yellow", bold=True
            )
            project.print_docker_logs()


## RELEASE ----
def release_opts(func):
    func = click.option("--quiet", "-q", is_flag=True, help="Quiet output")(func)
    func = click.option(
        "--xwalk-group-col", help="Column name to group by in the crosswalk", type=str
    )(func)
    func = click.option(
        "--xwalk-join-col", help="Column name to join IDs to crosswalk", type=str
    )(func)
    func = click.option(
        "--xwalk-path",
        help="Path to crosswalk file for grouping reports, such as between towns and COGs",
        type=click.Path(exists=True, file_okay=True, dir_okay=False),
    )(func)
    func = click.option(
        "--md-out",
        "-m",
        help="Path to write out notes to markdown",
        type=click.Path(exists=False, file_okay=True, dir_okay=False, writable=True),
        default=Path("release-notes.md"),
        show_default=True,
    )(func)
    func = click.option(
        "--id-regex",
        "-I",
        help="Regex pattern to extract IDs from filenames",
        default="(\\w+)_equity",
        type=str,
        show_default=True,
    )(func)
    return func


### RELEASE NOTES ----
@click.command(short_help="Write notes for a release")
@release_opts
@common_opts
def release_notes(
    project_name,
    outdir,
    version,
    version_file,
    id_regex,
    md_out,
    xwalk_path,
    xwalk_join_col,
    xwalk_group_col,
    quiet,
    dry_run,
):
    """Write notes as a markdown table to serve as release notes. The table will include each report's ID as parsed based on `id_regex`, the path to that file, and the last time modified. This can then be uploaded as release notes on GitHub, either as is or after amending the markdown file manually."""
    verbose = ~quiet
    project_name = check_project_name(project_name, version_file)
    release = Release(
        name=project_name,
        outdir=outdir,
        version=version,
        version_file=version_file,
        id_regex=id_regex,
        md_out=md_out,
        xwalk_path=xwalk_path,
        xwalk_join_on=xwalk_join_col,
        xwalk_group_col=xwalk_group_col,
    )
    if dry_run:
        print(release)
        return None
    else:
        release.write_notes_md(verbose=verbose)


### ZIP FILES ----
@click.command(short_help="Zip files for a release")
@release_opts
@common_opts
@click.option(
    "--glob",
    "-g",
    type=str,
    default="*.pdf",
    show_default=True,
    help="Glob to select files for zipping",
)
@click.option(
    "--zip-by-group", is_flag=True, help="Bundle files by grouping column to zip"
)
@click.option(
    "--zipdir",
    "-z",
    help="Path to directory for zipped files",
    default=Path("."),
    show_default=True,
    type=click.Path(exists=False, file_okay=False, dir_okay=True),
)
def zip_release(
    project_name,
    outdir,
    version,
    version_file,
    id_regex,
    md_out,
    xwalk_path,
    xwalk_join_col,
    xwalk_group_col,
    quiet,
    dry_run,
    glob,
    zip_by_group,
    zipdir,
):
    """Zip all the files from `outdir`, optionally matching by a glob string. If no glob is given, will match all PDF files in the output directory. Use a crosswalk and the `--zip-by-group` flag in order to bundle files into some group before zipping."""
    verbose = ~quiet
    project_name = check_project_name(project_name, version_file)
    release = Release(
        name=project_name,
        outdir=outdir,
        version=version,
        version_file=version_file,
        id_regex=id_regex,
        md_out=md_out,
        xwalk_path=xwalk_path,
        xwalk_join_on=xwalk_join_col,
        xwalk_group_col=xwalk_group_col,
        glob=glob,
    )
    if dry_run:
        print(release)
        # should print info about zips
        return None
    else:
        release.zip_files(zip_by_group=zip_by_group, zipdir=zipdir, verbose=verbose)


## BIND OUT ----

cli.add_command(batch_write)
cli.add_command(release_notes)
cli.add_command(zip_release)

if __name__ == "__main__":
    cli()
