import re
from eqcli.utils import snakecase
import click
from eqcli.utils import read_commented
from eqcli.docker import DockerStream
from pathlib import Path
import uuid

import logging

logger = logging.getLogger(__name__)


class Batch:
    """Class to manage a set of files to generate from a single list of locations or other IDs. A `Batch` can be one of several created by a `Project`, each representing an independent set of files and tracking its own count of successes and failures. Instances of this class are intended to be created by a `Project` rather than called directly.

    Parameters
    ----------
    name : str | None
        Name of this batch. If None, the batch is named based on the `Project` with a batch number attached.
    ids : Path | str | list[str]
        Either a path to a file of IDs (i.e. location names) to be read in, or a list of IDs directly. If a file, it should be formatted with a single ID per line.
    file_pattern : str
        String to be used with `format()` to create desired report filenames. Include `"{id}"` as a placeholder for report IDs such as location names, such as `"{id}_equity_{year}.pdf"`, where `year` is a keyed value in the config file.
    image : str
        Name or URL of docker image, already built
    config : dict
        Snakemake config dictionary, as read from config.yml
    outdir : Path | str
        Directory for final generated reports
    batchdir : str
        Name of batch working directory
    version : str | None
        Text of version tag
    print_quarto : bool, optional
        Whether to run Quarto in verbose mode, including its printout of each chunk rendered, by default False
    print_snakemake : bool, optional
        Whether to run snakemake in verbose mode, by default False
    comment : str | None, optional
        Single character used to "comment" out lines in a file used in `ids`, by default "#"
    """

    mark_success = "+"
    mark_fail = "x"

    def __init__(
        self,
        name: str | None,
        ids: Path | str | list[str],
        file_pattern: str,
        image: str,
        # config: dict,
        outdir: Path | str,
        batchdir: str,
        version: str | None,
        print_quarto: bool = False,
        print_snakemake: bool = False,
        comment: str | None = "#",
        mark_success: str = "+",
        mark_fail: str = "x",
    ):

        if name is None:
            self.name = f"batch-{uuid.uuid4()}"
        else:
            self.name = name
        self.image = image
        self.outdir = Path(outdir)
        self.batchdir = batchdir
        self.version = version
        self.print_quarto = print_quarto
        self.print_snakemake = print_snakemake
        # self.config = config
        self.tries = 0
        self.failures = 0
        self.successes = 0
        self.logs: list[str] = []
        self.mark_success = mark_success
        self.mark_fail = mark_fail
        # self.file_pattern = file_pattern
        # self.files: list[Path] = []

        # ids: either list of names, or file to read names from
        if isinstance(ids, list):
            self.ids = ids
        else:
            self.ids = read_commented(ids, comment)

        self.files = self._create_file_names(file_pattern, to_snakecase=True)
        self.docker = self._prep_container()

    ## FILES ----
    def _create_file_names(
        self, file_pattern: str, to_snakecase: bool = True
    ) -> list[Path]:
        """Create file basenames based on a template literal"""
        if to_snakecase:
            ids = snakecase(self.ids)
        else:
            ids = self.ids
        filenames = [file_pattern.format(id=id) for id in ids]
        # return [Path(self.outdir) / fn for fn in filenames]
        return [Path(fn) for fn in filenames]

    def _rename_tagged(self, orig: Path, sep: str) -> Path | None:
        """Rename a file with a tag appended to its base"""
        # orig = Path(orig)
        orig = self.outdir / orig
        if orig.exists():
            tagged = orig.with_stem(f"{orig.stem}{sep}{self.version}")
            orig.rename(tagged)
            return tagged
        else:
            return None

    # run tag_files at end
    def tag_files(self, sep: str = "-") -> None:
        """Update self.files with tags, given the batch is versioned"""
        if self.version is not None:
            files = [self._rename_tagged(f, sep) for f in self.files]
            self.files = [Path(f) for f in files if f is not None]

    ## LOGGING ----
    def _write_successful(self, log: str | bytes) -> bool | None:
        """Translate bullets from bash script deployed by snakemake into boolean successes/failures"""
        if isinstance(log, bytes):
            log = log.decode("utf-8")
        if isinstance(log, str):
            bullet = re.findall(
                "^(.) .+ (written|failed)", log
            )  # returns list of tuple
            if bullet:
                if bullet[0][0] == self.mark_success:
                    return True
                elif bullet[0][0] == self.mark_fail:
                    return False
                else:
                    return None
        else:
            return None

    def _label_successes(self, log_success: bool | None) -> str | None:
        """Format running count of successes so far"""
        if log_success is not None:
            return f"{self.successes:>3} / {self.tries:>3} succeeding"

    ## DOCKER ----

    def _prep_container(self) -> DockerStream:
        """Create DockerStream instance tied to this batch"""
        container_name = f"{self.name}-docker"
        return DockerStream(
            name=container_name,
            image=self.image,
            outdir=self.outdir,
            contdir=self.batchdir,
            files=self.files,
            print_quarto=self.print_quarto,
            print_snakemake=self.print_snakemake,
        )

    def run_docker(self) -> None:
        """Stream output of docker container running from bash script in subprocess. Stores logs and container results."""
        with self.docker.stream_docker() as logs:
            printout: list[str] = []
            for log in logs:
                log = log.strip()
                logger.debug(log)
                # true, false, or none if no match
                current_success = self._write_successful(log)
                if current_success is not None:
                    if current_success:
                        self.successes += 1
                    self.tries += 1
                    click.echo(self._label_successes(current_success))
                printout.append(log)
        self.failures = self.tries - self.successes
        self.logs = printout

    ## BASIC METHODS ----
    def __str__(self) -> str:
        if self.version is None:
            tagging = "No tagging"
        else:
            tagging = self.version
        return f"""
Batch: {self.name}, {len(self)} files
Output directory: {str(self.outdir.absolute())}
File tagging: {tagging}"""

    def __len__(self) -> int:
        return len(self.files)
