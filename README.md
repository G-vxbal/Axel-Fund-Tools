# 台灣基金分析工具

## 功能
- TDCC 開放資料即時抓取（每日更新）
- 基金淨值查詢
- 多期間績效計算（1週/1月/3月/1年）
- 月資金流向分析
- 基金比較

## 數據源
- [TDCC 臺灣集中保管結算所開放資料](https://www.tdcc.com.tw/portal/zh/stats/openData)
- 涵蓋 5,300+ 檔境外基金

## 使用方式
```bash
python fund_analysis.py nav <關鍵字>   # 淨值查詢
python fund_analysis.py perf <基金名>   # 績效計算
python fund_analysis.py flow [月份]     # 資金流向
python fund_analysis.py compare 基金1,基金2  # 比較
python fund_analysis.py report         # 完整報告
```
