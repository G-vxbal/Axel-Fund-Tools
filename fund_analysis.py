#!/usr/bin/env python3
"""
台灣基金分析工具 v2.0
TDCC 境外基金 + Yahoo 股市境內基金
快取機制 | 多期間績效 | 資金流向 | 比較分析
"""

import urllib.request, csv, io, sys, json, os, pickle
from datetime import datetime, timedelta
from pathlib import Path

BASE_URL = "https://opendata.tdcc.com.tw/getOD.ashx"
CACHE_DIR = Path.home() / ".hermes" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ─── 快取機制 ────────────────────────────────────────────
def cache_get(key, max_age_hours=4):
    """回傳 (data, age_hours) 或 (None, None)"""
    f = CACHE_DIR / f"{key}.pkl"
    if not f.exists():
        return None, None
    age = (datetime.now() - datetime.fromtimestamp(f.stat().st_mtime)).total_seconds() / 3600
    if age > max_age_hours:
        return None, None
    with open(f, 'rb') as fh:
        return pickle.load(fh), age

def cache_set(key, data):
    with open(CACHE_DIR / f"{key}.pkl", 'wb') as fh:
        pickle.dump(data, fh)

# ─── TDCC 資料抓取 ──────────────────────────────────────
def fetch_tdcc(id_, max_age=4):
    key = f"tdcc_{id_}"
    data, age = cache_get(key, max_age)
    if data is not None:
        print(f"  [快取] {id_} ({age:.1f}h 前)", file=sys.stderr)
        return data
    print(f"  [下載] {id_}...", file=sys.stderr)
    url = f"{BASE_URL}?id={id_}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=20)
    rows = list(csv.DictReader(io.StringIO(resp.read().decode('utf-8-sig'))))
    cache_set(key, rows)
    print(f"  [快取] 存檔完成，共 {len(rows)} 筆", file=sys.stderr)
    return rows

def get_nav_data():
    return fetch_tdcc("3-4")

def get_basic_data():
    return fetch_tdcc("3-2")

def get_market_flow():
    return fetch_tdcc("3-10")

# ─── 工具函式 ────────────────────────────────────────────
def latest_date(rows, date_col='日期'):
    return max(r[date_col] for r in rows)

def find_closest_date(rows, target_date_str, code_col='基金代碼', date_col='日期'):
    """找最接近目標日期的淨值（TDCC資料只有4個交易日/週）"""
    dates = sorted(set(r[date_col] for r in rows))
    target = target_date_str
    if target in dates:
        return target
    # 往前找最接近的
    for d in reversed(dates):
        if d <= target:
            return d
    return dates[0]

def date_offset(trading_days_list, from_idx, offset):
    """從 from_idx 往前 offset 個交易日"""
    target_idx = from_idx - offset
    if target_idx < 0:
        target_idx = 0
    return trading_days_list[target_idx]

def calc_period_returns(rows, code, date_col='日期', nav_col='基金淨值(金額)'):
    """計算各期間報酬（使用最近可用交易日）"""
    dates = sorted(set(r[date_col] for r in rows))
    latest = dates[-1]

    # 建立 基金代碼→(日期,淨值) 的 dict，便於查詢
    nav_by_date = {}
    for r in rows:
        if r.get('基金代碼') == code:
            nav_by_date[r[date_col]] = float(r[nav_col])

    if latest not in nav_by_date:
        return None

    # 每個期間需要的交易日數（約略）
    period_map = [
        ('1週', 5),
        ('1月', 20),
        ('3月', 60),
        ('6月', 126),
        ('1年', 252),
    ]

    results = {}
    for label, offset in period_map:
        target_idx = len(dates) - 1 - offset
        if target_idx < 0:
            target_idx = 0
        from_date = dates[target_idx]
        to_date = latest

        nav_from = nav_by_date.get(from_date)
        nav_to = nav_by_date.get(to_date)

        if nav_from and nav_to and nav_from > 0:
            ret = (nav_to - nav_from) / nav_from * 100
            # 年化
            ann = ret * (252 / offset) if offset > 0 else 0
            results[label] = {
                'from_date': from_date,
                'to_date': to_date,
                'return': ret,
                'annualized': ann,
                'nav_from': nav_from,
                'nav_to': nav_to,
            }
    return results

# ─── Yahoo 股市境內基金（web_extract） ──────────────────
def fetch_yahoo_domestic():
    """用 web_extract 抓 Yahoo 股市境內基金績效"""
    import urllib.request, json, re
    try:
        url = "https://tw.stock.yahoo.com/fund/domestic/ranking"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode('utf-8')

        # 直接解析 li 項目
        funds = []
        # 找表格內的基金行：名稱 + 數字
        rows = re.findall(
            r'>([^<]{5,50}?(?:基金|型) [^<]{0,30}?)</a>.*?(\d{1,3}[.\d]*%|[-−]\d{1,3}[.\d]*%)',
            html, re.DOTALL
        )
        # 嘗試正則抓績效數字
        perf_cells = re.findall(
            r'<td[^>]*>([\d.\-−%+]+)</td>',
            html
        )
        print(f"  [Yahoo] 找到 {len(perf_cells)} 個數值", file=sys.stderr)
        return {"status": "ok", "html_len": len(html)}
    except Exception as e:
        return {"status": "error", "msg": str(e)}

def get_yahoo_funds():
    """直接用 web_extract（外部工具），本腳本只做 TDCC"""
    return None  # Yahoo資料由外部web_extract提供

# ─── 指令 ────────────────────────────────────────────────
def cmd_nav(name_or_code, limit=15):
    rows = get_nav_data()
    latest = latest_date(rows)
    results = []
    nl = name_or_code.upper()
    for r in rows:
        if r['日期'] == latest:
            if nl in r['基金代碼'].upper() or nl in r['基金名稱'].upper():
                results.append(r)
    results.sort(key=lambda x: x['基金代碼'])
    print(f"\n=== {latest} 最新淨值 ===")
    print(f"{'代碼':<12} {'基金名稱':<40} {'淨值':>12} {'幣別'}")
    print("-"*70)
    for r in results[:limit]:
        print(f"{r['基金代碼']:<12} {r['基金名稱'][:40]:<40} {r[latest]:>12} {r['計價幣別']}" if latest in r else f"{r['基金代碼']:<12} {r['基金名稱'][:40]:<40} {r['基金淨值(金額)']:>12} {r['計價幣別']}")
    print(f"\n共 {len(results)} 筆")

def cmd_perf(name):
    rows = get_nav_data()
    nl = name.upper()
    latest = latest_date(rows)

    candidates = []
    for r in rows:
        if r['日期'] == latest and nl in r['基金名稱'].upper():
            candidates.append(r)

    if not candidates:
        print(f"找不到: {name}")
        return

    print(f"\n{'='*65}")
    for c in candidates[:5]:
        code = c['基金代碼']
        rets = calc_period_returns(rows, code)
        currency = c['計價幣別']
        nav_now = float(c['基金淨值(金額)'])

        print(f"\n{c['基金名稱'][:50]}")
        print(f"代碼: {code} | 幣別: {currency} | 最新淨值: {nav_now:.4f} | 日期: {latest}")
        if rets:
            print(f"{'期間':<6} {'期間報酬':>10} {'年化報酬':>10}  {'起日':<8} {'訖日'}")
            print("-"*50)
            for label in ['1週','1月','3月','6月','1年']:
                if label in rets:
                    r = rets[label]
                    print(f"{label:<6} {r['return']:>+9.2f}% {r['annualized']:>+9.2f}%  {r['from_date']:<8} {r['to_date']}")
        else:
            print("  無法計算報酬（資料不足）")

def cmd_flow(month=None):
    rows = get_market_flow()
    months = sorted(set(r['年月'] for r in rows))
    target = month or months[-1]

    print(f"\n=== {target} 基金市場資金流向 ===")
    print(f"{'基金類別':<18} {'淨申贖(NTD)':>16} {'國內持有(NTD)':>18} {'筆數':>6}")
    print("-"*62)

    cats = ['股票型','固定收益型','平衡型(混合型)','貨幣市場型','其他型']
    totals = {cat: {'net': 0, 'hold': 0, 'count': 0} for cat in cats}
    found_months = set()
    for r in rows:
        if r['年月'] == target:
            cat = r['基金類別']
            if cat in totals:
                totals[cat]['net'] += int(r['淨申贖總金額'])
                totals[cat]['hold'] += int(r['國內投資人持有金額'])
                totals[cat]['count'] += int(r['基金筆數'])
                found_months.add(cat)

    grand_net = 0
    for cat in cats:
        if cat in found_months:
            t = totals[cat]
            net_str = f"{t['net']:>+16,}"
            hold_str = f"{t['hold']:>18,}"
            print(f"{cat:<18} {net_str} {hold_str} {t['count']:>6,}")
            grand_net += t['net']

    print("-"*62)
    print(f"{'合計':<18} {grand_net:>+16,}")

def cmd_compare(funds_str):
    names = [n.strip() for n in funds_str.split(',')]
    rows = get_nav_data()
    latest = latest_date(rows)

    print(f"\n{'='*70}")
    print(f"{'基金名稱':<38} {'最新淨值':>12} {'1年報酬':>10} {'年化':>8}")
    print(f"{'='*70}")

    for name in names:
        nl = name.upper()
        candidates = [r for r in rows if r['日期']==latest and nl in r['基金名稱'].upper()]
        if not candidates:
            print(f"{name:<38} {'找不到':>12}")
            continue
        c = candidates[0]
        code = c['基金代碼']
        rets = calc_period_returns(rows, code)
        nav = float(c['基金淨值(金額)'])
        ret_1y = rets.get('1年', {}) if rets else {}
        ret_str = f"{ret_1y.get('return', 0):+.2f}%" if ret_1y else "N/A"
        ann_str = f"{ret_1y.get('annualized', 0):+.2f}%" if ret_1y else ""
        print(f"{c['基金名稱'][:38]:<38} {nav:>12.4f} {ret_str:>10} {ann_str:>8}")

def cmd_report():
    rows = get_nav_data()
    flow_rows = get_market_flow()
    latest = latest_date(rows)
    dates = sorted(set(r['日期'] for r in rows))

    print("="*65)
    print("  台灣基金市場 每週報告")
    print(f"  產生: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  數據: {latest}（約 {len(dates)} 個交易日）")
    print("="*65)

    # ── 月資金流向 ──
    months = sorted(set(r['年月'] for r in flow_rows))
    print("\n【月資金流向】")
    for m in months[-3:]:
        for r in flow_rows:
            if r['年月'] == m and r['基金類別'] in ['股票型','固定收益型','平衡型(混合型)']:
                net = int(r['淨申贖總金額'])
                net_str = f"{net:>+15,}" if net >= 0 else f"{net:<+16,}"
                print(f"  {m} {r['基金類別']:<14} 淨申贖: {net_str} NTD")

    # ── 熱門固定收益基金 ──
    print(f"\n【固定收益型 報酬前10（境外基金，USD計價）】")
    bond_keywords = ['債券','收益','高收益','非投資等級']
    found = {}
    for r in rows:
        if r['日期'] == latest and r['計價幣別'] == 'USD':
            for kw in bond_keywords:
                if kw in r['基金名稱']:
                    code = r['基金代碼']
                    if code not in found:
                        found[code] = r
                    break

    bond_rets = []
    for code, r in found.items():
        rets = calc_period_returns(rows, code)
        ret_1y = rets.get('1年', {}).get('return') if rets else None
        bond_rets.append((ret_1y or -999, r))
    bond_rets.sort(key=lambda x: x[0], reverse=True)

    print(f"{'基金名稱':<40} {'1年報酬':>10} {'年化':>8} {'最新淨值'}")
    print("-"*70)
    for ret_val, r in bond_rets[:10]:
        rets_all = calc_period_returns(rows, r['基金代碼'])
        ann = rets_all.get('1年',{}).get('annualized',0) if rets_all else 0
        ret_str = f"{ret_val:+.2f}%" if ret_val > -999 else "N/A"
        ann_str = f"{ann:+.2f}%" if ann else ""
        print(f"{r['基金名稱'][:40]:<40} {ret_str:>10} {ann_str:>8} {float(r['基金淨值(金額)']):.4f}")

    # ── 境內台股基金（Yahoo） ──
    print(f"\n【境內台股基金 報酬前10（Yahoo股市）】")
    yf = get_yahoo_funds()
    if yf:
        # 取前10
        for item in yf[:10]:
            name = item.get('name','')
            nav = item.get('nav','')
            perf_1y = item.get('perf1Y','')
            print(f"  {name:<35} 1年: {perf_1y:>8} 淨值: {nav}")
    else:
        print("  無法取得Yahoo資料，請至 https://tw.stock.yahoo.com/fund/domestic/ranking 查看")

    print("\n" + "="*65)

# ─── 主程式 ──────────────────────────────────────────────
if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        cmd_report()
    elif args[0] == "nav" and len(args) > 1:
        cmd_nav(args[1])
    elif args[0] == "perf" and len(args) > 1:
        cmd_perf(args[1])
    elif args[0] == "flow":
        cmd_flow(args[1] if len(args) > 1 else None)
    elif args[0] == "compare" and len(args) > 1:
        cmd_compare(args[1])
    elif args[0] == "report":
        cmd_report()
    elif args[0] == "cache_clear":
        import shutil
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
        print("快取已清除")
    else:
        print(__doc__)
