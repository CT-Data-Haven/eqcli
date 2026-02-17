import uuid
import subprocess
from pathlib import Path


class DockerStream:
    """Docker subprocess to be streamed by batch writer"""

    def __init__(
        self,
        name: str | None,
        image: str,
        outdir: Path | str,
        contdir: str,
        files: list[Path],
        print_quarto: bool,
        print_snakemake: bool,
    ):
        if name is None:
            self.name = f"docker-{uuid.uuid4()}"
        else:
            self.name = name
        self.image = image
        # self.files = files
        self.files = [f"{contdir}/{fn}" for fn in files]
        self.quiet_quarto = not print_quarto
        self.snake_quiet_opt = self._make_snakeopt(print_snakemake)
        self.volume = self._make_volume(outdir, contdir)
        # self.stream = self.stream_docker()

    def _make_snakeopt(self, print_snakemake):
        if print_snakemake:
            return "host"
        else:
            return "all"

    def _make_volume(self, outdir, contdir):
        outdir = Path(outdir)
        # if contdir[0] != "/":
        #     contdir = f"/{contdir}"
        return f"{outdir.absolute()}:/project/{contdir}"

    def stream_docker(self):
        quiet_config = f"quiet={self.quiet_quarto}"
        process = subprocess.Popen(
            [
                "docker",
                "run",
                # "--rm",
                "-v",
                self.volume,
                self.image,
                *self.files,
                "--cores",
                "all",
                "--config",
                quiet_config,
                "--quiet",
                self.snake_quiet_opt,
                "--keep-going",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        return process.stdout

    def __str__(self) -> str:
        return f"""
Docker container: {self.name}
Image: '{self.image}'
Volume: {self.volume}"""
