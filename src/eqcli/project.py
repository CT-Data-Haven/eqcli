from eqcli.utils import read_version
import yaml

from eqcli.batch import Batch
from pathlib import Path


class Project:
    """Container for project attributes"""

    # instance attribute
    def __init__(
        self,
        name: str,
        image: str,
        config_file: Path | str,
        file_pattern: str,
        outdir: Path | str,
        version: str | None = None,
        version_file: Path | str | None = None,
        version_patt: str | None = None,
        print_quarto: bool = False,
        print_snakemake: bool = False,
        repo: str | None = None,
    ):
        self.name = name
        self.repo = repo
        self.image = image
        self.file_pattern = file_pattern
        self.outdir = Path(outdir)
        self.config = self._read_config(config_file)
        self.version = self._check_version(version, version_file, version_patt)
        self.print_quarto = print_quarto
        self.print_snakemake = print_snakemake
        self.batches: list[Batch] = []

    def _read_config(self, config_file) -> dict:
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
        if "batch_dir" not in config or "batchdir" not in config:
            config["batch_dir"] = "batch"
        return config

    def _check_version(self, version, version_file, version_patt) -> str:
        if version is None:
            if version_file is None:
                raise ValueError("must supply a version or a version file")
            else:
                return read_version(version_file, version_patt)
        else:
            return version

    # prep batch
    def _create_batch(self, batch_name, ids) -> Batch:
        # skipping default args for now
        return Batch(
            name=batch_name,
            ids=ids,
            file_pattern=self.file_pattern,
            image=self.image,
            config=self.config,
            outdir=self.outdir,
            batchdir=self.config["batch_dir"],
            version=self.version,
            print_quarto=self.print_quarto,
            print_snakemake=self.print_snakemake,
        )

    def add_batch(self, ids, append=True) -> None:
        batch_id = len(self.batches)
        batch = self._create_batch(
            batch_name=f"{self.name}-batch-{batch_id}",
            ids=ids,
        )
        if append:
            self.batches.append(batch)
        else:
            self.batches = [batch]

    # run batch
    def run_batches(self):
        for batch in self.batches:
            batch.run_docker()

    # write release notes

    def __str__(self) -> str:
        return f"""
Project: `{self.name}` version {self.version}
Docker image: '{self.image}'
Batches: {len(self.batches)}"""
