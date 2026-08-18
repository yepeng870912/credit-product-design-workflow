# 信贷产品设计工作流

用于设计区域化信贷产品参数并构建可审计的单笔与生命周期定价模型。

## 功能

- 支持等额本息、等额本金、等本等息和到期还本。
- 建模提前结清和 0+/30+/90+ Vintage 曲线。
- 计算企业逐期现金流、毛利润、NPV、ROI、RAROC 和生命周期 LTV。
- 分别计算搭售产品购买者与未购买者的借款人 IRR/APR。
- 保留余额递推、公式轨迹、输入来源和自动对账结果。
- 支持地域政策、定价限制、税务规则和市场资料登记。

## 目录

- `design-credit-product/`：Codex Skill、计算脚本、输入模板和参考资料。
- `outputs/`：示例验证工作簿。
- 根目录 Markdown 文件：历次模型验证与计算说明。

## 运行示例

```powershell
python design-credit-product/scripts/credit_model.py `
  --input design-credit-product/assets/example-input-v7.json `
  --output example-output.json `
  --cashflows example-cashflows.csv
```

运行测试：

```powershell
python -m unittest discover -s design-credit-product/scripts -p "test_*.py"
```

## 重要说明

本项目是透明的产品可行性及定价测算工具，不构成法律、税务、会计或监管意见，也不替代 IFRS 9/CECL、正式资本计量或生产系统。正式使用前应由产品、风险、财务、税务、法务及合规团队审批，并使用与目标地域和主体匹配的最新官方规则及真实风险数据。
