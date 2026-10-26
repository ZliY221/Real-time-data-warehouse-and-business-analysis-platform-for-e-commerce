# 用户使用指南

适用版本：`v4.5.0`

本指南随项目版本同步更新，介绍当前版本可直接使用的入口、功能和输出位置。首次使用建议先阅读仓库首页的项目简介、架构和常用入口，再按本指南完成运行。

## 1. 环境要求

- Python 3.11 或更高版本
- 本地离线流程无需 Docker
- 完整实时链路需要 Docker、JDK 17 和 Maven

环境按离线便携、查询看板和实时集成三档独立维护。可先运行 `python scripts/project_doctor.py --profile warehouse` 检查最低依赖；完整选择说明见[运行环境分层](runtime-environments.md)。启动器会隔离项目依赖，并使用 UTF-8 输出适配中文路径。

## 2. 最快启动

在仓库根目录执行：

```powershell
python scripts/bootstrap.py
```

启动器会创建隔离运行时，生成订单事件，校验事件契约，构建 DuckDB 离线数仓并导出经营报告。主要输出位于 `build/quickstart/`。

## 3. 启动经营看板

商品告警流 `/api/v2/products/alerts` 将超过配置变化率阈值的 SKU 转换为中、高等级经营提醒，并保留方向、变化率和触发原因；用户可按经营场景调整阈值。

`/api/v2/products/contribution` 在当前筛选窗口内计算每个品类或 SKU 的 GMV 与订单贡献率，可用于活动期商品结构分析和经营下钻。

商品趋势接口 `/api/v2/products/trends` 会自动取等长的上一周期作为基准，按品类或 SKU 返回 GMV 增减、变化率与趋势方向，结果按绝对变化排序，便于快速定位主要波动。

界面预览模式使用固定演示数据，不依赖 ClickHouse：

```powershell
./scripts/dashboard-preview.ps1
```

浏览器访问 `http://127.0.0.1:8000/dashboard`。真实链路启动后使用：

```powershell
./scripts/api-up.ps1
```

看板支持时间、地区和渠道筛选，并展示 GMV、订单量、客单价、分钟趋势、商品分析、异常侧流和质量历史。v2.10.0 延续电商经营指挥台版型：顶部横向导航可直接定位周期对比、地区渠道、商品分析、链路健康和质量诊断；经营摘要使用非对称 Bento 卡片，玫红、橙色、青绿、蓝色和紫色分别承载收入、订单、客户、维度与链路状态，移动端自动改为单列。

“商品分析”使用订单明细中的 SKU、品类、数量与行金额，由 Flink 按事件时间分钟窗口实时聚合后写入 ClickHouse。页面可以切换“按品类”和“按 SKU”两种口径，并可选择单一品类缩小范围；柱状图与明细表同步展示 GMV、订单数和销量。预览模式内置固定商品数据，可在没有 Kafka、Flink 和 ClickHouse 时检查完整交互。

“经营周期对比”提供上一等长时段、昨日同期和上周同期三种基准，并展示订单量、GMV 和客单价变化率。例如选择 10:00 至 12:00，“上一等长时段”使用 08:00 至 10:00，“昨日同期”使用前一天 10:00 至 12:00。地区和渠道条件会同时应用于两个区间。基准值为零时显示“暂无基准”，避免把无法计算的增长率误写成零。保存经营视图时会同时保存所选对比基准。

“变化贡献”可以切换按地区或按渠道拆解 GMV 差额。系统合并当前与基准时段出现的维度，按变化绝对值从高到低展示前五项；正值表示增长来源，负值表示下降来源。异常、无穷大或无法转换的 GMV 值会按零处理，避免贡献排序和金额展示出现非数值。点击任意贡献项会把对应地区或渠道应用为筛选条件，并刷新 KPI、周期对比、趋势和明细，实现从差异发现到单维度分析的连续下钻。当前贡献项会高亮，并在列表下方显示下钻维度和名称；点击“清除当前下钻”只移除当前贡献维度筛选，保留另一维度及时间条件。所选贡献维度会随经营视图保存。

“自动刷新”默认每 5 秒更新一次。可以切换为 15 秒、30 秒或关闭；使用快捷时间范围时，刷新会自动把查询窗口推进到当前时间。切换到其他浏览器标签页后自动暂停请求，返回页面时立即补充一次最新数据。

在“经营视图”区域输入名称并点击“保存视图”，可保存当前快捷时间范围或自定义时间、地区、渠道以及自动刷新频率。选择视图后立即应用并刷新数据；不再使用的视图可以删除。视图保存在当前浏览器中，不会写入业务数据库。

需要与其他使用者共享当前分析上下文时，可先填写交接主题，再点击“复制分享链接”。新版链接把签发时间、交接主题、开始时间、结束时间、地区、渠道、对比基准、贡献维度和自动刷新间隔写入链接；接收者打开后会直接恢复同一经营视图。分享参数会先经过时间范围和枚举值校验，非法、不完整或签发时间异常的链接不会覆盖默认看板状态。生成链接时当前页面地址也会同步更新，便于刷新后继续使用。

链接生成后，页面状态区会显示时间范围、地区/渠道范围和对比基准的一句话摘要，便于复制前快速核对分享内容。接收者打开链接时会看到统一交接摘要，其中包含交接主题、视图指纹、签发时长和剩余有效时间。链接健康状态统一分为 `HEALTHY`、`STALE`、`RENEW_SOON` 和 `EXPIRED`，其中临近过期优先于链接老化提示。状态区会进一步显示继续分析、核对时间范围、续期链接或申请新链接等建议动作，并以“核对指纹—执行建议—记录交接”的顺序生成检查清单。指纹校验成功会自动计入完成步骤，`dashboardShareChecklistProgress` 可继续计算总步骤、完成率和剩余动作，并拒绝不属于当前清单的步骤。`dashboardShareHandoffReadiness` 将当前状态归纳为 `READY`、`ACTION_REQUIRED`、`BLOCKED` 或 `NOT_APPLICABLE`，同时给出需要继续处理的动作。

分享链接自生成时间起有效 7 天。生成成功时页面会直接显示剩余有效小时数；剩余不足 24 小时会被识别为即将过期。对仍有效的链接可点击“续期当前链接”，系统会保留筛选、对比、刷新和交接主题，并重新签发 7 天有效期。打开无法使用的链接时，页面会区分已过期、版本不支持和参数不完整三种情况，并回退到默认经营视图，避免长期流传的静态时间窗口被误认为最新数据。

打开有效分享链接后，页面会移除未支持的查询参数，并按固定顺序重写地址。经营筛选之外的参数不会继续出现在二次复制的链接中。

每个规范化经营视图会生成 `VIEW-` 开头的 8 位十六进制指纹，并显示在链接生成提示中。交接双方可以对照指纹确认筛选、对比和有效期参数是否完全一致；指纹仅用于一致性核对，不代表权限凭据。

刷新区域会显示下一次更新倒计时。“暂停实时刷新”按钮可临时停止自动请求，再次点击会恢复暂停前的刷新间隔，适合查看图表局部或核对某一时点的数据。

“链路健康与影响范围”区域会自动读取资产健康汇总，展示监控资产数、异常资产数、责任团队、处理延迟以及可能受影响的下游服务。资产按处置优先级排列：无数据状态优先于延迟状态，同时结合延迟压力和下游影响数量计算分值。可按健康状态与责任团队组合筛选资产表，表格上方会显示当前结果数和监控总数。

## 4. 数据资产运维

资源建议接口 `/api/v2/operations/resource-plan` 根据商品查询规模与当前告警数返回 `NORMAL`、`BALANCED` 或 `PROTECT` 模式，并给出最小刷新间隔和并发查询上限，防止高峰期看板轮询反向挤压实时链路。

- `GET /api/v1/operations/assets`：查看资产责任团队与上下游关系。
- `GET /api/v1/operations/assets/health`：查看全部受监控资产的健康汇总、`priority_rank`、`priority_score` 与受影响下游。
- `GET /api/v1/operations/assets/{asset_id}/freshness`：查看单个资产的新鲜度、延迟和影响范围。

可以传入 `evaluated_at` UTC 时间复现某一时点的健康判定。

## 5. 完整实时链路

```powershell
docker compose up -d
./scripts/flink-up.ps1
./scripts/submit-flink-job.ps1
./scripts/api-up.ps1
```

实时链路从 Kafka 读取订单事件，经 Flink 完成事件时间计算、去重和分钟聚合，再将结果写入 ClickHouse。接口文档位于 `http://127.0.0.1:8000/docs`。

商品查询接口为 `GET /api/v1/products/breakdown`，参数包括 `start`、`end`、`dimension=category|sku`、`category` 和 `limit`。实时订单消息的 `payload.items` 必须为数组，每一项包含 `sku_id`、`category`、`quantity`、`unit_price` 与 `line_amount`。

## 6. 工程验证

```powershell
./scripts/test-all.ps1
```

统一入口会检查 Python 数据处理、质量门禁、离线数仓、接口与看板、Flink Java 模块以及仓库发布内容。Windows 会优先识别 `py` 启动器，并自动跳过无效的应用商店占位命令。

## 7. 常见问题

- 端口占用：通过脚本的 `-Port` 参数改用其他端口。
- ClickHouse 不可用：先检查 `docker compose ps`，再核对 `CLICKHOUSE_HTTP_URL`。
- 本地 Python 依赖冲突：重新执行 `python scripts/bootstrap.py --refresh`。
- 看板显示预览提示：当前连接的是演示数据入口，不代表实时基础设施已启动。

## 8. 数据与运行边界

`GET /api/v3/operations/command-center` 汇总当前窗口的商品数量、成交额、前三贡献商品、趋势告警与经营状态。运营人员可用这一入口快速判断是否需要下钻，再访问商品趋势和异常明细接口。

`GET /api/v3/operations/campaign-pacing?current_gmv=400&target_gmv=1000&elapsed_ratio=0.6` 将实时成交进度与活动时间进度比较，返回领先、正常或落后状态以及进度差值。

`GET /api/v3/operations/inventory-signal?available_units=20&demand_per_hour=10&replenishment_hours=5` 根据库存、实时需求速度和补货周期估算库存覆盖小时数，返回健康、待补货或缺货风险状态。

`GET /api/v3/operations/briefing` 接收当前商品告警数、活动进度和库存状态，生成 P0 至 P3 的行动清单。缺货风险优先于活动落后和普通商品波动；没有风险时提示继续观察。

`GET /api/v3/operations/conversion-funnel?views=1000&carts=200&orders=100` 返回浏览到加购、加购到下单的转化率及主要流失阶段。输入必须满足浏览数不少于加购数、加购数不少于订单数。

`GET /api/v3/operations/alert-acknowledgement?alert_count=5&acknowledged_count=2&owner=commerce-oncall` 返回负责人、已确认和剩余告警数量，用于页面显示处置进度。

`GET /api/v3/operations/campaign-guardrail` 在活动发布前检查折扣比例、库存风险和活动进度。存在高折扣、缺货风险或落后情况下继续加大折扣时返回 `BLOCKED` 及具体原因。

`GET /api/v3/operations/shift-handoff` 将未确认商品告警、活动进度和库存状态整理成换班行动清单。交接人员可按返回顺序继续处理，不需要重新组合多个页面信息。

仓库内样例数据均为合成数据。运行产物写入 `build/`，不应将业务凭据、个人数据或生产连接信息提交到仓库。

## v3.8.0 促销毛利保护

调用 `GET /api/v3/operations/promotion-margin`，传入原价 `selling_price`、单位成本 `unit_cost`、折扣率 `discount_rate`，并可加入运费补贴 `shipping_subsidy`、预期退货率 `expected_return_rate` 和最低毛利率 `minimum_margin_rate`。接口返回折后价、预期实际收入、贡献毛利、毛利率以及最大安全折扣率。

`READY` 表示预计毛利高于保护线，`REVIEW` 表示接近保护线，`BLOCKED` 表示预计亏损或低于最低毛利要求。该结果用于活动上线前的经营复核，不替代财务结算，也不直接修改商品价格。

## v3.9.0 退货处理容量预测

调用 `GET /api/v3/operations/return-capacity`，传入订单量、当前退货请求、已处理数量、历史积压、每小时处理能力和班次时长。接口会计算实时退货率、班次可用容量、预计剩余积压和建议补充的小时处理能力。`RETURN_SURGE` 表示退货比例异常但现有产能可消化，`CAPACITY_GAP` 表示普通积压超出容量，`SURGE_CAPACITY_GAP` 表示退货激增且产能不足，应同时排查商品质量并调整逆向物流班次。

## v3.10.0 履约承诺风险预测

调用 `GET /api/v3/operations/fulfillment-promise`，传入今日应发订单、已发订单、待打包订单、每小时打包速度、承运商剩余容量和距离截单时间。接口返回预计可发货数量、承诺缺口以及 `PACKING`、`CARRIER`、`PACKING_AND_CARRIER` 或 `ORDER_READINESS` 瓶颈。`CUTOFF_RISK` 表示距离截单不足一小时且仍存在缺口，应优先调整波次或承运资源；接口只提供经营判断，不会自动更改订单承诺。

## v4.0.0 多节点履约分配

调用 `POST /api/v4/operations/fulfillment-allocation`，提交待分配订单总数及各履约节点的可用库存、每小时打包速度、承运容量和距离截单时间。系统先计算每个节点的安全履约能力，再按能力从高到低分配订单，并在 `constraints` 中标明库存、打包或承运限制。`ALLOCATED` 表示全部订单均有安全去向，`PARTIAL` 表示仍有未分配订单，`BLOCKED` 表示当前节点无法接单。接口返回 `dispatch_started=false`，不会自动向仓库下发任务。

## v4.1.0 库存再平衡

调用 `POST /api/v4/operations/inventory-rebalancing`，提交各履约节点的可用库存、预测需求、安全库存、最大调出量和最大调入量。系统只将满足需求和安全库存后的剩余库存视为可调出量，优先补充缺口更大的节点，并同时遵守两端容量限制。`BALANCED` 表示计划可消除全部预测缺口，`PARTIAL` 表示调拨后仍有缺口，`GAP` 表示当前没有可行调拨来源，`NO_TRANSFER_NEEDED` 表示各节点已满足需求。`transfer_started=false` 表示接口不会自动生成仓间任务。

## v4.2.0 拆单合并窗口

调用 `POST /api/v4/operations/shipment-consolidation`，提交允许等待的最长分钟数，以及每个订单的商品总数、当前可用商品数、下一件商品预计到齐时间、承运截单剩余时间和打包耗时。接口以“截单剩余时间减打包耗时”计算安全等待窗口：可在用户设定窗口内齐货时返回 `CONSOLIDATE`；等待会影响截单时返回 `SHIP_AVAILABLE_NOW`；全部商品已齐返回 `SHIP_COMPLETE`；尚无可发商品返回 `HOLD_FOR_STOCK`。`packages_avoided` 用于衡量建议收益，`shipment_changes_started=false` 表示结果不会自动修改订单或仓库任务。

## v4.3.0 多工位打包波次排程

调用 `POST /api/v4/operations/packing-wave-plan`，提交可用打包工位数量，以及每个订单的打包耗时、距承运截单的分钟数和业务优先级。系统先处理截单时间更早的订单；截单时间相同时优先处理高优先级订单，并始终分配当前最早空闲的工位。每项结果包含工位、计划开始与完成时间、截单余量和 `ON_TIME` 或 `AT_RISK` 状态。`packing_tasks_dispatched=false` 表示排程只用于班次复核，不会自动向仓内系统下发任务。

## v4.4.0 承运交接时隙预约

调用 `POST /api/v4/operations/carrier-handoff`，提交货件的就绪分钟、交付截点和业务优先级，以及各承运交接时隙的时间与容量。系统优先处理高优先级、截点更早的货件，并为其选择不早于就绪时间且不晚于交付截点的最早可用时隙。结果以 `RESERVED` 或 `UNASSIGNED` 标明预约状态，并返回各时隙剩余容量；`carrier_booking_started=false` 表示接口只生成内部复核计划，不会自动向承运商提交预约。

## v4.5.0 履约操作旅程演练

调用 `POST /api/v4/operations/operator-rehearsal`，一次提交恰好 100 条履约操作旅程。每条记录包含数据延迟、库存状态、打包产能、承运时隙、截单剩余时间和优先级。系统依次检查数据新鲜度、库存、打包、承运与截单风险，并返回 `primary_action`、三步 `steps`、中文 `message` 和人工确认要求。结果按优先级与截单时间排序，方便值班人员先处理紧急订单；`unresolved_count=0` 表示所有场景均有明确路径，`warehouse_commands_started=false` 表示不会自动下发仓库或承运指令。
