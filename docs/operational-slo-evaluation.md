# 压测 SLO 判定与告警

压测证据汇总完成后，SLO 判定器根据 `config/operational-slos.json` 对每个负载档位执行四项检查：端到端吞吐率、最大反压比例、失败 Checkpoint 数和作业状态。策略支持公共阈值及按档位覆盖，高负载档位可使用单独的容量边界。

输出报告包含稳定的规则编号、观测值、比较运算符、阈值、严重度和告警编号。任一检查失败时，报告状态为 `ALERT`；输入证据未完成、档位重复或字段类型错误时直接拒绝判定，避免把缺失证据解释为通过。

```powershell
./scripts/evaluate-load-slo.ps1 `
  -Summary build/load-experiment/summary.json `
  -Output build/load-experiment/slo-report.json
```

默认策略用于本项目可复现环境中的回归门禁，不代表生产容量认证。生产阈值需要结合部署资源、业务峰值、容错预算和持续观测重新审批。
