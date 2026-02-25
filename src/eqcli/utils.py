"""Utility functions, mostly for working with filenames to parse information in snakemake workflows."""

### STRING UTILITIES--------------------
######################################
import urllib
from urllib.parse import urlparse
from urllib.request import urlopen
from datetime import datetime
import tomllib
import re

from pathlib import Path


def _snakecase(x: str) -> str:
    """Convert single string to snakecase.

    Parameters
    ----------
    x : str
        String to be converted.

    Returns
    -------
    str
        String in snakecase.
    """
    return x.lower().replace(" ", "_")


def snakecase(x: list[str] | str) -> list[str] | str:
    """Convert single string or list of strings to snakecase.

    Parameters
    ----------
    x : list[str] | str
        String or list of strings to be converted.

    Returns
    -------
    list[str] | str
        String or list of strings in snakecase.
    """
    if isinstance(x, list):
        return [_snakecase(i) for i in x]
    else:
        return _snakecase(x)


def _titlecase(x: str, cap: list[str] | None) -> str:
    """Convert single string to titlecase, optionally writing some text in all caps.

    Parameters
    ----------
    x : str
        String to be converted.
    cap : list[str] | None
        Optional list of strings to be all caps.

    Returns
    -------
    str
        String in titlecase, with `cap` substrings in all caps.
    """
    title = x.title()
    if cap is not None:
        for c in cap:
            cap_title = c.title()
            title = title.replace(cap_title, c)

    return title.replace("_", " ")


def titlecase(
    x: list[str] | str, cap: list[str] | None = ["COG", "HSA"]
) -> list[str] | str:
    """Convert single string or list of strings to titlecase, optionally writing some text in all caps (such as acronyms).

    Parameters
    ----------
    x : list[str] | str
        String or list of strings to be converted.
    cap : list[str] | None, optional
        Optional list of strings to be all caps. If `None`, this step is skipped. By default, ["COG", "HSA"].

    Returns
    -------
    list[str] | str
        String or list of strings in titlecase, with `cap` substrings in all caps.
    """
    if isinstance(x, list):
        return [_titlecase(i, cap) for i in x]
    else:
        return _titlecase(x, cap)


def unabbrev_yrs(x: str, sep: str = "_") -> str:
    """Split a concatenated string of years in 2-digit format

    Parameters
    ----------
    x : str
        A string of two 2-digit years smooshed together, e.g. "1524"
    sep : str, optional
        Character to separate strings in output, by default "_"

    Returns
    -------
    str
        A string of years separated, e.g. "1524" -> "15_24"
    """
    return f"{x[0:2]}{sep}{x[2:4]}"


def _y2k(x: str) -> str:
    return "20" + x


def y2k(x: str, sep: str = "_") -> str:
    """Bring 2-digit years into the 21st century.

    Parameters
    ----------
    x : str
        String with one or more sets of 21st century years in 2-digit format, e.g. "15_24"
    sep : str, optional
        Separator on which to split years, by default '_'

    Returns
    -------
    str
        String where 2-digit years have been converted to 4-digit, e.g. "15_24" -> "2015_2024"
    """
    xs = x.split(sep)
    return sep.join([_y2k(i) for i in xs])


### FILE UTILITIES ------------------------
######################################


# check url vs file
def _is_url(path: str | Path) -> bool:
    return urlparse(str(path)).scheme in ["http", "https"]


def read_commented(path: str | Path, comment: str | None = "#") -> list[str]:
    """Read lines in a file, optionally omitting commented lines

    Parameters
    ----------
    path : str | Path
        Path to a text file
    comment : str | None, optional
        Single character string designating a line to omit, by default '#'

    Returns
    -------
    list[str]
        Lines of the file as a list of strings, excluding commented lines

    Raises
    ------
    ValueError
        'comment' must be a string of length 1
    """
    if comment is not None and len(comment) != 1:
        raise ValueError("'comment' should be a string of length 1")
    if _is_url(path):
        with urlopen(str(path)) as f:
            lines = f.read().splitlines()
            lines = [l.decode() for l in lines]
    else:
        with open(path, "r") as f:
            lines = f.read().splitlines()
    if comment is None:
        return lines
    else:
        return [line for line in lines if line[0] != comment]


def create_file_names(
    template: str,
    path: str | Path | None = None,
    ids: list[str] | None = None,
    to_snakecase: bool = True,
    comment: str | None = "#",
    **kwargs,
) -> list[str]:
    """Batch create filenames based on IDs read from a text file and/or a list, formatted with a template literal and kwargs

    Parameters
    ----------
    template : str
        Template that can be interpreted by `format()`. Should contain '{id}' to have that filled in by identifiers
    path : str | Path | None, optional
        Path to a text file of identifiers that can be passed to `read_commented`, by default None
    ids : list[str] | None, optional
        List of strings of identifiers, by default None
    to_snakecase : bool, optional
        Convert filenames to snakecase, by default True
    comment : str | None, optional
        Single string designating a comment for omitting lines to pass to `read_commented`, by default "#"
    **kwargs: dict
        Keyword args to fill into the template

    Returns
    -------
    list[str]
        A list of strings giving paths to output files with keywords filled in.

    Raises
    ------
    ValueError
        Errors if both 'path' and 'ids' are None

    Examples
    ------
    >>> create_file_names("{outdir}/{id}_report_{yr}.pdf", ids=["New Haven", "Hartford"], outdir="to_distro", yr=2026)
    ['to_distro/new_haven_report_2026.pdf', 'to_distro/hartford_report_2026.pdf']
    """
    if path is None and ids is None:
        raise ValueError("must supply 'path' and/or 'ids'")
    if ids is None:
        ids_out = []
    else:
        ids_out = ids
    if path is not None:
        ids_out = ids_out + read_commented(path, comment)
    if to_snakecase:
        ids_out = snakecase(ids_out)
    return [template.format(**kwargs, id=id) for id in ids_out]


def file_timestamp(path: Path | str, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Get file's modification time as a formatted timestamp

    Parameters
    ----------
    path : Path | str
        Path to file
    fmt  : str
        Datetime format compatable with `strftime`, defaults "%Y-%m-%d %H:%M:%S"

    Returns
    -------
    str
        Formatted timestamp
    """
    path = Path(path)
    mod = path.stat().st_mtime
    timestamp = datetime.fromtimestamp(mod)
    fmttd = timestamp.strftime(fmt)
    return fmttd


def parse_file_pattern(filename: Path | str, file_pattern: str):
    """Convert format string used for generating file names into regex to extract IDs"""
    filename = str(filename)
    # replace {id} with regex for named matching group
    # e.g. "{id}_equity_{doc_yr}.{ext}" -> "(?P<id>.+)_equity_{doc_yr}.{ext}"
    patt1 = file_pattern.replace("{id}", "(?P<id>.+)")
    # replace brackets with wildcards
    patt2 = re.sub(r"\{.*?\}", ".+", patt1)
    id = re.compile(patt2).findall(filename)
    return id[0]


def id_from_file(path: Path | str, patt: str | re.Pattern) -> str | None:
    """Extract a report ID (location, etc) from its filename given a regex pattern

    Parameters
    ----------
    path : Path | str
        Path to file
    patt : str | re.Pattern
        Pattern or string that can be compiled to re pattern. Should probably contain a group to match.

    Returns
    -------
    str | None
        If the pattern matches, the first match is returned; otherwise, None

    Examples
    --------
    >>> id_from_file("to_distro/capitol_region_cog_equity_2026.pdf", "(\\w+)_equity")
    'capitol_region_cog'
    """
    fn = Path(path).name
    if isinstance(patt, str):
        patt = re.compile(patt)
    id = patt.findall(fn)
    if id:
        return id[0]
    else:
        return None


### METADATA----------------------------
######################################


def read_version(file: Path | str, patt: str | None = None) -> str:
    """Extract project version from a file based on a pattern

    Parameters
    ----------
    file : Path | str, optional
        Path to a file containing project version
    patt : str | None, optional
        Pattern to compile to regex in order to extract version. If None, will supply a pattern that matches either an R description file or a common pyproject.toml pattern.

    Returns
    -------
    str
        First match found, in "v$version" format.
    """
    # if no pattern supplied, use appropriate for file type
    file = Path(file)
    if file.stem == "DESCRIPTION":
        txt = file.read_text()
        if patt is None:
            patt = r"(?<=Version:\s)([0-9a-z\-\.]+)(?=\n)"
        version = re.compile(patt).findall(txt)
    else:
        version = value_from_toml(file, key="version")
    if version:
        return f"v{version[0]}"
    else:
        raise ValueError("pattern 'patt' not found for project version")


def read_proj_name(file: Path | str, patt: str | None = None) -> str:
    file = Path(file)
    if file.stem == "DESCRIPTION":
        txt = file.read_text()
        if patt is None:
            patt = r"(?<=Package:\s)(.+)(?=\n)"
        name = re.compile(patt).findall(txt)
    else:
        name = value_from_toml(file, key="name", table="project")
    if name:
        return name[0]
    else:
        raise ValueError("pattern 'patt' not found for project name")


def check_version(
    version: str | None,
    version_file: Path | str | None,
    version_patt: str | None,
    is_required: bool = True,
) -> str | None:
    """Read and/or verify project version

    Parameters
    ----------
    version : str | None
        Version, such as "0.2.1"
    version_file : Path | str | None
        File containing a version, such as "pyproject.toml" or "DESCRIPTION"
    version_patt : str | None
        Regex pattern to use to find version tag
    is_required : bool
        If true (default), must resolve to some version. Otherwise, not finding a version and returning None is allowed

    Returns
    -------
    str | None
        The version, either as supplied or as read from a file. `version` argument takes precedence if both it and `version_file` are given. If `is_required` is false and no version is found, will return `None`.

    Raises
    ------
    ValueError
        Error if neither `version` nor `version_file` is given, and `is_required=True`.
    """
    if version is None:
        if version_file is None:
            if is_required:
                raise ValueError("must supply a version or a version file")
            else:
                return None
        else:
            if is_required:
                return read_version(version_file, version_patt)
            else:
                try:
                    return read_version(version_file, version_patt)
                except ValueError:
                    return None
    else:
        return version


def value_from_toml(file: Path | str, key: str, table: str | None = None):
    with open(file, "rb") as f:
        config = tomllib.load(f)
    if table is None:
        return [v[key] for k, v in config.items() if key in v.keys()]
    else:
        return [config[table][key]]


# def version_from_toml(file: Path | str):
#     with open(file, "rb") as f:
#         config = tomllib.load(f)
#     # find nested dict with version key
#     return [v["version"] for k, v in config.items() if "version" in v.keys()]
