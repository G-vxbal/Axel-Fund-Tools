#!/usr/bin/env python3
"""
台灣基金分析工具 - TDCC數據自動抓取、績效計算、配置建議
用法: python fund_analysis.py [指令] [參數]
指令:
  nav <基金名稱或代碼>   - 查詢基金淨值
  perf <基金名稱>       - 計算績效（1週/1月/3月/1年）
  flow <月>             - 月資金流向（預設最近）
  top <類型> [筆數]     - 同類型排名（預設10）
  compare <基金1,基金2> - 兩檔比較
  report               - 完整分析報告
"""

import urllib.request, csv, io, sys, json
from datetime import datetime, timedelta

BASE_URL = "https://opendata.tdcc.com.tw/getOD.ashx"

def fetch(id_):
    url = f"{BASE_URL}?id={id_}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=20)
    return list(csv.DictReader(io.StringIO(resp.read().decode('utf-8-sig'))))

def get_nav_data():
    return fetch("3-4")

def get_basic_data():
    return fetch("3-2")

def get_market_flow():
    return fetch("3-10")

def latest_date(rows):
    return max(r['日期'] for r in rows)

def year_ago_date(rows):
    dates = sorted(set(r['日期'] for r in rows))
    return dates[-4] if len(dates) >= 4 else dates[0]  # TDCC約4個交易日/週

def calc_return(rows, code, date_from, date_to):
    """計算期間報酬率"""
    nav_from = None
    nav_to = None
    for r in rows:
        if r['基金代碼'] == code:
            if r['日期'] == date_from:
                nav_from = float(r['基金淨值(金額)'])
            if r['日期'] == date_to:
                nav_to = float(r['基金淨值(金額)'])
    if nav_from and nav_to:
        return (nav_to - nav_from) / nav_from * 100
    return None

def cmd_nav(name_or_code, limit=10):
    rows = get_nav_data()
    latest = latest_date(rows)
    results = []
    for r in rows:
        if r['日期'] == latest:
            if name_or_code.upper() in r['基金代碼'].upper() or name_or_code.upper() in r['基金名稱'].upper():
                results.append(r)
    results.sort(key=lambda x: x['基金代碼'])
    print(f"=== {latest} 最新淨值 ===")
    for r in results[:limit]:
        print(f"{r['基金代碼']} | {r['基金名稱'][:40]} | {r['基金淨值(金額)']} {r['計價幣別']}")
    print(f"共 {len(results)} 筆")

def cmd_perf(name):
    rows = get_nav_data()
    dates = sorted(set(r['日期'] for r in rows))
    latest = dates[-1]
    
    # 找到符合的基金
    candidates = []
    for r in rows:
        if r['日期'] == latest and name.upper() in r['基金名稱'].upper():
            candidates.append(r)
    
    if not candidates:
        print(f"找不到: {name}")
        return
    
    print(f"\n{'='*60}")
    print(f"{'基金名稱':<42} {'日期':<8} {'淨值':>12} {'幣別'}")
    print(f"{'='*60}")
    
    for c in candidates[:5]:
        code = c['基金代碼']
        name_full = c['基金名稱']
        currency = c['計價幣別']
        
        # 計算不同期間
        periods = {
            '1週': dates[-5] if len(dates)>=5 else dates[0],
            '1月': dates[-20] if len(dates)>=20 else dates[0],
            '3月': dates[-60] if len(dates)>=60 else dates[0],
            '1年': dates[-252] if len(dates)>=252 else dates[0],
        }
        
        print(f"\n{name_full[:40]}")
        print(f"代碼: {code} | 幣別: {currency}")
        print(f"{'期間':<8} {'期間報酬率':>10} {'年化報酬率':>10}")
        print("-"*40)
        
        for label, d in periods.items():
            ret = calc_return(rows, code, d, latest)
            if ret is not None:
                # 年化
                days_map = {'1週': 5, '1月': 20, '3月': 60, '1年': 252}
                days = days_map[label]
                annualized = ret * (252 / days) if days > 0 else 0
                print(f"{label:<8} {ret:>+9.2f}% {annualized:>+9.2f}%")
            else:
                print(f"{label:<8} {'N/A':>10}")

def cmd_flow(month=None):
    rows = get_market_flow()
    months = sorted(set(r['年月'] for r in rows))
    target = month or months[-1]
    
    print(f"\n=== {target} 基金市場資金流向 ===")
    print(f"{'類別':<18} {'淨申贖(NTD)':>16} {'國內持有(NTD)':>16} {'筆數':>6}")
    print("-"*58)
    
    total_net = 0
    for r in rows:
        if r['年月'] == target:
            net = int(r['淨申贖總金額'])
            hold = int(r['國內投資人持有金額'])
            count = int(r['基金筆數'])
            cat = r['基金類別']
            total_net += net
            net_str = f"{net:+,}" if net >= 0 else f"{net:,}"
            hold_str = f"{hold:,.0f}"[:16]
            print(f"{cat:<18} {net_str:>16} {hold_str:>16} {count:>6}")
    
    print("-"*58)
    print(f"{'合計':<18} {total_net:>+16,}")

def cmd_top(fund_type=None, n=10):
    """同類型績效排行"""
    # 從Yahoo股市抓台股基金
    import urllib.request
    url = "https://tw.stock.yahoo.com/fund/domestic/ranking"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    # Yahoo會阻擋，這裡用靜態方式
    print(f"請用 web_search 或瀏覽器查看: https://tw.stock.yahoo.com/fund/domestic/ranking")
    print(f"或使用 TDCC 3-4 自行計算")

def cmd_compare(funds_str):
    names = [n.strip() for n in funds_str.split(',')]
    rows = get_nav_data()
    dates = sorted(set(r['日期'] for r in rows))
    latest = dates[-1]
    
    print(f"\n=== 基金比較 | {latest} ===")
    print(f"{'基金':<35} {'最新淨值':>12} {'1年報酬':>10} {'年化':>8}")
    print("-"*70)
    
    for name in names:
        candidates = [r for r in rows if r['日期']==latest and name.upper() in r['基金名稱'].upper()]
        if not candidates:
            print(f"{name:<35} {'找不到':>12}")
            continue
        c = candidates[0]
        code = c['基金代碼']
        ret = calc_return(rows, code, dates[-252], latest) if len(dates)>=252 else None
        ann = ret * (252/252) if ret else None
        print(f"{c['基金名稱'][:35]:<35} {float(c['基金淨值(金額)']):>12.4f} {ret:>+9.2f}% {ann:>+7.2f}%" if ret else f"{c['基金名稱'][:35]:<35} {float(c['基金淨值(金額)']):>12.4f} {'N/A':>10}")

def cmd_report():
    """完整報告"""
    rows = get_nav_data()
    flow_rows = get_market_flow()
    dates = sorted(set(r['日期'] for r in rows))
    latest = latest_date(rows)
    
    print("="*60)
    print("  台灣基金市場 每週報告")
    print(f"  產生時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  數據日期: {latest}")
    print("="*60)
    
    # 月資金流向
    months = sorted(set(r['年月'] for r in flow_rows))
    print(f"\n【月資金流向】")
    for m in months[-3:]:
        for r in flow_rows:
            if r['年月'] == m:
                net = int(r['淨申贖總金額'])
                print(f"  {m} {r['基金類別']:<12} 淨申贖: {net:>15,} NTD")
    
    # 熱門類型
    print(f"\n【固定收益型 熱門基金】")
    bond_keywords = ['債券','收益','高收益','非投資等級']
    found = {}
    for r in rows:
        if r['日期'] == latest:
            for kw in bond_keywords:
                if kw in r['基金名稱'] and r['計價幣別']=='USD':
                    code = r['基金代碼']
                    if code not in found:
                        found[code] = r
                    break
    count = 0
    for code, r in sorted(found.items()):
        if count >= 10: break
        ret = calc_return(rows, code, dates[-252], latest) if len(dates)>=252 else None
        ret_str = f"{ret:+.2f}%" if ret else "N/A"
        print(f"  {r['基金名稱'][:38]:<38} 1年: {ret_str:>10}")
        count += 1
    
    print("\n" + "="*60)

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        cmd_report()
    elif args[0] == "nav" and len(args) > 1:
        cmd_nav(args[1])
    elif args[0] == "perf" and len(args) > 1:
        cmd_perf(args[1])
    elif args[0] == "flow":
        cmd_flow(args[1] if len(args)>1 else None)
    elif args[0] == "top":
        cmd_top(args[1] if len(args)>1 else None, int(args[2]) if len(args)>2 else 10)
    elif args[0] == "compare" and len(args) > 1:
        cmd_compare(args[1])
    elif args[0] == "report":
        cmd_report()
    else:
        print(__doc__)
