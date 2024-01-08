from __future__ import annotations

import glob
import re
from contextlib import contextmanager
from io import BytesIO, StringIO
from pathlib import Path
from typing import IO, Any, ContextManager, Iterator, overload

from polars.dependencies import _FSSPEC_AVAILABLE, fsspec
from polars.exceptions import NoDataError
from polars.utils.various import normalize_filepath


def _is_glob_pattern(file: str) -> bool:
    return any(char in file for char in ["*", "?", "["])


def _is_supported_cloud(file: str) -> bool:
    return bool(re.match("^(s3a?|gs|gcs|file|abfss?|azure|az|adl|https?)://", file))


def _is_local_file(file: str) -> bool:
    try:
        next(glob.iglob(file, recursive=True))  # noqa: PTH207
    except StopIteration:
        return False
    else:
        return True


@overload
def _prepare_file_arg(
    file: str | list[str] | Path | IO[bytes] | bytes,
    encoding: str | None = ...,
    *,
    use_pyarrow: bool = ...,
    raise_if_empty: bool = ...,
    storage_options: dict[str, Any] | None = ...,
) -> ContextManager[str | BytesIO]:
    ...


@overload
def _prepare_file_arg(
    file: str | Path | IO[str] | IO[bytes] | bytes,
    encoding: str | None = ...,
    *,
    use_pyarrow: bool = ...,
    raise_if_empty: bool = ...,
    storage_options: dict[str, Any] | None = ...,
) -> ContextManager[str | BytesIO]:
    ...


@overload
def _prepare_file_arg(
    file: str | list[str] | Path | IO[str] | IO[bytes] | bytes,
    encoding: str | None = ...,
    *,
    use_pyarrow: bool = ...,
    raise_if_empty: bool = ...,
    storage_options: dict[str, Any] | None = ...,
) -> ContextManager[str | list[str] | BytesIO | list[BytesIO]]:
    ...


def _prepare_file_arg(
    file: str | list[str] | Path | IO[str] | IO[bytes] | bytes,
    encoding: str | None = None,
    *,
    use_pyarrow: bool = False,
    raise_if_empty: bool = True,
    storage_options: dict[str, Any] | None = None,
) -> ContextManager[str | list[str] | BytesIO | list[BytesIO]]:
    """
    Prepare file argument.

    Utility for read_[csv, parquet]. (not to be used by scan_[csv, parquet]).
    Returned value is always usable as a context.

    A :class:`StringIO`, :class:`BytesIO` file is returned as a :class:`BytesIO`.
    A local path is returned as a string.
    An http URL is read into a buffer and returned as a :class:`BytesIO`.

    When `encoding` is not `utf8` or `utf8-lossy`, the whole file is
    first read in python and decoded using the specified encoding and
    returned as a :class:`BytesIO` (for usage with `read_csv`).

    A `bytes` file is returned as a :class:`BytesIO` if `use_pyarrow=True`.

    When fsspec is installed, remote file(s) is (are) opened with
    `fsspec.open(file, **kwargs)` or `fsspec.open_files(file, **kwargs)`.
    If encoding is not `utf8` or `utf8-lossy`, decoding is handled by
    fsspec too.
    """
    storage_options = storage_options or {}

    # Small helper to use a variable as context
    @contextmanager
    def managed_file(file: Any) -> Iterator[Any]:
        try:
            yield file
        finally:
            pass

    has_utf8_utf8_lossy_encoding = (
        encoding in {"utf8", "utf8-lossy"} if encoding else True
    )
    encoding_str = encoding if encoding else "utf8"

    # PyArrow allows directories, so we only check that something is not
    # a dir if we are not using PyArrow
    check_not_dir = not use_pyarrow

    if isinstance(file, bytes):
        if not has_utf8_utf8_lossy_encoding:
            file = file.decode(encoding_str).encode("utf8")
        return _check_empty(
            BytesIO(file), context="bytes", raise_if_empty=raise_if_empty
        )

    if isinstance(file, StringIO):
        return _check_empty(
            BytesIO(file.read().encode("utf8")),
            context="StringIO",
            read_position=file.tell(),
            raise_if_empty=raise_if_empty,
        )

    if isinstance(file, BytesIO):
        if not has_utf8_utf8_lossy_encoding:
            return _check_empty(
                BytesIO(file.read().decode(encoding_str).encode("utf8")),
                context="BytesIO",
                read_position=file.tell(),
                raise_if_empty=raise_if_empty,
            )
        return managed_file(
            _check_empty(
                b=file,
                context="BytesIO",
                read_position=file.tell(),
                raise_if_empty=raise_if_empty,
            )
        )

    if isinstance(file, Path):
        if not has_utf8_utf8_lossy_encoding:
            return _check_empty(
                BytesIO(file.read_bytes().decode(encoding_str).encode("utf8")),
                context=f"Path ({file!r})",
                raise_if_empty=raise_if_empty,
            )
        return managed_file(normalize_filepath(file, check_not_directory=check_not_dir))

    if isinstance(file, str):
        # make sure that this is before fsspec
        # as fsspec needs requests to be installed
        # to read from http
        if file.startswith("http"):
            return _process_http_file(file, encoding_str)
        if _FSSPEC_AVAILABLE:
            from fsspec.utils import infer_storage_options

            # check if it is a local file
            if infer_storage_options(file)["protocol"] == "file":
                # (lossy) utf8
                if has_utf8_utf8_lossy_encoding:
                    return managed_file(
                        normalize_filepath(file, check_not_directory=check_not_dir)
                    )
                # decode first
                with Path(file).open(encoding=encoding_str) as f:
                    return _check_empty(
                        BytesIO(f.read().encode("utf8")),
                        context=f"{file!r}",
                        raise_if_empty=raise_if_empty,
                    )
            storage_options["encoding"] = encoding
            return fsspec.open(file, **storage_options)

    if isinstance(file, list) and bool(file) and all(isinstance(f, str) for f in file):
        if _FSSPEC_AVAILABLE:
            from fsspec.utils import infer_storage_options

            if has_utf8_utf8_lossy_encoding:
                if all(infer_storage_options(f)["protocol"] == "file" for f in file):
                    return managed_file(
                        [
                            normalize_filepath(f, check_not_directory=check_not_dir)
                            for f in file
                        ]
                    )
            storage_options["encoding"] = encoding
            return fsspec.open_files(file, **storage_options)

    if isinstance(file, str):
        file = normalize_filepath(file, check_not_directory=check_not_dir)
        if not has_utf8_utf8_lossy_encoding:
            with Path(file).open(encoding=encoding_str) as f:
                return _check_empty(
                    BytesIO(f.read().encode("utf8")),
                    context=f"{file!r}",
                    raise_if_empty=raise_if_empty,
                )

    return managed_file(file)


def _check_empty(
    b: BytesIO, *, context: str, raise_if_empty: bool, read_position: int | None = None
) -> BytesIO:
    if raise_if_empty and not b.getbuffer().nbytes:
        hint = (
            f" (buffer position = {read_position}; try seek(0) before reading?)"
            if context in ("StringIO", "BytesIO") and read_position
            else ""
        )
        raise NoDataError(f"empty CSV data from {context}{hint}")
    return b


def _process_http_file(path: str, encoding: str | None = None) -> BytesIO:
    from urllib.request import urlopen

    with urlopen(path) as f:
        if not encoding or encoding in {"utf8", "utf8-lossy"}:
            return BytesIO(f.read())
        else:
            return BytesIO(f.read().decode(encoding).encode("utf8"))
