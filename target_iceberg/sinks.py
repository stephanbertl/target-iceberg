"""Iceberg target sink class, which handles writing streams."""

from __future__ import annotations
from typing import Dict, List, Optional
from singer_sdk import PluginBase
from singer_sdk.sinks import BatchSink
import pyarrow as pa
from pyiceberg.catalog import load_catalog
from pyiceberg.exceptions import NoSuchTableError
from requests import HTTPError

from .iceberg import singer_schema_to_pyiceberg_schema


class IcebergSink(BatchSink):
    """Iceberg target sink class."""

    max_size = 10000  # Max records to write in one batch

    def __init__(
        self,
        target: PluginBase,
        stream_name: str,
        schema: Dict,
        key_properties: Optional[List[str]],
    ) -> None:
        super().__init__(
            target=target,
            schema=schema,
            stream_name=stream_name,
            key_properties=key_properties,
        )
        self.stream_name = stream_name
        self.schema = schema

    def process_batch(self, context: dict) -> None:
        """Write out any prepped records and return once fully written.

        Args:
            context: Stream partition or context dictionary.
        """

        # Create pyarrow df
        df = pa.Table.from_pylist(context["records"])

        # Load the Iceberg catalog
        # IMPORTANT: Make sure pyiceberg catalog env variables are set in the host machine - i.e. PYICEBERG_CATALOG__DEFAULT__URI, etc
        #   - For more details, see: https://py.iceberg.apache.org/configuration/)
        catalog_name = self.config.get("iceberg_catalog_name")
        catalog = load_catalog(catalog_name)

        # Create a namespace if it doesn't exist
        ns_name = self.config.get("iceberg_catalog_namespace_name")
        nss = catalog.list_namespaces()
        ns_names = [n[0] for n in nss]
        if ns_name not in ns_names:
            catalog.create_namespace(ns_name)

        # Create a table if it doesn't exist
        table_name = self.stream_name
        table_identifier = f"{catalog_name}.{ns_name}.{table_name}"
        self.logger.info(f"table_id={table_identifier}")

        try:
            table = catalog.load_table(table_identifier)
            
            # TODO: Handle schema evolution - compare existing table schema with singer schema (converted to pyiceberg schema)
        except NoSuchTableError:
            # Table doesn't exist, so create it
            table_schema = singer_schema_to_pyiceberg_schema(self, self.schema)
            self.logger.info(f"Creating table {table_identifier}")
            table = catalog.create_table(table_identifier, schema=table_schema)

        # Add data to the table
        table.append(df)
