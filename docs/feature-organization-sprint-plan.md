# Featcat Feature Organization Proposal and Sprint Plan

## 1. Mục tiêu

Tài liệu này điều chỉnh lại proposal bổ sung cho Featcat theo hướng rõ trách nhiệm từng thành phần, có thể triển khai theo sprint, và chuẩn bị nền tảng cho feature registry, feature lineage, online store và materialization.

Mục tiêu chính là tránh việc feature bị tổ chức thành một list phẳng. Thay vào đó, Featcat nên quản lý feature theo cấu trúc có metadata rõ ràng:

```text
DataSource -> Entity -> EntityRelationship -> FeatureView -> Feature -> BusinessMetric -> FeatureSet
```

Trong đó `EntityRelationship` là metadata riêng để biểu diễn quan hệ giữa các entity, ví dụ `Customer HAS_MANY Contract`. Relationship không nên nằm ngầm trong `Entity` hoặc từng `Feature`, vì sau này sẽ khó validate join, khó kiểm soát grain, khó dựng lineage và dễ tạo lỗi duplicate row khi join feature ở các cấp dữ liệu khác nhau.

`BusinessMetric` hoặc `MetricDefinition` là lớp metadata nghiệp vụ nằm trên `Feature`. Một business metric có thể map tới một hoặc nhiều technical features. `FeatureSet` vẫn có thể chọn trực tiếp các technical `Feature` để phục vụ training/serving, nhưng người dùng business có thể tìm kiếm và quản lý feature thông qua metric framework của công ty.

## 2. Phạm vi bổ sung

### 2.1 DataSource

DataSource là metadata mô tả nơi dữ liệu gốc đang nằm. Featcat cần hỗ trợ thêm S3-compatible source để phục vụ dữ liệu offline, đồng thời dùng MinIO để giả lập S3 trong môi trường local dev/test.

Phạm vi cần làm:

- Thêm input source từ S3-compatible storage.
- Dùng MinIO để dev/test local.
- Thiết kế abstraction `DataSource` để sau này mở rộng thêm PostgreSQL, BigQuery, Snowflake, Kafka hoặc file local.
- Thêm config cho bucket, path/prefix, endpoint, access key, secret key, region, format dữ liệu, partition, event time column và schema inference.
- Hỗ trợ validate cơ bản: source tồn tại, credential hợp lệ, format đọc được, schema có các column cần thiết.

Kết quả mong muốn:

- Có thể khai báo một source S3/MinIO trong registry.
- Có thể scan schema từ source.
- Có thể dùng source đó trong FeatureView.

### 2.2 Entity

Entity là đối tượng nghiệp vụ mà feature mô tả. Entity chỉ nên chịu trách nhiệm về định danh và grain, không nên ôm luôn toàn bộ relationship nghiệp vụ.

Ví dụ:

```yaml
name: customer
primary_keys:
  - customer_id
join_keys:
  - customer_id
description: Customer level entity.
```

```yaml
name: contract
primary_keys:
  - contract_id
join_keys:
  - contract_id
  - customer_id
description: Contract level entity.
```

Phạm vi cần làm:

- Chuẩn hóa metadata cho Entity.
- Hỗ trợ primary key và join key.
- Hỗ trợ mô tả grain của entity.
- Hỗ trợ validate trùng tên entity, thiếu key hoặc key không tồn tại trong source schema khi được dùng trong FeatureView.

### 2.3 EntityRelationship

EntityRelationship là metadata riêng để biểu diễn quan hệ giữa các entity. Đây là phần cần bổ sung rõ hơn so với proposal ban đầu.

Ví dụ khách hàng có nhiều hợp đồng:

```yaml
name: customer_has_contracts
left_entity: customer
right_entity: contract
relation_type: one_to_many
join_keys:
  - left_key: customer_id
    right_key: customer_id
temporal:
  valid_from: contract_start_date
  valid_to: contract_end_date
description: One customer can have multiple contracts over time.
```

Ý nghĩa:

- `Entity` định nghĩa object và key.
- `EntityRelationship` định nghĩa object này liên hệ với object kia như thế nào.
- `FeatureView` có thể dùng relationship để derive hoặc aggregate feature về đúng target entity.
- `FeatureSet` dùng relationship để validate feature từ nhiều FeatureView có join được với nhau không.

Phạm vi cần làm:

- Thêm model metadata cho relationship.
- Hỗ trợ relation type: `one_to_one`, `one_to_many`, `many_to_one`, `many_to_many`.
- Hỗ trợ join keys giữa hai entity.
- Hỗ trợ optional temporal validity: `valid_from`, `valid_to`, `event_time`.
- Hỗ trợ validate relationship path khi FeatureSet chọn feature từ nhiều FeatureView.
- Với quan hệ `one_to_many`, bắt buộc phải có aggregation nếu muốn đưa feature từ entity con về entity cha.

Kết quả mong muốn:

- Biểu diễn được customer - contract - service - device.
- Biết được feature nào join trực tiếp được và feature nào cần aggregate.
- Chuẩn bị nền tảng cho feature lineage và PIT join.

### 2.4 FeatureView

FeatureView là nhóm feature có cùng source, cùng entity/grain và cùng logic cập nhật. FeatureView không chỉ là container, mà còn là đơn vị để validate schema, materialize, theo dõi freshness và lineage.

Có hai loại FeatureView nên hỗ trợ:

```text
Direct FeatureView
- Feature được tạo trực tiếp ở entity chính.
- Ví dụ: contract_usage_7d_view, entity = contract.

Derived/Aggregated FeatureView
- Feature được tạo từ entity khác thông qua EntityRelationship.
- Ví dụ: customer_contract_agg_view, entity = customer, source_entity = contract, relationship = customer_has_contracts.
```

Ví dụ aggregated FeatureView:

```yaml
name: customer_contract_agg_view
entity: customer
source_entity: contract
source: customer_contract_source
relationship: customer_has_contracts
aggregation:
  group_by:
    - customer_id
  event_time: contract_start_date
features:
  - name: active_contract_count
    expression: count_if(contract_status = 'active')
  - name: total_contract_value
    expression: sum(contract_value)
  - name: latest_contract_value
    expression: latest(contract_value, order_by = contract_start_date)
```

Phạm vi cần làm:

- Chuẩn hóa metadata `FeatureView`.
- Bổ sung `entity`, `source`, `features`, `refresh_policy`, `freshness_policy`.
- Bổ sung `source_entity`, `relationship`, `aggregation` cho derived/aggregated FeatureView.
- Validate grain: FeatureSet target entity chỉ được chọn feature cùng entity hoặc feature đã aggregate về target entity.

### 2.5 Feature

Feature là từng biến cụ thể dùng cho phân tích, training hoặc serving. Feature nên nằm trong FeatureView để tránh catalog phẳng và để metadata được quản lý theo nhóm.

Metadata tối thiểu:

```yaml
name: total_traffic_gb_7d
dtype: float
description: Total internet traffic in the last 7 days.
source_columns:
  - traffic_gb
dependencies:
  - internet_usage_daily_source.traffic_gb
owner: data_team
```

#### Feature semantics and business metadata

Featcat cần bổ sung metadata nghiệp vụ cho feature để tránh việc feature chỉ được quản lý như một cột dữ liệu kỹ thuật. Metadata này giúp data scientist, ML engineer, business owner và reviewer hiểu feature đang đo cái gì, dùng trong ngữ cảnh nào, có rủi ro leakage không, và khi nào feature đủ điều kiện đưa vào model production.

Mỗi feature nên có các trường cơ bản:

```yaml
name: total_traffic_gb_7d
business_definition: Total internet traffic generated by a customer in the last 7 days.
entity_grain: customer_id
observation_time: inference_time
window: 7d
aggregation: sum(traffic_gb) grouped by customer_id over event_time
semantic_type: quantity
unit: GB
source_of_truth: internet_usage_daily_source
valid_condition: customer has at least one active internet contract during the observation window
missing_value_policy: treat missing as unknown; do not coerce to zero unless no usage record means zero by business rule
quality_expectation:
  nullable: false
  min: 0
  max: 10000
freshness_sla: 24h
leakage_risk: low
allowed_use_cases:
  - churn_prediction
  - usage_segmentation
business_domain: network
business_metric_name: weekly_customer_traffic
metric_domain: network_quality
lifecycle_stage: consume
metric_group: usage_quality
metric_level: customer
business_objective: detect customer experience degradation before churn
owner: data_team
lifecycle_status: validated
```

Ý nghĩa các field:

- `business_definition`: định nghĩa nghiệp vụ dễ hiểu, không chỉ mô tả tên column.
- `entity_grain`: grain kỹ thuật mà feature dùng để join/serving, ví dụ `customer_id`, `contract_id`, `service_id`, `device_id`.
- `observation_time`: thời điểm feature được tính phục vụ training/inference.
- `window`: cửa sổ thời gian nếu là feature dạng rolling hoặc historical, ví dụ `7d`, `30d`, `current_month`.
- `aggregation`: cách aggregate nếu feature được derive qua relationship one-to-many.
- `semantic_type`: loại ngữ nghĩa như `money`, `count`, `ratio`, `duration`, `category`, `status`.
- `unit`: đơn vị đo như `VND`, `GB`, `ms`, `days`, `minutes`.
- `source_of_truth`: nguồn dữ liệu chuẩn được dùng để tính feature.
- `valid_condition`: điều kiện nghiệp vụ để feature có ý nghĩa.
- `missing_value_policy`: cách hiểu và xử lý `null`, missing, zero hoặc `not_applicable`.
- `quality_expectation`: kỳ vọng chất lượng dữ liệu như min/max, nullable, accepted categories.
- `freshness_sla`: yêu cầu về độ mới của feature.
- `leakage_risk`: mức rủi ro data leakage, ví dụ `low`, `medium`, `high`.
- `allowed_use_cases`: các use case/model được phép dùng feature.
- `business_domain`: domain nghiệp vụ như `billing`, `network`, `contract`, `support`.
- `business_metric_name`: tên metric nghiệp vụ mà feature hỗ trợ, nếu có.
- `metric_domain`: domain trong customer metrics framework của công ty.
- `lifecycle_stage`: giai đoạn vòng đời khách hàng mà metric phục vụ.
- `metric_group`: nhóm metric con trong domain/stage.
- `metric_level`: cấp độ nghiệp vụ của metric trong framework.
- `business_objective`: mục tiêu nghiệp vụ mà metric hỗ trợ.
- `owner`: người hoặc team chịu trách nhiệm.
- `lifecycle_status`: trạng thái vòng đời như `draft`, `validated`, `production`, `deprecated`.

#### Business metric framework alignment

Featcat nên phân biệt rõ `Feature` và `BusinessMetric`/`MetricDefinition`:

- `Feature` là biến kỹ thuật/ML được tính từ `DataSource` hoặc `FeatureView`, có dtype, source columns, dependencies, grain phục vụ join/training/serving.
- `BusinessMetric` là metric nghiệp vụ được map tới một hoặc nhiều `Feature`, được tổ chức theo customer metrics framework của công ty để business user dễ tìm, review và governance.

Customer metrics taxonomy nên có các field:

- `metric_domain`: một trong `network_quality`, `device_intel`, `customer_experience`, `billing`, `service_ops`, `contact`, `customer_profile`.
- `lifecycle_stage`: một trong `consume`, `manage`, `leave`.
- `metric_group`: nhóm metric chi tiết trong domain/stage, ví dụ `signal_quality`, `payment_behavior`, `support_interaction`.
- `metric_level`: một trong `device`, `contract`, `customer`, `mixed`.
- `business_metric_name`: tên metric nghiệp vụ chuẩn.
- `business_objective`: mục tiêu nghiệp vụ, ví dụ giảm churn, phát hiện trải nghiệm xấu, ưu tiên chăm sóc khách hàng.

Cần phân biệt `entity_grain` và `metric_level`:

- `entity_grain` là grain kỹ thuật dùng cho join và serving, ví dụ `device_id`, `contract_id`, `customer_id`.
- `metric_level` là cấp độ nghiệp vụ trong customer metrics framework, ví dụ `device`, `contract`, `customer`, `mixed`.

Ví dụ cùng một metric bắt đầu từ dữ liệu device-level nhưng được roll up về customer-level:

```yaml
name: bad_signal_days_7d
entity_grain: customer_id
metric_level: customer
metric_domain: network_quality
lifecycle_stage: consume
metric_group: signal_quality
business_metric_name: bad_signal_days_7d
business_objective: identify customers with poor network experience
source_of_truth: device_signal_daily_source
aggregation: count_distinct(day where signal_quality = 'bad') from device -> service -> contract -> customer
```

Các ví dụ ISP/customer metrics nên hỗ trợ:

- `bad_signal_days_7d`: network quality metric, có thể bắt đầu từ device-level và aggregate lên contract/customer.
- `payment_delay_count_30d`: billing metric ở customer hoặc contract level.
- `downtime_minutes_7d`: network/service ops metric, thường roll up từ service/device lên contract/customer.
- `preferred_channel`: contact/customer experience metric ở customer level.
- `churn_basket_count`: leave-stage metric ở customer hoặc mixed level, cần kiểm tra leakage risk cẩn thận.

`BusinessMetric`/`MetricDefinition` là registry object tùy chọn nhưng nên được thiết kế sớm. Object này không thay thế `Feature`; nó là lớp mapping nghiệp vụ để gom, mô tả và tìm kiếm technical features theo customer metrics framework.

```yaml
name: network_quality.bad_signal_days_7d
business_metric_name: bad_signal_days_7d
business_definition: Number of days in the last 7 days where the customer had bad signal quality.
metric_domain: network_quality
lifecycle_stage: consume
metric_group: signal_quality
metric_level: customer
entity_grain: customer_id
mapped_features:
  - network_quality_customer_7d_view.bad_signal_days_7d
owner: network_analytics_team
lifecycle_status: validated
allowed_use_cases:
  - churn_prediction
  - proactive_care
```

Validation cho BusinessMetric nên có:

- `FeatureSet` vẫn validate `entity_grain` như hiện tại để đảm bảo join/training/serving đúng grain.
- `BusinessMetric` validate `metric_domain`, `lifecycle_stage`, `metric_level` và `mapped_features`.
- Nếu `metric_level` không tương ứng với `entity_grain`, phải có rollup hoặc aggregation rule rõ ràng.
- Metric hoặc feature có `leakage_risk=high` cần cảnh báo khi được dùng trong production FeatureSet.

Validation nên có:

- `entity_grain` phải khớp với entity của FeatureView hoặc grain sau aggregation.
- Feature được derive từ relationship one-to-many phải khai báo `aggregation`.
- Feature dạng rolling/historical nên có `window` và `observation_time`.
- `semantic_type=money` nên có `unit`; `semantic_type=duration` nên có đơn vị thời gian.
- `leakage_risk=high` cần cảnh báo khi add vào FeatureSet production.
- `allowed_use_cases` nên được kiểm tra khi FeatureSet khai báo use case/model.
- `lifecycle_status=deprecated` không nên được thêm mới vào FeatureSet nếu không có override.
- `quality_expectation` nên được dùng làm input cho monitoring và validation.
- Nếu feature khai báo `business_metric_name`, các field `metric_domain`, `lifecycle_stage`, `metric_level` nên hợp lệ theo taxonomy.
- Nếu `metric_level` không tương ứng với `entity_grain`, feature phải khai báo `aggregation` hoặc rollup path qua `EntityRelationship`.

Phạm vi cần làm:

- Chuẩn hóa metadata Feature.
- Thể hiện feature lấy từ source nào.
- Thể hiện feature phụ thuộc vào column hoặc feature nào.
- Bổ sung metadata nghiệp vụ và semantic metadata cho Feature.
- Cho phép Feature khai báo optional mapping tới customer metrics framework: `business_metric_name`, `metric_domain`, `lifecycle_stage`, `metric_group`, `metric_level`, `business_objective`.
- Validate grain, aggregation, semantic type, unit, leakage risk và lifecycle status ở mức registry.
- Validate taxonomy metric nếu Feature hoặc BusinessMetric có khai báo.
- Chuẩn bị lineage ở mức source column -> feature -> feature view -> feature set.
- Validate type, missing expression, missing source column, trùng tên feature trong cùng FeatureView.

### 2.6 FeatureSet

FeatureSet là tập feature được chọn cho một model hoặc use case cụ thể. FeatureSet không định nghĩa feature mới, mà reference các feature đã có trong FeatureView.

Ví dụ:

```yaml
name: churn_prediction_features_v1
target_entity: customer
features:
  - customer_profile_view.province
  - customer_contract_agg_view.active_contract_count
  - customer_usage_7d_view.total_traffic_gb_7d
  - customer_billing_30d_view.payment_delay_count_30d
```

Validation cần có:

- Tất cả feature phải tồn tại trong registry.
- Feature phải cùng target entity hoặc đã được aggregate về target entity.
- Không cho join trực tiếp feature ở cấp `contract` vào FeatureSet target `customer` nếu chưa có aggregation.
- Cảnh báo nếu feature freshness quá cũ hoặc source schema không còn khớp.

### 2.7 Feature Registry

Feature Registry là nơi lưu metadata của DataSource, Entity, EntityRelationship, FeatureView, Feature, BusinessMetric/MetricDefinition và FeatureSet.

Phạm vi cần làm:

- Lưu metadata registry.
- Lưu mapping từ BusinessMetric tới một hoặc nhiều Feature.
- Hỗ trợ list/search/describe.
- Hỗ trợ validate trước khi register.
- Chuẩn bị versioning cho feature definition.
- Chuẩn bị audit log cho thay đổi metadata.

API/CLI tối thiểu:

```text
featcat source list
featcat entity list
featcat relationship list
featcat feature-view list
featcat feature describe <feature_name>
featcat metric describe <metric_name>
featcat feature-set describe <feature_set_name>
featcat apply <config.yaml>
```

### 2.8 Python SDK

Python SDK giúp user define/register metadata bằng code thay vì chỉ dùng YAML hoặc UI.

Phạm vi cần làm:

- SDK khai báo DataSource.
- SDK khai báo Entity.
- SDK khai báo EntityRelationship.
- SDK khai báo FeatureView.
- SDK khai báo Feature.
- SDK khai báo BusinessMetric/MetricDefinition.
- SDK khai báo FeatureSet.
- SDK gọi API register/apply metadata.

Ví dụ mong muốn:

```python
customer = Entity(
    name="customer",
    primary_keys=["customer_id"],
)

contract = Entity(
    name="contract",
    primary_keys=["contract_id"],
    join_keys=["customer_id"],
)

customer_contract = EntityRelationship(
    name="customer_has_contracts",
    left_entity="customer",
    right_entity="contract",
    relation_type="one_to_many",
    join_keys=[JoinKey(left_key="customer_id", right_key="customer_id")],
)
```

Ví dụ SDK cho churn prediction:

```python
with FeatcatSDK() as sdk:
    sdk.register_data_source(
        DataSource(name="device_signal_daily", path="s3://lake/device_signal_daily.parquet")
    )
    sdk.register_entity(Entity(name="customer", primary_keys=["customer_id"], join_keys=["customer_id"]))
    sdk.register_entity(Entity(name="device", primary_keys=["device_id"], join_keys=["device_id", "customer_id"]))
    sdk.register_relationship(
        EntityRelationship(
            name="customer_has_devices",
            left_entity="customer",
            right_entity="device",
            relation_type="one_to_many",
            join_keys=[JoinKey(left_key="customer_id", right_key="customer_id")],
        )
    )
    sdk.register_feature(
        Feature(
            name="device_signal_daily.bad_signal_days_7d",
            data_source_id="...",
            column_name="bad_signal_days_7d",
            entity_grain="device_id",
        )
    )
    sdk.register_feature_view(
        FeatureView(
            name="network_quality_customer_7d_view",
            entity="customer",
            source_name="device_signal_daily",
            source_entity="device",
            relationship="customer_has_devices",
            aggregation="count_distinct(day where signal_quality = 'bad') by customer_id",
            feature_names=["device_signal_daily.bad_signal_days_7d"],
        )
    )
    sdk.register_business_metric(
        BusinessMetric(
            name="network_quality.bad_signal_days_7d",
            business_metric_name="bad_signal_days_7d",
            metric_domain="network_quality",
            lifecycle_stage="consume",
            metric_level="customer",
            entity_grain="customer_id",
            aggregation_rule="roll up device signal days to customer",
            mapped_features=["network_quality_customer_7d_view.bad_signal_days_7d"],
        )
    )
    sdk.register_feature_set(
        FeatureSet(
            name="churn_prediction_features_v1",
            target_entity="customer",
            feature_names=["device_signal_daily.bad_signal_days_7d"],
            rollup_rules={"device_signal_daily.bad_signal_days_7d": "roll up to customer"},
        )
    )
```

### 2.9 Online Store

Online Store phục vụ truy vấn feature theo entity key cho inference.

Phạm vi cần làm:

- Thiết kế interface cho online store.
- Chọn implementation ban đầu: PostgreSQL trước để giảm dependency, Redis có thể để option sau.
- Thêm API lấy online feature theo entity key.
- Chuẩn bị flow materialize từ offline source sang online store.
- Lưu metadata freshness và materialization timestamp.

API mong muốn:

```text
GET /online-features?feature_set=churn_prediction_features_v1&entity_key=customer_id:123
```

### 2.10 Materialization

Materialization là flow đưa feature từ offline source/FeatureView sang online store.

Phạm vi cần làm:

- Thiết kế job materialize theo FeatureView hoặc FeatureSet.
- Hỗ trợ incremental materialization ở mức đơn giản nếu source có event time/updated_at.
- Tracking job status: pending, running, success, failed.
- Tracking job runtime, rows processed, freshness timestamp, error message.
- Hỗ trợ kiểm tra freshness cơ bản.

### 2.11 CLI, examples và docs

Phạm vi cần làm:

- CLI cơ bản cho list, describe, apply config.
- Example dùng MinIO + S3 source + Python SDK.
- Example register source -> entity -> relationship -> feature view -> feature set.
- Example query metadata registry.
- Docs ngắn cho cách chạy local.

### 2.12 UI

UI nên được điều chỉnh để workflow rõ hơn thay vì chỉ hiển thị feature rời rạc.

Workflow đề xuất:

```text
Sources -> Entities -> Relationships -> FeatureViews -> Features -> FeatureSets -> Materialization
```

UI vẫn giữ workflow kỹ thuật trên, nhưng cần hỗ trợ thêm business-facing metrics view để người dùng tìm feature theo metric framework thay vì chỉ theo tên column/feature.

Phạm vi cần làm:

- Layout lại navigation theo workflow trên.
- Thêm BusinessMetric detail page hoặc metric mapping view để xem metric map tới feature nào.
- Thêm filter/search theo `metric_domain`, `lifecycle_stage`, `metric_level`, `business_objective` và `owner`.
- Thêm trang Relationship để xem quan hệ entity.
- Thêm view lineage đơn giản cho FeatureView/Feature.
- Thêm trang FeatureSet validation result.
- Thêm trạng thái freshness/materialization nếu đã có backend support.

## 3. Ví dụ tổ chức feature cho use case churn prediction

Use case: dự đoán churn cho khách hàng Internet cố định.

DataSource:

- `customer_contract_source`
- `internet_usage_daily_source`
- `network_quality_daily_source`
- `billing_payment_source`
- `customer_support_ticket_source`

Entity:

- `customer`, key = `customer_id`
- `contract`, key = `contract_id`, join key = `customer_id`
- `service`, key = `service_id`, join key = `contract_id`
- `device`, key = `device_id`, join key = `contract_id` hoặc `service_id`

EntityRelationship:

- `customer_has_contracts`: customer one-to-many contract
- `contract_has_services`: contract one-to-many service
- `service_has_devices`: service one-to-many device

FeatureView:

- `customer_profile_view`, entity = customer
- `customer_contract_agg_view`, entity = customer, source_entity = contract, relationship = customer_has_contracts
- `customer_usage_7d_view`, entity = customer hoặc contract tùy grain dữ liệu đã aggregate
- `network_quality_7d_view`, entity = service/device hoặc aggregate về customer/contract
- `billing_30d_view`, entity = customer hoặc contract
- `support_ticket_30d_view`, entity = customer

BusinessMetric/MetricDefinition:

```yaml
name: network_quality.bad_signal_days_7d
business_metric_name: bad_signal_days_7d
metric_domain: network_quality
lifecycle_stage: consume
metric_group: signal_quality
metric_level: customer
entity_grain: customer_id
business_objective: detect poor network experience before churn
mapped_features:
  - network_quality_customer_7d_view.bad_signal_days_7d
```

Ví dụ rollup từ device-level data lên customer-level metric:

```text
device_signal_daily_source
-> device_signal_7d_view.bad_signal_days_7d, entity_grain = device_id, metric_level = device
-> EntityRelationship service_has_devices + contract_has_services + customer_has_contracts
-> network_quality_customer_7d_view.bad_signal_days_7d, entity_grain = customer_id, metric_level = customer
```

Các metric ví dụ:

- `bad_signal_days_7d`: số ngày tín hiệu xấu trong 7 ngày, domain `network_quality`, stage `consume`.
- `payment_delay_count_30d`: số lần trễ thanh toán trong 30 ngày, domain `billing`, stage `manage`.
- `downtime_minutes_7d`: tổng phút mất kết nối trong 7 ngày, domain `service_ops` hoặc `network_quality`, stage `consume`.
- `preferred_channel`: kênh liên hệ ưu tiên, domain `contact`, stage `manage`.
- `churn_basket_count`: số tín hiệu/rổ hành vi liên quan churn, domain `customer_experience`, stage `leave`, cần cảnh báo leakage risk.

FeatureSet:

```yaml
name: churn_prediction_features_v1
target_entity: customer
features:
  - customer_profile_view.province
  - customer_profile_view.customer_segment
  - customer_contract_agg_view.active_contract_count
  - customer_contract_agg_view.latest_package_price
  - customer_usage_7d_view.total_traffic_gb_7d
  - network_quality_customer_7d_view.bad_signal_days_7d
  - network_quality_customer_7d_view.downtime_minutes_7d
  - billing_30d_view.payment_delay_count_30d
  - contact_customer_view.preferred_channel
  - customer_experience_leave_view.churn_basket_count
  - support_ticket_30d_view.complaint_count_30d
```

Ghi chú quan trọng: nếu feature gốc nằm ở cấp `contract`, `service` hoặc `device`, nhưng model target là `customer`, thì phải tạo aggregated FeatureView về `customer` trước. Không join trực tiếp feature cấp thấp hơn vào FeatureSet cấp customer.

## 4. Sprint plan

### Sprint 0 - Chốt thiết kế metadata và migration scope

Mục tiêu: thống nhất domain model trước khi code sâu.

Tasks:

- Review lại các model hiện tại trong Featcat: DataSource, Entity, FeatureView, Feature, FeatureSet nếu đã có.
- Chốt naming: dùng `FeatureView` thay vì `FeatureGroup` nếu muốn gần với feature store terminology.
- Bổ sung model `EntityRelationship`.
- Bổ sung model tùy chọn `BusinessMetric`/`MetricDefinition`.
- Chốt metadata nghiệp vụ bắt buộc/tùy chọn cho Feature.
- Chốt taxonomy customer metrics: metric domain, lifecycle stage, metric group, metric level, business metric name và business objective.
- Chốt validation rule cho grain và relationship.
- Chốt validation rule cho semantic metadata: unit, window, aggregation, leakage risk, allowed use cases và lifecycle status.
- Chốt validation rule cho BusinessMetric và mapped features.
- Viết migration plan nếu schema registry hiện tại cần đổi.
- Viết docs ngắn mô tả domain model mới.

Acceptance criteria:

- Có tài liệu domain model mới.
- Có schema metadata draft cho 7 object: DataSource, Entity, EntityRelationship, FeatureView, Feature, BusinessMetric/MetricDefinition, FeatureSet.
- Có schema metadata draft cho feature semantics và business metadata.
- Có schema metadata draft cho customer metrics taxonomy.
- Có danh sách breaking changes nếu cần.

### Sprint 1 - Registry core và relationship metadata

Mục tiêu: registry lưu và validate được metadata lõi.

Tasks:

- Implement schema/model cho EntityRelationship.
- Implement schema/model tùy chọn cho BusinessMetric/MetricDefinition.
- Cập nhật registry để lưu DataSource, Entity, EntityRelationship, FeatureView, Feature, BusinessMetric/MetricDefinition, FeatureSet.
- Cập nhật Feature schema để lưu business metadata: definition, grain, observation time, window, aggregation, semantic type, unit, source of truth, valid condition, missing policy, quality expectation, freshness SLA, leakage risk, allowed use cases, domain, owner và lifecycle status.
- Cập nhật Feature schema để optional khai báo `business_metric_name`, `metric_domain`, `lifecycle_stage`, `metric_group`, `metric_level`, `business_objective`.
- Cập nhật BusinessMetric schema để lưu `name`, `business_metric_name`, `business_definition`, `metric_domain`, `lifecycle_stage`, `metric_group`, `metric_level`, `entity_grain`, `mapped_features`, `owner`, `lifecycle_status`, `allowed_use_cases`.
- Thêm validate cơ bản trước khi register.
- Thêm validate semantic metadata cơ bản trước khi register feature.
- Thêm validate BusinessMetric: taxonomy hợp lệ, mapped features tồn tại, metric level không tương ứng với entity grain phải có aggregation/rollup rule.
- Thêm API list/search/describe cho các object chính.
- Thêm test cho relationship one-to-many customer-contract.
- Thêm test validate không cho FeatureSet target customer chọn feature contract trực tiếp nếu chưa aggregate.
- Thêm test validate feature missing unit/window/aggregation trong các case bắt buộc.
- Thêm test validate BusinessMetric mapped features và high leakage warning khi dùng trong production FeatureSet.

Acceptance criteria:

- Register được customer, contract và customer_has_contracts.
- Register được FeatureView direct và aggregated.
- Register được feature có business metadata đầy đủ.
- Register được BusinessMetric map tới một hoặc nhiều Feature.
- Describe feature hiển thị được business definition, grain, semantic type, unit, freshness SLA, leakage risk và lifecycle status.
- Describe metric hiển thị được domain, lifecycle stage, metric level, objective và mapped features.
- Describe được lineage đơn giản từ feature về source column.
- Test registry và validation pass.

### Sprint 2 - S3/MinIO source và local dev flow

Mục tiêu: Featcat đọc được offline source từ S3-compatible storage.

Tasks:

- Implement S3-compatible DataSource abstraction.
- Thêm MinIO vào docker compose hoặc local dev setup.
- Thêm config cho bucket, prefix/path, endpoint, credential, file format.
- Implement schema scan cho Parquet/CSV ở mức tối thiểu.
- Validate source và source schema khi register FeatureView.
- Viết example MinIO source.

Acceptance criteria:

- Chạy local được MinIO.
- Upload sample data và register S3/MinIO source thành công.
- FeatureView có thể reference source đó.
- Schema validation phát hiện được missing column.

### Sprint 3 - Python SDK và CLI

Mục tiêu: user có thể thao tác với Featcat bằng code và command line.

Tasks:

- Implement SDK classes: DataSource, Entity, EntityRelationship, FeatureView, Feature, BusinessMetric, FeatureSet.
- Implement SDK client gọi API register/list/describe.
- Implement CLI `apply`, `list`, `describe`.
- Thêm example SDK cho churn prediction.
- Thêm docs local quickstart.

Acceptance criteria:

- User có thể register full flow bằng Python SDK.
- User có thể apply YAML config bằng CLI.
- CLI list/describe hiển thị được source, entity, relationship, feature view, business metric và feature set.

### Sprint 4 - Online store interface và materialization MVP

Mục tiêu: có flow đầu tiên từ offline feature sang online feature serving.

Tasks:

- Thiết kế interface OnlineStore.
- Implement PostgreSQL online store MVP.
- Thêm API get online feature theo entity key.
- Implement materialization job theo FeatureView.
- Lưu job status, runtime, rows processed, freshness timestamp.
- Thêm freshness check cơ bản.

Acceptance criteria:

- Materialize được một FeatureView vào online store.
- Query online feature theo entity key thành công.
- Có job status và freshness timestamp.
- Có test cho materialization success/fail.

### Sprint 5 - UI workflow và lineage view

Mục tiêu: UI phản ánh đúng workflow mới của Featcat.

Tasks:

- Điều chỉnh navigation: Sources -> Entities -> Relationships -> FeatureViews -> Features -> FeatureSets -> Materialization.
- Thêm trang Relationship list/detail.
- Thêm FeatureView detail hiển thị source, entity, features, dependencies.
- Thêm FeatureSet validation result.
- Thêm lineage view đơn giản: DataSource -> FeatureView -> Feature -> BusinessMetric -> FeatureSet.
- Thêm materialization/freshness status nếu backend đã có.

Acceptance criteria:

- Người dùng nhìn được workflow end-to-end trên UI.
- Relationship không còn bị ẩn trong Entity hoặc Feature.
- FeatureSet hiển thị được target entity và validation status.
- Người dùng business tìm được metric/feature theo business domain, lifecycle stage và metric level.
- Lineage cơ bản đọc được từ UI.

## 5. Thứ tự ưu tiên đề xuất

Ưu tiên cao nhất là metadata và registry, vì nếu chưa chốt domain model thì S3, SDK, online store và UI đều dễ phải sửa lại.

Thứ tự đề xuất:

1. EntityRelationship, BusinessMetric và registry validation.
2. DataSource S3/MinIO.
3. Python SDK + CLI.
4. Online store + materialization.
5. UI workflow + lineage.

## 6. Rủi ro và lưu ý

### Rủi ro 1: Entity quá rộng

Nếu Entity vừa định nghĩa key, vừa định nghĩa relationship, vừa chứa logic join, model sẽ bị phình và khó maintain. Nên giữ Entity nhỏ, relationship tách riêng.

### Rủi ro 2: Join sai grain

Ví dụ FeatureSet target `customer` nhưng chọn feature từ `contract` trực tiếp sẽ làm duplicate row nếu một customer có nhiều contract. Cần validate bắt buộc aggregation trong case one-to-many.

### Rủi ro 3: Làm online store quá sớm

Online store phụ thuộc vào registry, entity key, materialization và freshness. Nếu làm online store trước khi metadata ổn định, khả năng phải refactor cao.

### Rủi ro 4: UI đi trước backend

UI nên đi sau khi registry API có shape ổn định. Nếu không, UI sẽ phải đổi nhiều lần.

## 7. Output sau khi hoàn thành

Sau các sprint trên, Featcat nên có các output chính:

- Registry lưu được source, entity, relationship, feature view, feature, business metric và feature set.
- Registry lưu được BusinessMetric/MetricDefinition và mapping từ metric nghiệp vụ tới technical features.
- Metadata thể hiện được relationship customer-contract-service-device.
- Featcat map được technical features vào customer metrics framework của công ty.
- User search được feature/metric theo business domain, lifecycle stage và metric level.
- FeatureSet validate được target entity và relationship path.
- S3/MinIO source chạy được local.
- Python SDK và CLI dùng được cho flow register/query.
- Materialization MVP đưa feature sang online store.
- UI thể hiện workflow end-to-end và lineage cơ bản.
