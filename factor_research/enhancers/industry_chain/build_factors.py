#!/usr/bin/env python3
"""industry_chain family — build PIT-safe factor matrices aligned to panel [67 x 1617].

Factors (all use ONLY daily returns up to and including base_date; industry
membership = panel.npz['industry'] — CURRENT SNAPSHOT, caveat reported):

  c1_loo_20 / c1_loo_60   leave-one-out EW industry cum return over past 20/60d
                          (own-industry momentum; LOO removes own-stock return)
  c2up_20  / c2up_60      upstream(supplier) industries' EW cum return assigned
                          to downstream member stocks (cost/lead-lag axis)
  c2cu_20  / c2cu_60      customer(downstream) industries' EW cum return assigned
                          to supplier member stocks (Cohen-Frazzini customer momentum)
  c4lead_20 / c4lead_60   top-half-by-MV (leaders) EW cum return assigned to
                          bottom-half (followers) of same industry; NaN for leaders
  c4gap_20                (leader 20d - follower 20d) gap assigned to followers

Commodity leg (c3) INFEASIBLE on DockCase volume: 期货数据/日线行情/by_symbol
contains only 豆一(A.DCE) contracts; 南华期货指数行情 empty; no commodity ETFs
in ETF专题/ETF日线行情/by_symbol (24 files, none commodity); only gold spot.
akshare not allowed -> skipped.

THS index leg: 打板专题数据/同花顺概念和行业指数行情/all.csv is sparse
year-end snapshots (median 13 rows/code), NOT a daily series -> industry index
series are instead built from member-stock daily returns (fully PIT).

Adjacency (justified from config/industry_graphs/*.yaml cross industry_tags and
config/industry_to_commodity.yaml BOM rationale):
  NONFERROUS_METALS -> STORAGE_GRID            (NONFERROUS yaml seg tagged [NONFERROUS,STORAGE_GRID]; LC0/NI0/CU0 BOM)
  NONFERROUS_METALS -> CONSUMER_ELECTRONICS    (CU0/L0 BOM in industry_to_commodity)
  NONFERROUS_METALS -> ROBOTICS                (AL0/CU0 BOM)
  NONFERROUS_METALS -> EXPORT_MFG              (CU0/AL0 BOM)
  ANTI_INVOLUTION_CYCLICAL -> EXPORT_MFG       (RB0/I0/JM0 steel chain -> 通用设备)
  ANTI_INVOLUTION_CYCLICAL -> ROBOTICS         (steel/materials -> 装备制造; ROBOTICS seg tagged [ROBOTICS,EXPORT_MFG])
  SEMI_EQUIPMENT -> AI_COMPUTE                 (SEMI yaml segs tagged [SEMI_EQUIPMENT,AI_COMPUTE] x2)
  SEMI_EQUIPMENT -> CONSUMER_ELECTRONICS       (chips -> devices)
  STORAGE_GRID -> AI_COMPUTE                   (AI_COMPUTE yaml EVENT.dc_buildout + liquid_cooling tagged [AI_COMPUTE,STORAGE_GRID])
  AI_COMPUTE -> HK_CN_INTERNET                 (HK_CN_INTERNET yaml seg tagged [HK_CN_INTERNET,AI_COMPUTE])
"""
import os, sys, json
import numpy as np

os.environ["DOCKCASE_WRITEBACK"] = "0"
ROOT = "/Users/fanjie/Desktop/Cowork/project-ult-mvp20"
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "factor_research", "model"))

OUT = os.path.join(ROOT, "factor_research", "enhancers", "industry_chain", "factors_industry_chain.npz")

# supplier -> [customers]
EDGES = {
    "NONFERROUS_METALS": ["STORAGE_GRID", "CONSUMER_ELECTRONICS", "ROBOTICS", "EXPORT_MFG"],
    "ANTI_INVOLUTION_CYCLICAL": ["EXPORT_MFG", "ROBOTICS"],
    "SEMI_EQUIPMENT": ["AI_COMPUTE", "CONSUMER_ELECTRONICS"],
    "STORAGE_GRID": ["AI_COMPUTE"],
    "AI_COMPUTE": ["HK_CN_INTERNET"],
}


def main():
    meta = json.load(open("factor_research/model/panel_meta.json"))
    z = np.load("factor_research/model/panel.npz")
    px = np.load("factor_research/data/px_20230101.npz")
    pxm = json.load(open("factor_research/data/px_20230101.json"))
    assert pxm["cols"] == meta["cols"], "px cols != panel cols"
    RET = px["RET"].astype(np.float64)          # n_days x N, simple daily returns
    base_idx = meta["base_idx"]
    D, N = len(base_idx), len(meta["cols"])
    ind = z["industry"].astype(int)             # N
    lnmv = z["ln_mv"].astype(np.float64)        # D x N (PIT per base date)
    names = meta["industry_names"]
    K = len(names)
    name2k = {n: i for i, n in enumerate(names)}

    # ---- per-stock trailing cum returns ending AT base date (inclusive) ----
    def cum_ret(w):
        """C[d, j] = prod(1+r) - 1 over the w days ending at base_idx[d].
        Requires >= 80% non-NaN days in window, else NaN."""
        C = np.full((D, N), np.nan)
        L1 = np.log1p(RET)                      # NaN propagates
        for d, t in enumerate(base_idx):
            win = L1[t - w + 1: t + 1]          # w x N
            nok = np.isfinite(win).sum(0)
            s = np.nansum(win, 0)
            C[d] = np.where(nok >= int(0.8 * w), np.expm1(s), np.nan)
        return C

    C20, C60 = cum_ret(20), cum_ret(60)

    # ---- industry EW means + LOO ----
    factors, fnames = {}, []

    def ind_ew(C):
        """returns (M [D x K] industry EW mean, CNT [D x K])"""
        M = np.full((D, K), np.nan); CNT = np.zeros((D, K), int)
        for k in range(K):
            mask = ind == k
            sub = C[:, mask]
            n = np.isfinite(sub).sum(1)
            with np.errstate(invalid="ignore"):
                M[:, k] = np.where(n >= 5, np.nanmean(sub, 1), np.nan)
            CNT[:, k] = n
        return M, CNT

    M20, CNT20 = ind_ew(C20)
    M60, CNT60 = ind_ew(C60)

    # c1 LOO: (n*mean - own)/(n-1)
    for tag, C, M, CNT in (("c1_loo_20", C20, M20, CNT20), ("c1_loo_60", C60, M60, CNT60)):
        F = np.full((D, N), np.nan)
        for k in range(K):
            mask = ind == k
            n = CNT[:, [0]] * 0 + CNT[:, [k]]   # D x 1
            m = M[:, [k]]
            own = C[:, mask]
            with np.errstate(invalid="ignore"):
                loo = (n * m - own) / np.maximum(n - 1, 1)
            loo = np.where(np.isfinite(own) & np.isfinite(m) & (n >= 6), loo, np.nan)
            F[:, mask] = loo
        factors[tag] = F; fnames.append(tag)

    # c2 upstream->downstream and customer->supplier broadcasts
    up_of = {}      # downstream k -> list of upstream k
    cust_of = {}    # supplier k -> list of customer k
    for sup, custs in EDGES.items():
        ks = name2k[sup]
        for c in custs:
            kc = name2k[c]
            up_of.setdefault(kc, []).append(ks)
            cust_of.setdefault(ks, []).append(kc)

    def broadcast(M, rel):
        F = np.full((D, N), np.nan)
        for k, partners in rel.items():
            vals = np.nanmean(M[:, partners], 1)    # D
            F[:, ind == k] = vals[:, None]
        return F

    factors["c2up_20"] = broadcast(M20, up_of); fnames.append("c2up_20")
    factors["c2up_60"] = broadcast(M60, up_of); fnames.append("c2up_60")
    factors["c2cu_20"] = broadcast(M20, cust_of); fnames.append("c2cu_20")
    factors["c2cu_60"] = broadcast(M60, cust_of); fnames.append("c2cu_60")

    # c4 leader->follower (split by ln_mv median within industry, per base date)
    F_lead20 = np.full((D, N), np.nan)
    F_lead60 = np.full((D, N), np.nan)
    F_gap20 = np.full((D, N), np.nan)
    for d in range(D):
        for k in range(K):
            mask = ind == k
            mv = lnmv[d, mask]
            ok = np.isfinite(mv)
            if ok.sum() < 10:
                continue
            med = np.nanmedian(mv)
            lead = mask.copy(); lead[mask] = ok & (mv >= med)
            foll = mask.copy(); foll[mask] = ok & (mv < med)
            l20 = C20[d, lead]; f20 = C20[d, foll]
            l60 = C60[d, lead]
            if np.isfinite(l20).sum() < 5 or np.isfinite(l60).sum() < 5:
                continue
            lm20 = np.nanmean(l20); lm60 = np.nanmean(l60)
            fm20 = np.nanmean(f20) if np.isfinite(f20).sum() >= 5 else np.nan
            F_lead20[d, foll] = lm20
            F_lead60[d, foll] = lm60
            F_gap20[d, foll] = lm20 - fm20
    factors["c4lead_20"] = F_lead20; fnames.append("c4lead_20")
    factors["c4lead_60"] = F_lead60; fnames.append("c4lead_60")
    factors["c4gap_20"] = F_gap20; fnames.append("c4gap_20")

    # coverage report
    cov = {}
    for nme in fnames:
        F = factors[nme]
        per_date = np.isfinite(F).mean(1)
        cov[nme] = {"mean_cov": round(float(per_date.mean()), 4),
                    "min_cov": round(float(per_date.min()), 4),
                    "max_cov": round(float(per_date.max()), 4)}
        print(nme, cov[nme])

    np.savez_compressed(OUT, **{n: factors[n].astype(np.float32) for n in fnames},
                        fnames=np.array(fnames))
    json.dump({"coverage": cov, "edges": EDGES,
               "ind_mean_M20_shape": [D, K]},
              open(OUT.replace(".npz", "_meta.json"), "w"), indent=1)
    # save industry-level EW momentum for industry-level IC supplement
    np.savez_compressed(OUT.replace(".npz", "_indlevel.npz"), M20=M20, M60=M60)
    print("saved", OUT)


if __name__ == "__main__":
    main()
