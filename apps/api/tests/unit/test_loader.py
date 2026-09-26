from pathlib import Path

import pytest

from app.errors import AppError, ErrorCode
from app.services.ingestion.loader import load_dataset

FIXTURES = Path(__file__).parent.parent / "fixtures"
MB = 1024 * 1024


def _load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_loads_csv() -> None:
    df = load_dataset(_load("sample.csv"), "sample.csv", 25 * MB)
    assert df.shape == (40, 9)
    assert list(df.columns)[:3] == ["order_id", "order_date", "region"]


def test_loads_xlsx_with_same_shape_as_csv() -> None:
    df = load_dataset(_load("sample.xlsx"), "Sample.XLSX", 25 * MB)
    assert df.shape == (40, 9)


def test_messy_csv_sniffs_delimiter_decodes_cp1252_and_drops_blank_rows() -> None:
    df = load_dataset(_load("messy.csv"), "messy.csv", 25 * MB)
    assert list(df.columns) == ["city", "temp_c", "note"]
    assert df["city"].tolist() == ["Zürich", "Montréal", "São Paulo"]


def test_strips_column_names_and_drops_empty_columns() -> None:
    data = b" a , b ,empty\n1,2,\n3,4,\n"
    df = load_dataset(data, "x.csv", MB)
    assert list(df.columns) == ["a", "b"]


@pytest.mark.parametrize(
    ("data", "filename", "code"),
    [
        (b"a,b\n1,2\n", "data.json", ErrorCode.INVALID_FILE),
        (b"", "empty.csv", ErrorCode.EMPTY_DATASET),
        (b"\n\n", "blank.csv", ErrorCode.EMPTY_DATASET),
        (b"a,b\n", "header_only.csv", ErrorCode.EMPTY_DATASET),
        (b"\x00\x01\x02binary", "bin.csv", ErrorCode.INVALID_FILE),
        (b"a,b\n1,2\n", "fake.xlsx", ErrorCode.INVALID_FILE),
        (b"PK\x03\x04garbage", "corrupt.xlsx", ErrorCode.INVALID_FILE),
    ],
)
def test_rejects_bad_input(data: bytes, filename: str, code: ErrorCode) -> None:
    with pytest.raises(AppError) as exc:
        load_dataset(data, filename, MB)
    assert exc.value.code == code


def test_rejects_oversized_file() -> None:
    with pytest.raises(AppError) as exc:
        load_dataset(b"a\n" * 100, "big.csv", max_bytes=10)
    assert exc.value.code == ErrorCode.FILE_TOO_LARGE
