# offshoot of project, not batch, so list files in current outdir state
from zipfile import ZipFile, ZIP_BZIP2
import re
import click
from pathlib import Path
import pandas as pd
from eqcli.utils import file_timestamp, titlecase, id_from_file, check_version
import logging

logger = logging.getLogger(__name__)


class Release:
    def __init__(
        self,
        name: str,
        outdir: Path | str,
        version: str | None = None,
        version_file: Path | str | None = None,
        version_patt: str | None = None,
        id_regex: str | re.Pattern = r"(\w+)_equity",
        md_out: Path | str = "release-notes.md",
        xwalk_path: Path | str | None = None,
        xwalk_join_on: str | None = None,
        xwalk_group_col: str | None = None,
        glob: str | None = "*.pdf",
    ):
        self.name = name
        self.outdir = Path(outdir)
        self.version = check_version(version, version_file, version_patt)
        self.md_out = Path(md_out)
        self.group_col = xwalk_group_col

        if xwalk_path is not None:
            xwalk = self._read_xwalk(xwalk_path)
        else:
            xwalk = None

        if glob is None:
            glob = "*"

        self.files_df = self._list_files(glob, id_regex, xwalk, xwalk_join_on)
        self.last_mod = self.files_df["modified"].max()

    def _read_xwalk(self, path: Path | str) -> pd.DataFrame:
        df = pd.read_csv(path)
        return df

    def _list_files(
        self,
        glob: str,
        id_regex: str | re.Pattern,
        xwalk: pd.DataFrame | None,
        join_on: str | None,
    ) -> pd.DataFrame:
        """Create df of files for release, optionally joining with a crosswalk to categorize reports"""
        files = [f for f in self.outdir.glob(glob)]
        df = pd.DataFrame(files, columns=["path"])
        df["fn"] = df["path"].apply(lambda x: x.name)
        df["modified"] = df["path"].apply(file_timestamp)
        df["id"] = df["fn"].apply(lambda x: id_from_file(x, id_regex))
        df["id"] = df["id"].apply(titlecase)
        df = df.loc[:, ["id", "path", "modified"]]
        df = df.set_index("id")

        # if this release has a grouping crosswalk, merge it here and reindex
        if isinstance(xwalk, pd.DataFrame):
            if join_on in xwalk.columns:
                xwalk = xwalk.set_index(join_on)
                df = df.merge(xwalk, left_index=True, right_index=True, how="left")
                df = df.reset_index()
            else:
                logger.warning(f"Missing column {join_on} in xwalk; skipping join step")
                return df
        if self.group_col in df.columns:
            df = df.sort_values([self.group_col, "id"]).set_index(self.group_col)
        else:
            df = df.sort_values("id")
        return df

    def _df_to_zip(
        self,
        zipname: str,
        df: pd.DataFrame,
        zipdir: Path,
        path_col: str = "path",
        verbose: bool = True,
    ) -> Path:
        paths = df[path_col].to_list()
        file_out = zipdir / f"{zipname}.zip"
        with ZipFile(file_out, "w", compression=ZIP_BZIP2) as zipper:
            for file in paths:
                zipper.write(file)
            if verbose:
                click.echo(f"{file_out} created with {len(paths)} file(s).")
        return file_out

    def write_notes_md(self, verbose: bool = True) -> None:
        """Write files_df to markdown table"""
        self.files_df.reset_index().to_markdown(self.md_out)
        if verbose:
            if self.md_out.exists():
                click.echo(f"Markdown table written to {self.md_out}")
            else:
                click.echo(f"Failed to write markdown table to {self.md_out}")
        return None

    def zip_files(
        self, zip_by_group: bool, zipdir: Path | str | None = None, verbose: bool = True
    ) -> list[Path]:
        if zipdir is None:
            zipdir = "."
        zipdir = Path(zipdir)
        zipdir.mkdir(parents=True, exist_ok=True)
        # copy to avoid changing object's dataframe
        df = self.files_df.copy()
        zip_paths = []
        if zip_by_group:
            # should be indexed by group col but double check
            if self.group_col in df.columns:
                df = df.set_index(self.group_col)
            elif self.group_col not in df.index.names:
                raise ValueError(f"column {self.group_col} not found in df columns")
            # df_to_zip for each sub-df
            groups = df.index.unique()
            for group in groups:
                name = f"{self.name}_{group}-{self.version}"
                grp_df = df.loc[[group], :]
                zip_path = self._df_to_zip(
                    zipname=name,
                    df=grp_df,
                    zipdir=zipdir,
                    path_col="path",
                    verbose=verbose,
                )
                zip_paths.append(zip_path)
        else:
            # df_to_zip for full df
            name = f"{self.name}_all_files-{self.version}"
            zip_path = self._df_to_zip(
                zipname=name, df=df, zipdir=zipdir, path_col="path", verbose=verbose
            )
            zip_paths.append(zip_path)
        return zip_paths

    def __str__(self) -> str:
        return f"""
Release: {self.name} version {self.version}
Files: {len(self.files_df)}
Last file modification: {self.last_mod}
Notes: {self.md_out.absolute()}"""
