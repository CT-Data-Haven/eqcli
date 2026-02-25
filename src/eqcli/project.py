from eqcli.utils import check_version
import yaml
import click

from eqcli.batch import Batch
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class Project:
    """Object to hold overarching project attributes, including its Docker image, snakemake configs, version, and other options for how the container should be run. A `Project` will also create one or more `Batch` objects, representing different sets of files created as part of the project. For example, different batches might have their IDs come from different text files, and maintain their success tracking independently.

    Parameters
    ----------
    name : str | None
        Project name
    image : str
        Name or URL to docker image, already built
    config_file : Path | str
        Path to snakemake config file
    file_pattern : str
        String to be used with `format()` to create desired report filenames. Include `"{id}"` as a placeholder for report IDs such as location names, such as `"{id}_equity_{year}.pdf"`, where `year` is a keyed value in the config file.
    outdir : Path | str
        Directory for final generated reports
    rename : bool, optional
        Whether generated reports should be renamed with the version tag appended, by default False
    version : str | None, optional
        Text of version tag, e.g. "0.1.0". If None, must supply `version_file`. If both are supplied, this takes precedence.
    version_file : Path | str | None, optional
        File that can be parsed to get a version tag, presumably either pyproject.toml for Python or DESCRIPTION for R. If None, must supply `version` directly
    version_patt : str | None, optional
        Regex pattern to use to extract version if `version_file='DESCRIPTION'`. If None, one is used by default that should get a properly formatted version.
    clean : bool, optional
        Whether to remove all files from `outdir` before generating new ones, by default False
    clean_glob : str | None, optional
        If `clean=True`, the glob to use to designate what files to remove. If None, all files in `outdir` are removed
    print_quarto : bool, optional
        Whether to run Quarto in verbose mode, including its printout of each chunk rendered, by default False
    print_snakemake : bool, optional
        Whether to run snakemake in verbose mode, by default False
    repo : str | None, optional
        GitHub repo of the project (currently unused), by default None
    """

    def __init__(
        self,
        name: str | None,
        image: str,
        config_file: Path | str,
        file_pattern: str,
        outdir: Path | str,
        rename: bool = False,
        version: str | None = None,
        version_file: Path | str | None = None,
        version_patt: str | None = None,
        clean: bool = False,
        clean_glob: str | None = None,
        print_quarto: bool = False,
        print_snakemake: bool = False,
        repo: str | None = None,
    ):
        self.name = name
        self.repo = repo
        self.image = image
        # self.file_pattern = file_pattern
        self.outdir = Path(outdir)
        self.rename = rename
        self.config = self._read_config(config_file)
        self.file_pattern = self._file_patt_fill(file_pattern)
        self.version = check_version(version, version_file, version_patt)
        self.print_quarto = print_quarto
        self.print_snakemake = print_snakemake
        self.batches: list[Batch] = []

        # setup outdir
        self._setup_dir()
        if clean and clean_glob is not None:
            self._clean_dir(clean_glob)

    ## SETUP PROJECT ----
    def _setup_dir(self) -> None:
        """Give a directory permissions necessary for docker & GitHub Actions runner to have write access, creating the directory if needed"""
        if not self.outdir.exists():
            click.echo(f"Creating directory {self.outdir}")
            self.outdir.mkdir(parents=True, exist_ok=True)
        self.outdir.chmod(mode=0o777)
        return None

    def _clean_dir(self, glob: str) -> None:
        """Delete files in a directory based on a glob

        Parameters
        ----------
        glob : str
            Glob pattern to match files for deletion
        """
        files = list(self.outdir.glob(glob))
        if len(files) == 0:
            click.echo(f"No files in {self.outdir} to remove")
        else:
            click.echo(f"Removing {len(files)} files from {self.outdir}")
            for file in files:
                file.unlink()
        return None

    def _read_config(self, config_file: Path | str) -> dict:
        """Read a snakemake-syle yaml config file

        Parameters
        ----------
        config_file : Path | str
            Path to config file

        Returns
        -------
        dict
            A dict as represented in `config_file`, with a default value of "batch" set if no key `batch_dir` already exists
        """
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
        if "batch_dir" not in config or "batchdir" not in config:
            config["batch_dir"] = "batch"
        return config

    ## MAKE & DEPLOY BATCHES ----
    def _file_patt_fill(self, patt: str) -> str:
        """Fill in file_pattern templates based on config, so batch can just handle IDs"""
        return patt.format(**self.config, id="{id}")

    def _create_batch(
        self, batch_name: str, ids: Path | str | list[str], rename: bool
    ) -> Batch:
        batch_version = self.version if rename else None
        # skipping default args for now
        return Batch(
            name=batch_name,
            ids=ids,
            file_pattern=self.file_pattern,
            image=self.image,
            outdir=self.outdir,
            batchdir=self.config["batch_dir"],
            version=batch_version,
            print_quarto=self.print_quarto,
            print_snakemake=self.print_snakemake,
        )

    def add_batch(
        self, ids: Path | str | list[str], rename: bool = False, append: bool = True
    ) -> None:
        batch_id = len(self.batches)
        batch = self._create_batch(
            batch_name=f"{self.name}-batch-{batch_id}", ids=ids, rename=rename
        )
        if append:
            self.batches.append(batch)
        else:
            self.batches = [batch]

    def run_batches(self) -> None:
        for batch in self.batches:
            batch.run_docker()

    def print_overview(self) -> None:
        click.secho("\nPROJECT: -------------------------", fg="yellow", bold=True)
        print(self)
        click.secho("\nBATCHES: -------------------------", fg="yellow", bold=True)
        for batch in self.batches:
            print(batch)

    def print_docker_logs(self) -> None:
        for batch in self.batches:
            for log in batch.logs:
                click.echo(log)

    ## BASIC METHODS ----
    def __str__(self) -> str:
        return f"""
Project: {self.name} version {self.version}
Docker image: '{self.image}'
File pattern: '{self.file_pattern}'
Batches: {len(self.batches)}"""

    def __iter__(self):
        return iter(self.batches)
