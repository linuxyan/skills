#!/usr/bin/env python3
"""
内生增长分红估值模型 (V1.0)
核心算法：以 ROE × 留存比例 推导内生增长率，以十年后 YoC=8% 反推安全买入价
"""

import argparse
import json
import sys


def get_roe_tier(roe: float) -> tuple:
    """
    根据 ROE 档位返回 (生意类型, 增速上限)
    ROE 传入为小数形式，如 0.25 表示 25%
    """
    if roe > 0.25:
        return ("顶级生意", 0.08, "ROE>25%，护城河深，再投资回报极高")
    elif roe >= 0.15:
        return ("强力生意", 0.05, "ROE 15%-25%，行业较饱和，增长受限")
    else:
        return ("平庸/公用事业", 0.03, "ROE<15%，增长缓慢，接近GDP或通胀")


def calculate_valuation(
    eps_curr: float,
    roe_5y: float,
    payout_5y: float,
    target_yield: float = 0.08,
    years: int = 10,
) -> dict:
    """
    执行估值计算

    参数:
        eps_curr:     当前每股收益（元），推荐使用 TTM EPS
        roe_5y:       近5年平均 ROE（小数，如 0.20 表示 20%）
        payout_5y:    近5年平均分红率（小数，如 0.70 表示 70%）
        target_yield: 目标成本收益率，默认 0.08 (8%)
        years:        复利计算周期，默认 10 年

    返回:
        包含所有中间计算结果和最终估值的字典
    """
    # ── 第一步：计算理论增速 ──────────────────────────────────────────
    retention = 1.0 - payout_5y          # 留存比例
    g_base = roe_5y * retention           # 理论增速

    # ── 第二步：根据 ROE 档位截断，得到 g_final ──────────────────────
    biz_type, cap, cap_reason = get_roe_tier(roe_5y)
    g_final = min(g_base, cap)

    # ── 第三步：计算安全买入价 ────────────────────────────────────────
    # 安全买入价 = EPS_curr × (1+g_final)^years × Payout / target_yield
    future_eps = eps_curr * (1 + g_final) ** years
    future_dps = future_eps * payout_5y   # 第 years 年的每股分红
    safe_price = future_dps / target_yield

    return {
        "eps_curr": eps_curr,
        "roe_5y": roe_5y,
        "payout_5y": payout_5y,
        "retention": retention,
        "g_base": g_base,
        "biz_type": biz_type,
        "cap": cap,
        "cap_reason": cap_reason,
        "g_final": g_final,
        "years": years,
        "target_yield": target_yield,
        "future_eps": future_eps,
        "future_dps": future_dps,
        "safe_price": safe_price,
    }


def get_g_final_trust_guidance(g_base: float, g_final: float, payout: float, cap: float) -> str:
    """
    根据 g_base/g_final 的关系和分红率，输出可信度评估的提示信息。
    注意：这仅提供计算视角的参考，实际可信度还需结合行业/历史增速等外部数据。
    """
    lines = []
    if g_base > cap:
        lines.append(f"  ⚡ g_base({g_base*100:.1f}%) 被 Cap({cap*100:.1f}%) 截断至 g_final({g_final*100:.1f}%)")
        lines.append(f"     截断幅度 {((g_base-g_final)/g_base)*100:.0f}%，模型偏保守，可信度加分")
    else:
        lines.append(f"  📊 g_base({g_base*100:.1f}%) 未被截断，g_final = g_base")
        lines.append(f"     留存再投资需实际产生 {g_base*100:.1f}% 的回报才能兑现")

    if payout >= 0.70:
        lines.append(f"  💰 分红率 {payout*100:.0f}% ≥ 70%，不依赖大量再投资，g_final 天然容易实现")
    elif payout >= 0.40:
        lines.append(f"  ⚖️ 分红率 {payout*100:.0f}%，留存比例 {int((1-payout)*100)}%，适度依赖再投资质量")
    else:
        lines.append(f"  ⚠️ 分红率仅 {payout*100:.0f}%，留存比例 {int((1-payout)*100)}%，高度依赖再投资效率")

    lines.append(f"  🔍 请结合：历史 EPS CAGR、行业空间、ROE 稳定性 综合评分（见 SKILL.md Phase 2.5）")
    return "\n".join(lines)


def format_report(result: dict, stock_name: str = "", current_price: float = None) -> str:
    """格式化输出估值报告"""
    title = f"股票估值报告" + (f"——{stock_name}" if stock_name else "")
    sep = "=" * 58

    # 价格比较
    price_compare = ""
    if current_price is not None and current_price > 0:
        ratio = current_price / result["safe_price"]
        if ratio <= 0.85:
            status = "🟢 明显低估（当前价低于安全价 15% 以上）"
        elif ratio <= 1.0:
            status = "🟡 基本合理（当前价接近安全价）"
        elif ratio <= 1.20:
            status = "🟠 略微高估（当前价高于安全价 0%-20%）"
        else:
            status = "🔴 明显高估（当前价高于安全价 20% 以上）"
        discount = (result["safe_price"] - current_price) / result["safe_price"] * 100
        price_compare = f"""
【当前价格对比】
  当前股价        : ¥{current_price:.2f}
  安全买入价      : ¥{result['safe_price']:.2f}
  安全边际        : {discount:+.1f}%
  估值状态        : {status}
"""

    lines = [
        sep,
        f"  {title}",
        sep,
        "",
        "【核心输入参数】",
        f"  当前 EPS (TTM)  : ¥{result['eps_curr']:.4f}",
        f"  5年均 ROE       : {result['roe_5y']*100:.1f}%",
        f"  5年均分红率     : {result['payout_5y']*100:.1f}%",
        f"  留存比例        : {result['retention']*100:.1f}%",
        "",
        "【增速计算】",
        f"  理论增速 g_base : {result['g_base']*100:.2f}%   (ROE × 留存比)",
        f"  生意类型        : {result['biz_type']}",
        f"  增速上限 Cap    : {result['cap']*100:.1f}%   ({result['cap_reason']})",
        f"  实战增速 g_final: {result['g_final']*100:.2f}%",
        "",
        "【g_final 可信度评估提示】",
        get_g_final_trust_guidance(
            result['g_base'], result['g_final'], result['payout_5y'], result['cap']
        ),
        "",
        "【估值结果】",
        f"  复利年数        : {result['years']} 年",
        f"  目标 YoC        : {result['target_yield']*100:.1f}%",
        f"  {result['years']}年后预测EPS   : ¥{result['future_eps']:.4f}",
        f"  {result['years']}年后预测DPS   : ¥{result['future_dps']:.4f}（每股分红）",
        "",
        f"  ★ 安全买入价    : ¥{result['safe_price']:.2f}",
        "",
    ]

    if price_compare:
        lines.append(price_compare)

    lines += [
        "【风险提示】",
        "  ⚠ 本模型结果仅供参考，不构成投资建议。",
        "  ⚠ 宁可保守，永远给预测留出余地。",
        "  \u26a0 分红是\u201c谎言检测器\u201d，连续高分红能过滤虚假利润。",
        sep,
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="内生增长分红估值模型 V1.0 — 计算股票安全买入价"
    )
    parser.add_argument("--eps", type=float, required=True,
                        help="当前每股收益（元），建议使用 TTM EPS")
    parser.add_argument("--roe", type=float, required=True,
                        help="近5年平均 ROE（小数，如 0.20 表示 20%%）")
    parser.add_argument("--payout", type=float, required=True,
                        help="近5年平均分红率（小数，如 0.70 表示 70%%）")
    parser.add_argument("--target-yield", type=float, default=0.08,
                        help="目标成本收益率，默认 0.08 (8%%)")
    parser.add_argument("--years", type=int, default=10,
                        help="复利计算年数，默认 10")
    parser.add_argument("--stock-name", type=str, default="",
                        help="股票名称（可选，仅用于报告标题）")
    parser.add_argument("--current-price", type=float, default=None,
                        help="当前股价（可选，用于与安全价比较）")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 格式输出原始计算结果")

    args = parser.parse_args()

    # 参数校验
    if args.eps <= 0:
        print("错误：EPS 必须为正数（负收益公司不适用本模型）", file=sys.stderr)
        sys.exit(1)
    if not (0 < args.roe <= 1):
        print("错误：ROE 应为 0-1 之间的小数（如 20% 请传 0.20）", file=sys.stderr)
        sys.exit(1)
    if not (0 < args.payout <= 1):
        print("错误：分红率应为 0-1 之间的小数（如 70% 请传 0.70）", file=sys.stderr)
        sys.exit(1)
    if not (0 < args.target_yield <= 1):
        print("错误：目标收益率应为 0-1 之间的小数（如 8% 请传 0.08）", file=sys.stderr)
        sys.exit(1)

    result = calculate_valuation(
        eps_curr=args.eps,
        roe_5y=args.roe,
        payout_5y=args.payout,
        target_yield=args.target_yield,
        years=args.years,
    )

    if args.json:
        # 添加辅助信息到 JSON 输出
        output = dict(result)
        output["stock_name"] = args.stock_name
        output["g_final_trust_hint"] = get_g_final_trust_guidance(
            result["g_base"], result["g_final"], result["payout_5y"], result["cap"]
        )
        output["is_truncated"] = (result["g_base"] > result["cap"])
        output["truncation_pct"] = (
            ((result["g_base"] - result["g_final"]) / result["g_base"] * 100)
            if result["g_base"] > result["cap"] else 0.0
        )
        if args.current_price:
            output["current_price"] = args.current_price
            output["discount_pct"] = (result["safe_price"] - args.current_price) / result["safe_price"] * 100
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(format_report(result, stock_name=args.stock_name, current_price=args.current_price))


if __name__ == "__main__":
    main()
