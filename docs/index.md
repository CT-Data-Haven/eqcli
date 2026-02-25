# eqcli

<!-- badges: start -->

![GitHub Tag](https://img.shields.io/github/v/tag/ct-data-haven/eqcli?style=flat-square)

<!-- badges: end -->
This is a minimal package of utility functions plus a CLI for generating batches of [equity reports](https://ctdatahaven.org/report/connecticut-town-equity-reports/) at DataHaven, plus prepping notes and zip files for release and distro. 

The equity reports project requires generating as many as 200 PDFs, 40+ pages each, of extensive narrative, charts, maps, tables, and notes. All of these moving pieces are orchestrated very precisely across R, Python, and bash, running in a custom Docker container with a snakemake workflow. This is tested locally, then deployed with GitHub Actions. Over the years, the helper Python scripts I've put together for this have evolved into a small yet sprawling CLI, which I am now spinning off into a proper package of its own.

## Installation

Until this is on PyPI or similar, install with `pip` directly from GitHub:

```bash
pip install git+https://github.com/ct-data-haven/eqcli
```

## Getting started

The [CLI](./cli) is built with click, which provides help pages.

```bash
> eqcli --help
Usage: eqcli [OPTIONS] COMMAND [ARGS]...

  Tools for creating equity reports in docker and writing release notes

Options:
  --help  Show this message and exit.

Commands:
  batch-write    Write a batch set of reports using docker
  release-notes  Write notes for a release
  zip-release    Zip files for a release
```

Each command has a `--dry-run` option that prints out information about the relevant objects and their potential outputs, based on supplied parameters (work in progress).

A handful of utility functions are available in the `utils` module, mostly useful for string manipulation and metadata extraction for snakemake.