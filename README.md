# 信贷产品设计与定价 Skill

这是一个去案例化、配置驱动且可审计的 Codex Skill，用于设计区域化信贷产品参数，并构建单笔及生命周期定价模型。

## 核心能力

- 支持等额本息、等额本金、等本等息和到期还本。
- 建模提前结清及 0+/30+/90+ Vintage 曲线。
- 计算企业逐期现金流、毛利润、NPV、ROI、RAROC 和生命周期 LTV。
- 分别计算搭售产品实际购买者和未购买者的借款人 IRR 与配置化管理 APR。
- 保留余额递推、公式轨迹、输入来源和自动对账结果。
- 将地域政策、税务口径、观察期、风险映射及决策阈值保留为项目配置。

## 目录

- `design-credit-product/SKILL.md`：Skill 入口和工作流。
- `design-credit-product/references/`：输入协议、产品设计、模型和合规规则。
- `design-credit-product/scripts/`：确定性计算引擎及回归测试。
- `design-credit-product/assets/input-template.json`：无地区、无产品参数的输入模板。

项目输入、政策快照、模型输出和审批资料应保存在 Skill 目录之外。

## 运行

```powershell
python design-credit-product/scripts/credit_model.py `
  --input C:\path\to\project-input.json `
  --output C:\path\to\result.json `
  --cashflows C:\path\to\cashflows.csv
```

运行测试：

```powershell
python -m unittest discover -s design-credit-product/scripts -p "test_*.py" -v
```

## 边界

Skill 不内置任何地区的现行监管、税务或市场结论。管理 APR 不等同于监管 APR；当前模型也不替代 IFRS 9/CECL、正式资本计量、纳税申报或生产系统。真实项目必须使用与目标地域、主体和日期匹配的权威来源，并经产品、风险、财务、税务、法务和合规团队审批。
