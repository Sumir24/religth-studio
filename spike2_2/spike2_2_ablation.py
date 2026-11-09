"""
RELIGHT STUDIO — SPIKE 2.2: CORRECTED COMPONENT ABLATION SUITE
==============================================================
Document Reference: RS-SPEC-SPIKE-2.2-METRICS.md
Strict Verification Mode: Mathematically isolated ablation suite with zero false zeros,
proper NOT_APPLICABLE reporting for missing features, and shadow recall penalties.
"""

import os
import json
import csv
import time
import numpy as np

import spike2_2_reference_renderer as ref
import spike2_2_candidate as cand
import spike2_2_evaluation as ev

OUTPUT_DIR = "spike2_2_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CONFIGS = [
    {
        "id": "C1_contact_only",
        "name": "Contact Grounding Only",
        "flags": dict(enable_ao=False, enable_contact=True, enable_diffuse=False, enable_self=False, enable_cast=False, enable_confidence=False)
    },
    {
        "id": "C2_ao_only",
        "name": "Ambient Occlusion Only",
        "flags": dict(enable_ao=True, enable_contact=False, enable_diffuse=False, enable_self=False, enable_cast=False, enable_confidence=False)
    },
    {
        "id": "C3_diffuse_only",
        "name": "Diffuse Orientation Only",
        "flags": dict(enable_ao=False, enable_contact=False, enable_diffuse=True, enable_self=False, enable_cast=False, enable_confidence=False)
    },
    {
        "id": "C4_self_only",
        "name": "Self-Occlusion Only",
        "flags": dict(enable_ao=False, enable_contact=False, enable_diffuse=False, enable_self=True, enable_cast=False, enable_confidence=False)
    },
    {
        "id": "C5_cast_only",
        "name": "Cast Shadow Only",
        "flags": dict(enable_ao=False, enable_contact=False, enable_diffuse=False, enable_self=False, enable_cast=True, enable_confidence=False)
    },
    {
        "id": "C6_contact_plus_cast",
        "name": "Contact + Cast Shadow",
        "flags": dict(enable_ao=False, enable_contact=True, enable_diffuse=False, enable_self=False, enable_cast=True, enable_confidence=False)
    },
    {
        "id": "C7_ao_plus_contact",
        "name": "AO + Contact Grounding",
        "flags": dict(enable_ao=True, enable_contact=True, enable_diffuse=False, enable_self=False, enable_cast=False, enable_confidence=False)
    },
    {
        "id": "C8_full_comp_no_conf",
        "name": "Full Comp (No Confidence)",
        "flags": dict(enable_ao=True, enable_contact=True, enable_diffuse=True, enable_self=True, enable_cast=True, enable_confidence=False, confidence_fallback=False)
    },
    {
        "id": "C9_full_comp_with_conf",
        "name": "Full Comp (Confidence Weighted)",
        "flags": dict(enable_ao=True, enable_contact=True, enable_diffuse=True, enable_self=True, enable_cast=True, enable_confidence=True, confidence_fallback=False)
    },
    {
        "id": "C10_full_comp_conf_fallback",
        "name": "Full Comp + Confidence Fallback",
        "flags": dict(enable_ao=True, enable_contact=True, enable_diffuse=True, enable_self=True, enable_cast=True, enable_confidence=True, confidence_fallback=True)
    }
]

def run_ablation_study():
    print("\n" + "="*80)
    print("RELIGHT STUDIO — SPIKE 2.2 COMPONENT ABLATION SUITE")
    print("="*80)
    
    print("Pre-rendering test scenes for ablation...")
    test_scenes = {
        "S1_grounded_sphere": ref.render_reference_synthetic_scene("S1_grounded_sphere", H=256, W=384),
        "S3_step_box_90deg": ref.render_reference_synthetic_scene("S3_step_box_90deg", H=256, W=384),
        "S4_shoe_hull": ref.render_reference_synthetic_scene("S4_shoe_hull", H=256, W=384),
        "R1_sneaker": ev.load_case_R1()
    }
    
    ablation_results = []
    
    for cfg in CONFIGS:
        cid = cfg["id"]
        cname = cfg["name"]
        flags = cfg["flags"]
        
        print(f"\n[EVALUATING CONFIGURATION] {cid}: {cname}")
        
        cfg_metrics = []
        for sname, sdata in test_scenes.items():
            fg = sdata["fg_mask"]
            if np.any(fg):
                gy = int(np.where(fg)[0].max())
            else:
                gy = int(sdata["H"] * 0.78)
            contact_seam = sdata.get("contact_seam", (gy, None))
            
            t0 = time.time()
            cand_res = cand.execute_candidate_light_transport(
                image_lin=sdata["image_lin"],
                depth=sdata["depth"],
                normals=sdata["normals"],
                fg_mask=sdata["fg_mask"],
                light_dir_3d=sdata["light_dir"],
                ground_y=gy,
                contact_seam=contact_seam,
                source_radius=sdata["source_radius"],
                **flags
            )
            lat = (time.time() - t0) * 1000.0
            
            cgs = ev.eval_CGS(cand_res["V_direct"], cand_res["C_contact"], sdata["contact_mask"])
            sdg = ev.eval_SDG(cand_res["V_direct"], sdata["contact_mask"], sdata["receiver_mask"])
            sbc = ev.eval_SBC(cand_res["V_direct"], sdata["receiver_mask"])
            slr = ev.eval_SLR(cand_res["V_direct"], sdata["cliff_mask"], sdata.get("V_direct_gt"), fg_mask=fg)
            sde = ev.eval_SDE(cand_res["V_direct"], sdata.get("V_direct_gt"), sdata["receiver_mask"])
            iou = ev.eval_IoU(cand_res["V_direct"], sdata.get("V_direct_gt"), sdata["receiver_mask"])
            rec = ev.eval_REC_shadow(cand_res["V_direct"], sdata.get("V_direct_gt"), sdata["receiver_mask"])
            for_m = ev.eval_FOR(cand_res["V_direct"], sdata["normals"], sdata["light_dir"], sdata.get("V_direct_gt"))
            dci = ev.eval_DCI(sdata["image_lin"], cand_res["relit_rgb"])
            
            cfg_metrics.append({
                "scene": sname, "cgs": cgs, "sdg": sdg, "sbc": sbc, "slr": slr,
                "sde": sde, "iou": iou, "rec": rec, "for": for_m, "dci": dci, "latency": lat
            })
            
        def mean_num(key):
            vals = [m[key] for m in cfg_metrics if isinstance(m[key], (int, float))]
            return round(float(np.mean(vals)), 4) if len(vals) > 0 else "NOT_APPLICABLE"
            
        entry = {
            "config_id": cid,
            "config_name": cname,
            "mean_CGS": mean_num("cgs"),
            "mean_SDG_px": mean_num("sdg"),
            "mean_SBC": mean_num("sbc"),
            "mean_SLR_pct": mean_num("slr"),
            "mean_SDE_px": mean_num("sde"),
            "mean_IoU": mean_num("iou"),
            "mean_REC_pct": mean_num("rec"),
            "mean_FOR_pct": mean_num("for"),
            "mean_DCI": mean_num("dci"),
            "mean_latency_ms": mean_num("latency")
        }
        ablation_results.append(entry)
        print(f"  -> CGS={entry['mean_CGS']}, SDG={entry['mean_SDG_px']}px, SBC={entry['mean_SBC']}, SLR={entry['mean_SLR_pct']}%, SDE={entry['mean_SDE_px']}, IoU={entry['mean_IoU']}, REC={entry['mean_REC_pct']}%, DCI={entry['mean_DCI']}")

    json_path = os.path.join(OUTPUT_DIR, "ablation_results.json")
    with open(json_path, "w") as f:
        json.dump(ablation_results, f, indent=2)
    print(f"\n[SAVED] Ablation JSON -> {json_path}")
    
    csv_path = os.path.join(OUTPUT_DIR, "ablation_results.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(ablation_results[0].keys()))
        writer.writeheader()
        writer.writerows(ablation_results)
    print(f"[SAVED] Ablation CSV -> {csv_path}")
    
    return ablation_results

if __name__ == "__main__":
    run_ablation_study()
