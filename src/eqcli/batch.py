import re
from eqcli.utils import snakecase
import click
from eqcli.utils import read_commented
from eqcli.docker import DockerStream
from pathlib import Path
import uuid

import logging

logger = logging.getLogger("batch")
logging.basicConfig(level=logging.DEBUG)


class Batch:
    """Assemble file names, prep writing process, deploy docker, return logs"""

    # should have file names, args to pass to bash script, way to map files from container back to host

    def __init__(
        self,
        name: str | None,
        ids: Path | str | list[str],
        file_pattern: str,
        image: str,
        config: dict,
        outdir: Path | str,
        batchdir: str,
        version: str | None,
        clean: bool = False,
        clean_glob: str | None = None,
        print_quarto: bool = False,
        print_snakemake: bool = False,
        comment: str | None = "#",
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
        self.config = config
        self.tries = 0
        self.failures = 0
        self.successes = 0
        self.logs: list[str] = []
        # self.file_pattern = file_pattern
        # self.files: list[Path] = []

        # setup outdir
        self._setup_dir()
        if clean and clean_glob is not None:
            self._clean_dir(clean_glob)

        # ids: either list of names, or file to read names from
        if isinstance(ids, list):
            self.ids = ids
        else:
            self.ids = read_commented(ids, comment)

        self.files = self._create_file_names(file_pattern, to_snakecase=True, **config)
        self.docker = self._prep_container()
        logger.debug(self.docker)

    ## SETUP ----
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

    ## FILES ----
    def _create_file_names(
        self, file_pattern: str, to_snakecase: bool = True, **kwargs
    ) -> list[Path]:
        """Create file basenames based on a template literal"""
        if to_snakecase:
            ids = snakecase(self.ids)
        else:
            ids = self.ids
        filenames = [file_pattern.format(**kwargs, id=id) for id in ids]
        # return [Path(self.outdir) / fn for fn in filenames]
        return [Path(fn) for fn in filenames]

    def _rename_tagged(self, orig: Path, tag: str, sep: str = "-") -> Path | None:
        """Rename a file with a tag appended to its base"""
        orig = Path(orig)
        if orig.exists():
            tagged = orig.with_stem(f"{orig.stem}{sep}{tag}")
            orig.rename(tagged)
            return tagged
        else:
            return None

    # run tag_files at end
    def tag_files(self, sep: str = "-") -> None:
        """Update self.files with tags, given the batch is versioned"""
        if self.version is not None:
            files = [self._rename_tagged(f, self.version, sep) for f in self.files]
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
                if bullet[0][0] == "+":
                    return True
                elif bullet[0][0] == "x":
                    return False
                else:
                    return None
        else:
            return None

    def _label_successes(self, log_success: bool | None) -> str | None:
        """Format running count of successes so far"""
        # if info is not None and "successes" in info.keys():
        #     if info["successes"] is not None:
        #         return f"{info['successes']:>3} / {info['tries']:>3} succeeding"
        if log_success is not None:
            return f"{self.successes:>3} / {self.tries:>3} succeeding"

    ## DOCKER ----

    def _prep_container(self) -> DockerStream:
        # container_files = [Path(self.batchdir) / fn for fn in self.files]
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
