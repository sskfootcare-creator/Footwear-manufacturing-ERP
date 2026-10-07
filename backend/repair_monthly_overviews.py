import asyncio
import motor.motor_asyncio

async def repair():
    client = motor.motor_asyncio.AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["ssk_footwear_erp"]
    docs = await db.online_monthly_reconciliation_overviews.find().to_list(10)
    for doc in docs:
        styles = doc.get("styles", [])
        tot_sold_rev = sum(float(s.get("net_sold_seller_price", 0) or 0) for s in styles)
        tot_prod_cost = sum(float(s.get("total_production_cost", 0) or 0) for s in styles)
        tot_sold_units = int(doc.get("total_net_sold") or (doc.get("pnl_summary", {}).get("net_units") or 0))
        fee_total = float((doc.get("platform_fee_breakdown") or {}).get("total_fees") or (doc.get("pnl_summary", {}).get("total_expenses") or 0.0))
        op_expenses = doc.get("operational_expenses") or {}
        allocated_op = float(op_expenses.get("allocated_operational_cost") or doc.get("allocated_operational_cost") or 0.0)
        total_plat_earnings = float(doc.get("platform_earnings") or 0.0)
        if not total_plat_earnings and doc.get("pnl_summary"):
            total_plat_earnings = float(doc["pnl_summary"].get("earnings_on_platform") or 0.0)
        
        actual_net_profit = round(total_plat_earnings - tot_prod_cost - allocated_op, 2)
        actual_net_margin = round((actual_net_profit / tot_sold_rev * 100), 2) if tot_sold_rev > 0 else 0.0
        
        net_asp = round(tot_sold_rev / tot_sold_units, 2) if tot_sold_units > 0 else 0.0
        avg_unit_cogs = round(tot_prod_cost / tot_sold_units, 2) if tot_sold_units > 0 else 0.0
        avg_platform_fee = round(fee_total / tot_sold_units, 2) if tot_sold_units > 0 else 0.0
        avg_overhead_per_pair = round(allocated_op / tot_sold_units, 2) if tot_sold_units > 0 else 0.0
        unit_contribution = round(net_asp - avg_unit_cogs - avg_platform_fee, 2)
        net_profit_per_pair = round(actual_net_profit / tot_sold_units, 2) if tot_sold_units > 0 else 0.0
        
        ret_analytics = doc.get("return_analytics") or {}
        unit_economics = {
            "net_asp": net_asp,
            "avg_unit_cogs": avg_unit_cogs,
            "avg_platform_fee_per_unit": avg_platform_fee,
            "avg_overhead_per_pair": avg_overhead_per_pair,
            "unit_contribution": unit_contribution,
            "net_profit_per_pair": net_profit_per_pair,
            "return_rate_pct": ret_analytics.get("overall_return_rate_pct", 0.0),
            "return_financial_damage": ret_analytics.get("total_return_financial_damage", 0.0) or ret_analytics.get("financial_damage_amount", 0.0),
        }
        
        await db.online_monthly_reconciliation_overviews.update_one(
            {"_id": doc["_id"]},
            {"$set": {
                "total_cost_of_production": round(tot_prod_cost, 2),
                "actual_net_profit": actual_net_profit,
                "actual_net_margin_pct": actual_net_margin,
                "unit_economics": unit_economics,
            }}
        )
        p = doc.get("platform")
        m = doc.get("month")
        print(f"Repaired {p}/{m}: tot_prod_cost={tot_prod_cost}, avg_unit_cogs={avg_unit_cogs}, unit_contribution={unit_contribution}, net_profit_per_pair={net_profit_per_pair}")

if __name__ == "__main__":
    asyncio.run(repair())
