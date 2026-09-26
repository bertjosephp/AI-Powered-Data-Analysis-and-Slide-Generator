"""Turn uploaded bytes into a DataFrame, rejecting anything we can't analyze."""

import csv
import io
from pathlib import PurePath

import pandas as pd

from app.errors import AppError, ErrorCode

SUPPORTED_EXTENSIONS = frozenset({".csv", ".xlsx", ".xls"})
CSV_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")
_SNIFF_BYTES = 64 * 1024
_XLSX_MAGIC = b"PK\x03\x04"
_XLS_MAGIC = b"\xd0\xcf\x11\xe0"


def load_dataset(data: bytes, filename: str, max_bytes: int) -> pd.DataFrame:
    if len(data) > max_bytes:
        raise AppError(
            ErrorCode.FILE_TOO_LARGE,
            f"File is {len(data) / 1_048_576:.1f} MB; the limit is {max_bytes // 1_048_576} MB.",
        )
    if not data:
        raise AppError(ErrorCode.EMPTY_DATASET, "The uploaded file is empty.")

    ext = PurePath(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise AppError(
            ErrorCode.INVALID_FILE,
            f"Unsupported file type '{ext or filename}'. Upload a .csv, .xlsx or .xls file.",
        )

    df = _read_csv(data) if ext == ".csv" else _read_excel(data, ext)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    if df.empty or len(df.columns) == 0:
        raise AppError(ErrorCode.EMPTY_DATASET, "The dataset has no rows or no columns.")
    df.columns = pd.Index([str(c).strip() for c in df.columns])
    return df


def _read_csv(data: bytes) -> pd.DataFrame:
    if b"\x00" in data[:_SNIFF_BYTES]:
        raise AppError(ErrorCode.INVALID_FILE, "The file looks binary, not a CSV.")

    for encoding in CSV_ENCODINGS:
        try:
            head = data[:_SNIFF_BYTES].decode(encoding)
        except UnicodeDecodeError:
            continue
        try:
            return pd.read_csv(
                io.BytesIO(data), sep=_sniff_delimiter(head), encoding=encoding, low_memory=False
            )
        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError as e:
            raise AppError(ErrorCode.EMPTY_DATASET, "The CSV file has no data.") from e
        except pd.errors.ParserError as e:
            raise AppError(ErrorCode.INVALID_FILE, f"Could not parse the CSV: {e}") from e
    raise AppError(ErrorCode.INVALID_FILE, "Could not decode the CSV text encoding.")


def _sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _read_excel(data: bytes, ext: str) -> pd.DataFrame:
    magic = _XLSX_MAGIC if ext == ".xlsx" else _XLS_MAGIC
    if not data.startswith(magic):
        raise AppError(ErrorCode.INVALID_FILE, f"The file is not a valid {ext} workbook.")
    try:
        return pd.read_excel(io.BytesIO(data), sheet_name=0)
    except Exception as e:  # openpyxl/xlrd raise a wide variety of errors on corrupt files
        raise AppError(ErrorCode.INVALID_FILE, f"Could not read the workbook: {e}") from e
