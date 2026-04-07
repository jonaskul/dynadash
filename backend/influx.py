from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from config import config


def _client() -> InfluxDBClient:
    return InfluxDBClient(
        url=config.influxdb.url,
        token=config.influxdb.token,
        org=config.influxdb.org,
    )


class InfluxWriter:
    """Write time-series measurements to InfluxDB."""

    def write_temperature(
        self,
        area_id: int,
        area_name: str,
        temperature: float,
        setpoint: float,
    ) -> None:
        point = (
            Point("temperature")
            .tag("area_id", str(area_id))
            .tag("area_name", area_name)
            .field("temperature", temperature)
            .field("setpoint", setpoint)
            .time(datetime.now(timezone.utc), WritePrecision.SECONDS)
        )
        with _client() as client:
            write_api = client.write_api(write_options=SYNCHRONOUS)
            write_api.write(bucket=config.influxdb.bucket, record=point)

    def write_level(
        self,
        area_id: int,
        area_name: str,
        channel: int,
        level: float,
    ) -> None:
        point = (
            Point("channel_level")
            .tag("area_id", str(area_id))
            .tag("area_name", area_name)
            .tag("channel", str(channel))
            .field("level", float(level))
            .time(datetime.now(timezone.utc), WritePrecision.SECONDS)
        )
        with _client() as client:
            write_api = client.write_api(write_options=SYNCHRONOUS)
            write_api.write(bucket=config.influxdb.bucket, record=point)

    def write_preset(
        self,
        area_id: int,
        area_name: str,
        preset: int,
    ) -> None:
        point = (
            Point("preset")
            .tag("area_id", str(area_id))
            .tag("area_name", area_name)
            .field("preset", preset)
            .time(datetime.now(timezone.utc), WritePrecision.SECONDS)
        )
        with _client() as client:
            write_api = client.write_api(write_options=SYNCHRONOUS)
            write_api.write(bucket=config.influxdb.bucket, record=point)


class InfluxReader:
    """Query historical measurements from InfluxDB."""

    def _query(self, flux: str) -> list[dict[str, Any]]:
        with _client() as client:
            query_api = client.query_api()
            tables = query_api.query(flux)
        records: list[dict[str, Any]] = []
        for table in tables:
            for record in table.records:
                records.append(
                    {
                        "time": record.get_time().isoformat() if record.get_time() else None,
                        "field": record.get_field(),
                        "value": record.get_value(),
                    }
                )
        return records

    def query_temperature_history(
        self, area_id: int, range_str: str = "24h"
    ) -> list[dict[str, Any]]:
        """Return temperature and setpoint readings for the past *range_str*."""
        flux = f"""
from(bucket: "{config.influxdb.bucket}")
  |> range(start: -{range_str})
  |> filter(fn: (r) => r._measurement == "temperature")
  |> filter(fn: (r) => r.area_id == "{area_id}")
  |> filter(fn: (r) => r._field == "temperature" or r._field == "setpoint")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
"""
        with _client() as client:
            query_api = client.query_api()
            tables = query_api.query(flux)

        results: list[dict[str, Any]] = []
        for table in tables:
            for record in table.records:
                results.append(
                    {
                        "time": record.get_time().isoformat() if record.get_time() else None,
                        "temperature": record.values.get("temperature"),
                        "setpoint": record.values.get("setpoint"),
                    }
                )
        return results

    def query_level_history(
        self, area_id: int, channel: int, range_str: str = "24h"
    ) -> list[dict[str, Any]]:
        """Return channel level readings for the past *range_str*."""
        flux = f"""
from(bucket: "{config.influxdb.bucket}")
  |> range(start: -{range_str})
  |> filter(fn: (r) => r._measurement == "channel_level")
  |> filter(fn: (r) => r.area_id == "{area_id}")
  |> filter(fn: (r) => r.channel == "{channel}")
  |> filter(fn: (r) => r._field == "level")
  |> sort(columns: ["_time"])
"""
        with _client() as client:
            query_api = client.query_api()
            tables = query_api.query(flux)

        results: list[dict[str, Any]] = []
        for table in tables:
            for record in table.records:
                results.append(
                    {
                        "time": record.get_time().isoformat() if record.get_time() else None,
                        "level": record.get_value(),
                    }
                )
        return results
