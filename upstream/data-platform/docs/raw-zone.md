# Raw Zone 归档规范

Raw Zone 只做 Parquet / gzip JSON 文件归档，不是 Iceberg namespace，也不接入
Iceberg catalog。`data_platform.serving.catalog.ensure_namespaces(...)` 会拒绝创建
`raw` namespace；Raw 数据必须留在文件目录中，不能绕过该 guard 写入 Iceberg。

## 路径规范

每个 Raw artifact 必须写入一个 source、dataset、date partition 下：

```text
<raw_root>/<source_id>/<dataset>/dt=YYYYMMDD/<run_id>.parquet
<raw_root>/<source_id>/<dataset>/dt=YYYYMMDD/<run_id>.json.gz
```

字段规则：

- `source_id`、`dataset`、`run_id` 必须是单个相对路径段，不能包含 `/`、`.`、`..`
  或绝对路径。
- `dt=YYYYMMDD` 必须是有效日历日期，表示 Raw 数据归档分区日期。
- `run_id` 必须是 UUID4 或 ULID。该值由 Raw producer 或上游运行上下文提供，
  用于 artifact 幂等性和 manifest 反查。
- 同一 `source_id` / `dataset` / `dt` 分区内不能重复使用同一个 `run_id`。

## Manifest Schema

每个 date partition 必须维护一个 `_manifest.json`，由 `RawWriter` 原子更新：

```json
{
  "manifest_version": 2,
  "source_id": "tushare",
  "dataset": "stock_basic",
  "partition_date": "2026-04-15",
  "provider": "tushare",
  "source_interface_id": "stock_basic",
  "doc_api": "stock_basic",
  "partition_key": [],
  "request_params_hash": "13f1c9c1d5f0...",
  "schema_hash": "6b8c681d0adc...",
  "artifacts": [
    {
      "source_id": "tushare",
      "dataset": "stock_basic",
      "partition_date": "2026-04-15",
      "run_id": "123e4567-e89b-42d3-a456-426614174000",
      "path": "/raw/tushare/stock_basic/dt=20260415/123e4567-e89b-42d3-a456-426614174000.parquet",
      "row_count": 100,
      "written_at": "2026-04-15T01:00:00+00:00",
      "provider": "tushare",
      "source_interface_id": "stock_basic",
      "doc_api": "stock_basic",
      "partition_key": [],
      "request_params_hash": "13f1c9c1d5f0...",
      "schema_hash": "6b8c681d0adc..."
    }
  ]
}
```

`RawReader.list_artifacts(source_id, dataset, partition_date)` 是 manifest 读取合同。
健康检查、dbt staging 和后续 smoke 应复用该结构，不定义第二套 manifest 语义。
`manifest_version=2` 的新增字段用于把 Raw artifact 绑定到 provider catalog：

- `provider`、`source_interface_id`、`doc_api` 来自 active provider interface registry。
- `partition_key` 是该 typed asset 的源侧增量/分区键列表；静态资产为空列表。
- `request_params_hash` 是实际请求参数的稳定 SHA-256，不记录 token 或本地路径。
- `schema_hash` 是 typed Arrow schema 的稳定 SHA-256。

旧 `_manifest.json` 可能没有这些 v2 字段；`RawReader` 和健康检查必须继续兼容读取。

`path` 可以是 `RawWriter` 生成的路径字符串；健康检查会要求它解析后仍位于
`<raw_root>/<source_id>/<dataset>/dt=YYYYMMDD/` 分区内，并指向
`<run_id>.parquet` 或 `<run_id>.json.gz`。

## Producer Payload 边界

`submitted_at` 与 `ingest_seq` 属于 PostgreSQL 队列表 `CandidateQueueItem`，
不属于 Raw producer payload，也不属于本阶段 Raw manifest。Raw manifest 只描述
文件归档事实：source、dataset、partition、run_id、path、row_count、written_at。

## 健康检查

本地或 CI 可运行：

```bash
PYTHONPATH=src python scripts/check_raw_zone.py --root ./data_platform/data/raw --deep --json
```

参数：

- `--root`：Raw Zone 根目录；未传时读取 `get_settings().raw_zone_path`。
  默认配置下该路径为 `<DP_DATA_STORAGE_ROOT_PATH>/raw`。
- `--source`：只扫描一个 `source_id`。
- `--dataset`：只扫描一个 dataset。
- `--date`：只扫描一个 date partition，支持 `YYYY-MM-DD` 或 `YYYYMMDD`。
- `--deep`：读取 Parquet / JSON artifact 计算真实行数并校验 `row_count`。
- `--json`：输出稳定 JSON，供 CI 或后续 smoke 收集。

返回码规则：没有 `error` 级别问题时返回 0；存在 `error` 时返回 1。

健康检查会报告：

- manifest JSON 无法解析或不符合 `RawWriter` manifest 结构。
- manifest 引用的 artifact 文件不存在。
- `--deep` 下 manifest `row_count` 与真实 artifact 行数不一致。
- 同一 partition 内重复 `run_id`。
- partition 目录不是 `dt=YYYYMMDD` 或日期无效。
- partition 内存在未列入 `_manifest.json` 的 Parquet / JSON artifact。
