#!/usr/bin/env python3
"""Single-factor diagnostics — validate the neutralized panel against known
priors (SUE weak+, momentum negative, reversal regime-flip, low-vol regime).
Pure sanity: per-feature mean per-date rank-IC + D10-D1 + by-regime IC at +10d.
"""
from __future__ import annotations
import json, os, sys
import numpy as np
sys.path.insert(0, os.getcwd())
from factor_research.model.harness import load_panel, neutralize, _spearman, _deciles

def main(h=10):
    z, meta = load_panel()
    Z = neutralize(z, meta)
    fwd = z[f"fwd{h}"].astype(np.float64)
    names = meta["feat_names"]; regimes = meta["regimes"]
    D, N, F = Z.shape
    print(f"{'feature':16} {'IC':>7} {'IC_t':>6} {'pos%':>5} {'D10-D1':>8} {'TOPexc':>8}  by-regime IC (up_c/up_t/dn_c/dn_t)")
    rows=[]
    for fi, nm in enumerate(names):
        ics=[]; dds=[]; tops=[]; reg={}
        for d in range(D):
            x=Z[d,:,fi]; y=fwd[d]
            ok=np.isfinite(x)&np.isfinite(y)
            if ok.sum()<50: continue
            ic=_spearman(x[ok],y[ok])
            if not np.isfinite(ic): continue
            ics.append(ic)
            g=regimes[d]["regime"]; reg.setdefault(g,[]).append(ic)
            dec=_deciles(x,y,10)
            if dec is not None:
                dds.append(dec[-1]-dec[0]); tops.append(dec[-1]-np.nanmean(y[ok]))
        if not ics: continue
        a=np.array(ics); t=a.mean()/(a.std(ddof=1)/np.sqrt(len(a))) if len(a)>1 else np.nan
        rmap={k:np.mean(v) for k,v in reg.items()}
        rstr=" ".join(f"{rmap.get(k,float('nan')):+.3f}" for k in ["up_calm","up_turbulent","down_calm","down_turbulent"])
        print(f"{nm:16} {a.mean():+.4f} {t:+5.2f} {100*(a>0).mean():4.0f}% {np.mean(dds):+.4f} {np.mean(tops):+.4f}  {rstr}")
        rows.append((nm, float(a.mean()), float(t), float((a>0).mean()), float(np.mean(dds)), float(np.mean(tops)), rmap))
    json.dump(rows, open("factor_research/model/diag_singlefactor.json","w"), default=float, indent=1)

if __name__=="__main__":
    main(int(sys.argv[1]) if len(sys.argv)>1 else 10)
