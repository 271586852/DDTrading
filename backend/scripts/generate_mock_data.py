from __future__ import annotations

import random
from pathlib import Path

import polars as pl


OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "mock_data.parquet"
SECTORS = [
    ("QuantumTech", 600000),
    ("CloudEnergy", 600100),
    ("NovaAero", 600200),
    ("LatticeSemi", 600300),
    ("NorthMed", 600400),
    ("SkylineMfg", 600500),
]


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def build_mock_rows(sample_size: int = 300) -> list[dict[str, float | str]]:
    random.seed(42)
    rows: list[dict[str, float | str]] = []

    for index in range(sample_size):
        sector_name, base_code = SECTORS[index % len(SECTORS)]
        ticker = f"{base_code + index:06d}"
        name = f"{sector_name}{index + 1:03d}"

        pe_ratio = round(clamp(random.gauss(24, 11), 5, 85), 2)
        momentum_20d = round(clamp(random.gauss(0.06, 0.12), -0.35, 0.45), 4)
        volatility = round(clamp(random.gauss(0.032, 0.012), 0.008, 0.095), 4)

        rows.append(
            {
                "ticker": ticker,
                "name": name,
                "pe_ratio": pe_ratio,
                "momentum_20d": momentum_20d,
                "volatility": volatility,
            }
        )

    return rows


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    dataframe = pl.DataFrame(build_mock_rows())
    dataframe.write_parquet(OUTPUT_PATH)
    print(f"Generated {dataframe.height} rows at: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
