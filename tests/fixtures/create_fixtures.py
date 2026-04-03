"""Generate sample Parquet fixture files for testing."""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

FIXTURES_DIR = Path(__file__).parent


def create_device_performance() -> None:
    """Create a small device_performance.parquet fixture (15 rows)."""
    table = pa.table(
        {
            "device_id": pa.array([f"dev_{i:03d}" for i in range(15)], type=pa.string()),
            "timestamp": pa.array(
                [f"2025-01-{d:02d}T00:00:00" for d in range(1, 16)], type=pa.string()
            ),
            "cpu_usage": pa.array(
                [45.2, 67.8, 23.1, 89.5, 12.3, 55.0, 78.4, 34.2, 91.0, 60.1, 42.7, 73.6, 28.9, 85.3, 50.0],
                type=pa.float64(),
            ),
            "memory_usage": pa.array(
                [60.0, 72.5, 45.0, 88.0, 30.0, 65.0, 80.0, 50.0, 95.0, 70.0, 55.0, 75.0, 40.0, 90.0, 62.0],
                type=pa.float64(),
            ),
            "latency_ms": pa.array(
                [12, 45, 8, 120, 5, 30, 67, 15, 200, 25, 18, 55, 10, 150, 22],
                type=pa.int64(),
            ),
            "error_count": pa.array(
                [0, 2, 0, 5, 0, 1, 3, 0, 8, 1, 0, 2, 0, 6, 1],
                type=pa.int64(),
            ),
            "region": pa.array(
                ["HCM", "HN", "DN", "HCM", "HN", "DN", "HCM", "HN", "DN", "HCM", "HN", "DN", "HCM", "HN", "DN"],
                type=pa.string(),
            ),
        }
    )
    pq.write_table(table, FIXTURES_DIR / "device_performance.parquet")
    print(f"Created {FIXTURES_DIR / 'device_performance.parquet'}")


def create_user_behavior_30d() -> None:
    """Create a small user_behavior_30d.parquet fixture (20 rows)."""
    table = pa.table(
        {
            "user_id": pa.array([f"usr_{i:04d}" for i in range(20)], type=pa.string()),
            "timestamp": pa.array(
                [f"2025-01-{(d % 28) + 1:02d}T00:00:00" for d in range(20)], type=pa.string()
            ),
            "session_count": pa.array(
                [10, 25, 3, 50, 8, 15, 42, 6, 30, 20, 12, 35, 4, 55, 9, 18, 40, 7, 28, 22],
                type=pa.int64(),
            ),
            "data_usage_gb": pa.array(
                [1.2, 5.5, 0.3, 12.0, 0.8, 2.5, 8.0, 0.5, 6.0, 3.5, 1.5, 7.0, 0.4, 15.0, 1.0, 3.0, 9.0, 0.6, 5.0, 4.0],
                type=pa.float64(),
            ),
            "complaint_count": pa.array(
                [0, 1, 0, 3, 0, 0, 2, 0, 1, 0, 0, 1, 0, 4, 0, 0, 2, 0, 1, 0],
                type=pa.int64(),
            ),
            "avg_session_duration": pa.array(
                [15.5, 30.2, 5.0, 45.0, 10.0, 20.0, 38.0, 8.0, 25.0, 18.0, 12.0, 32.0, 6.0, 50.0, 11.0, 22.0, 40.0, 7.5, 28.0, 19.0],
                type=pa.float64(),
            ),
            "churn_label": pa.array(
                [0, 0, 1, 0, 1, 0, 0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 1, 0, 0],
                type=pa.int64(),
            ),
        }
    )
    pq.write_table(table, FIXTURES_DIR / "user_behavior_30d.parquet")
    print(f"Created {FIXTURES_DIR / 'user_behavior_30d.parquet'}")


if __name__ == "__main__":
    create_device_performance()
    create_user_behavior_30d()
