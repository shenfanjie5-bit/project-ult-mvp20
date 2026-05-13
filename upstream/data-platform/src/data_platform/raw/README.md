# raw

Raw Zone archival package for Parquet and gzip JSON files.

`RawWriter` now writes manifest v2 metadata when producer code passes it:
`provider`, `source_interface_id`, `doc_api`, `partition_key`,
`request_params_hash`, and `schema_hash`. `RawReader` remains backward
compatible with older manifests that only contain the original artifact fields.
