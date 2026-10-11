# SLO 告警生命周期

`evaluate-slo` 输出的是单次负载实验判定；`reconcile-alerts` 将连续判定合并为可持续维护的事件状态。相同 `alert_id` 持续出现时只更新一个打开事件并增加出现次数，不重复创建事件。后续完整报告不再包含该告警时，事件转为 `RESOLVED`；恢复后再次出现会创建新的事件编号。

```powershell
./scripts/reconcile-slo-incidents.ps1 `
  -SloReport build/load-experiment/slo-report.json `
  -ObservedAt 2026-10-11T09:00:00Z
```

状态文件默认写入 `build/load-experiment/slo-incidents.json`，包含策略版本、打开与已恢复数量、首次/最近出现时间、出现次数和最新阈值对比。事件编号由告警编号与首次出现时间确定，不保存订单、用户或原始运行日志。

通知计划根据 `config/incident-routing.json` 把严重级别映射到逻辑渠道：

```powershell
./scripts/plan-incident-notifications.ps1
```

Outbox 为打开与恢复动作生成稳定 `event_id`。调用方把已成功投递的编号写入 `delivery-ledger.json` 后，相同状态再次生成计划时不会重复返回这些事件。当前实现只生成待发送事件，不直接连接短信、邮件或企业消息平台。

调用方必须提供带时区的 `ObservedAt`。早于现有事件最近时间的输入会被拒绝，避免乱序报告覆盖较新的事件状态。该模块负责事件状态聚合，不负责通知渠道、值班升级或生产事故管理平台同步。
