"""
IMS · objective measurement ingest.

Coach OS captures optional instrumented assessment data such as:

  ActivForce 2  · coach-approved peak isometric force and active/passive ROM
  Manual entry  · coach-entered force or ROM measurements
  VOLTRA        · verified isometric compound-pattern measurements only

Dynamic VOLTRA workout exports are not isometric strength tests and must not be
promoted into this object. Device-specific ingestion belongs upstream; this
module only normalizes already-approved evidence.

Those arrive in an OPTIONAL ``objective_measures`` object carrying the current
assessment, the previous one when it exists, and both dates.

Design rules that are not negotiable ·

1. Graceful degradation is the FIRST requirement. Absent or partial data must
   produce byte-identical output to a build with no objective data at all.
   Nothing in this module may raise into the generator · malformed entries are
   dropped and recorded as warnings. Loud failure happens at the API boundary
   (see validation.py), not mid-generation.
2. Everything is normalized once, here · force to lb, ROM to degrees, joints to
   the same canonical vocabulary the contraindication router already uses.
3. Every derived value keeps a pointer back to the measurement and the date
   that produced it, so the coach output can say where a number came from.
"""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Optional

from ims_contract import load_thresholds


CANONICAL_JOINTS = {
    "knee", "shoulder", "hip", "lumbar", "cervical", "wrist", "elbow", "ankle",
}

DYNAMO_TESTS = {
    "grip": ("wrist", "grip"), "hand_grip": ("wrist", "grip"),
    "wrist_flexion": ("wrist", "flexion"), "wrist_extension": ("wrist", "extension"),
    "shoulder_ir": ("shoulder", "ir"), "shoulder_er": ("shoulder", "er"),
    "shoulder_abduction": ("shoulder", "abduction"), "shoulder_adduction": ("shoulder", "adduction"),
    "shoulder_flexion": ("shoulder", "flexion"), "shoulder_extension": ("shoulder", "extension"),
    "hip_abduction": ("hip", "abduction"), "hip_adduction": ("hip", "adduction"),
    "hip_ir": ("hip", "ir"), "hip_er": ("hip", "er"),
    "hip_flexion": ("hip", "flexion"), "hip_extension": ("hip", "extension"),
    "imtp": ("hip", "isometric_mid_thigh_pull"),
    "knee_extension": ("knee", "extension"), "knee_flexion": ("knee", "flexion"),
    "ankle_dorsiflexion": ("ankle", "dorsiflexion"), "ankle_plantarflexion": ("ankle", "plantarflexion"),
    "ankle_inversion": ("ankle", "inversion"), "ankle_eversion": ("ankle", "eversion"),
    "elbow_flexion": ("elbow", "flexion"), "elbow_extension": ("elbow", "extension"),
    "cervical_flexion": ("cervical", "flexion"), "cervical_extension": ("cervical", "extension"),
    "cervical_lateral_flexion": ("cervical", "lateral_flexion"),
    "trunk_flexion": ("lumbar", "flexion"), "trunk_extension": ("lumbar", "extension"),
}

_JOINT_ALIASES = {"shoulders":"shoulder","gh":"shoulder","glenohumeral":"shoulder","knees":"knee","hips":"hip","low_back":"lumbar","lower_back":"lumbar","back":"lumbar","lumbar_spine":"lumbar","spine":"lumbar","neck":"cervical","cervical_spine":"cervical","hand":"wrist","grip":"wrist","ankles":"ankle","foot":"ankle"}
_SIDE_ALIASES = {"l":"L","left":"L","lt":"L","r":"R","right":"R","rt":"R","b":"bilateral","bi":"bilateral","both":"bilateral","bilateral":"bilateral","":"bilateral","n/a":"bilateral"}

def canonical_joint(raw):
    if raw is None: return None
    s=str(raw).strip().lower().replace(" ","_").replace("-","_")
    s=_JOINT_ALIASES.get(s,s)
    return s if s in CANONICAL_JOINTS else None

def canonical_side(raw): return _SIDE_ALIASES.get(str(raw or "").strip().lower(),"bilateral")
def canonical_motion(raw):
    s=str(raw or "").strip().lower().replace(" ","_").replace("-","_")
    return {"internal_rotation":"ir","int_rotation":"ir","internal_rot":"ir","external_rotation":"er","ext_rotation":"er","external_rot":"er","abd":"abduction","add":"adduction","flex":"flexion","ext":"extension","df":"dorsiflexion"}.get(s,s)

def _to_float(v):
    import math,re
    if v is None or isinstance(v,bool): return None
    if isinstance(v,(int,float)): value=float(v)
    elif isinstance(v,str):
        # Units must be supplied separately: stripping "kg" would silently treat it as lb.\n        m=re.fullmatch(r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*",v,re.I)
        if not m: return None
        value=float(m.group(1))
    else: return None
    return value if math.isfinite(value) else None

def _to_lb(value,unit,cfg):
    import math
    if value is None or not math.isfinite(value): return None
    u=str(unit or "lb").strip().lower(); units=cfg.get("units",{})
    if u in ("lb","lbs","pound","pounds",""): return float(value)
    if u in ("kg","kgs","kilogram","kilograms"): return float(value)*float(units.get("kg_to_lb",2.2046226218))
    if u in ("n","newton","newtons"): return float(value)*float(units.get("newton_to_lb",0.2248089431))
    return None

def _parse_date(raw):
    if not raw: return None
    if isinstance(raw,(date,datetime)): return raw.strftime("%Y-%m-%d")
    s=str(raw).strip()
    for fmt in ("%Y-%m-%d","%Y/%m/%d","%m/%d/%Y","%m-%d-%Y","%d %b %Y","%b %d, %Y"):
        try: return datetime.strptime(s[:len(fmt)+4],fmt).strftime("%Y-%m-%d")
        except ValueError: pass
    try: return datetime.fromisoformat(s.replace("Z","+00:00")).strftime("%Y-%m-%d")
    except ValueError: return None

def days_between(later_iso,earlier_iso):
    if not later_iso or not earlier_iso: return None
    try: return (datetime.strptime(later_iso,"%Y-%m-%d")-datetime.strptime(earlier_iso,"%Y-%m-%d")).days
    except (ValueError,TypeError): return None

@dataclass
class ForceMeasure:
    test:str; joint:Optional[str]; motion:str; side:str; value_lb:float
    device:str="dynamo"; position:Optional[str]=None; raw_value:Optional[float]=None; raw_unit:Optional[str]=None; measured_on:Optional[str]=None
    source:str="manual"; source_id:Optional[str]=None; metrics:dict=field(default_factory=dict)
    @property
    def key(self): return f"{self.test}_{self.side}{'_'+self.position if self.position else ''}".lower()
    def label(self):
        p=[self.test.replace("_"," ")]
        if self.position:p.append(self.position.replace("_","-"))
        if self.side in ("L","R"):p.append(self.side)
        return " · ".join(p)
    def evidence(self): return f"{self.label()} {int(round(self.value_lb))} lb{', '+self.measured_on if self.measured_on else ''}"

@dataclass
class RomMeasure:
    joint:str; motion:str; side:str; degrees:float; mode:str="passive"; measured_on:Optional[str]=None; source:str="manual"; source_id:Optional[str]=None
    @property
    def key(self): return f"{self.joint}_{self.motion}_{self.side}".lower()
    def label(self): return f"{self.joint} {self.motion}{' '+self.side if self.side in ('L','R') else ''}".replace("_"," ")
    def evidence(self): return f"{self.label()} {int(round(self.degrees))}°{', '+self.measured_on if self.measured_on else ''}"

@dataclass
class MeasureSet:
    measured_on:Optional[str]=None; bodyweight_lb:Optional[float]=None; forces:list=field(default_factory=list); roms:list=field(default_factory=list); notes:str=""
    def is_empty(self): return not self.forces and not self.roms
    def force(self,test,side=None,position=None):
        for f in self.forces:
            if f.test!=test: continue
            if side and f.side!=side: continue
            if position and f.position!=position: continue
            if position is None and f.position not in (None,"peak"): continue
            return f
    def forces_for_joint(self,joint): return [f for f in self.forces if f.joint==joint]
    def rom(self,joint,motion,side=None):
        for r in self.roms:
            if r.joint==joint and r.motion==motion and (not side or r.side==side): return r
    def tested_joints(self):
        seen=[]
        for f in self.forces:
            if f.joint and f.joint not in seen: seen.append(f.joint)
        return seen

@dataclass
class ObjectiveMeasures:
    current:MeasureSet; previous:Optional[MeasureSet]=None; warnings:list=field(default_factory=list)
    @property
    def current_date(self): return self.current.measured_on if self.current else None
    @property
    def previous_date(self): return self.previous.measured_on if self.previous else None
    def has_data(self): return self.current is not None and not self.current.is_empty()
    def has_previous(self): return self.previous is not None and not self.previous.is_empty()
    def age_days(self): return days_between(self.current_date,self.previous_date)
    def deltas(self,cfg=None):
        if not self.has_previous(): return []
        cfg=cfg or load_thresholds(); pct_gate=float(cfg.get("delta",{}).get("meaningful_change_pct",8.0)); deg_gate=float(cfg.get("delta",{}).get("meaningful_rom_change_deg",5)); out=[]
        for f in self.current.forces:
            prev=self.previous.force(f.test,f.side,f.position)
            if prev is None or not prev.value_lb: continue
            delta=f.value_lb-prev.value_lb; pct=delta/prev.value_lb*100
            out.append({"kind":"force","label":f.label(),"previous":round(prev.value_lb,1),"current":round(f.value_lb,1),"unit":"lb","delta":round(delta,1),"delta_pct":round(pct,1),"meaningful":abs(pct)>=pct_gate,"direction":"up" if delta>0 else "down" if delta<0 else "flat","previous_date":self.previous_date,"current_date":self.current_date})
        for r in self.current.roms:
            prev=self.previous.rom(r.joint,r.motion,r.side)
            if prev is None: continue
            delta=r.degrees-prev.degrees
            out.append({"kind":"rom","label":r.label(),"previous":round(prev.degrees,1),"current":round(r.degrees,1),"unit":"deg","delta":round(delta,1),"delta_pct":round(delta/prev.degrees*100,1) if prev.degrees else None,"meaningful":abs(delta)>=deg_gate,"direction":"up" if delta>0 else "down" if delta<0 else "flat","previous_date":self.previous_date,"current_date":self.current_date})
        return out
    def measure_table(self):
        rows=[]
        for f in self.current.forces:
            row={"kind":"force","device":f.device,"test":f.test,"position":f.position,"side":f.side,"value":round(f.value_lb,1),"unit":"lb","measured_on":f.measured_on,"source":f.source}
            if f.metrics: row["metrics"]=f.metrics
            rows.append(row)
        for r in self.current.roms: rows.append({"kind":"rom","device":"goniometry","test":f"{r.joint}_{r.motion}","position":r.mode,"side":r.side,"value":round(r.degrees,1),"unit":"deg","measured_on":r.measured_on,"source":r.source})
        return rows
    def to_dict(self): return {"current_date":self.current_date,"previous_date":self.previous_date,"bodyweight_lb":self.current.bodyweight_lb if self.current else None,"measures":self.measure_table(),"sources":sorted({m.get("source","manual") for m in self.measure_table()}),"warnings":list(self.warnings)}

def _parse_measure_set(raw,cfg,warnings,which,fallback_date=None):
    if not isinstance(raw,dict):
        if raw not in (None,{},[]): warnings.append(f"objective_measures.{which} ignored · expected an object")
        return None
    measured_on=_parse_date(raw.get("date") or raw.get("measured_on") or fallback_date); bw=_to_float(raw.get("bodyweight_lb") or raw.get("bodyweight"))
    if bw is not None and raw.get("bodyweight_unit"): bw=_to_lb(bw,raw.get("bodyweight_unit"),cfg)
    if bw is not None and not (50<=bw<=700): warnings.append(f"objective_measures.{which}.bodyweight {bw} out of range · ignored"); bw=None
    ms=MeasureSet(measured_on=measured_on,bodyweight_lb=bw,notes=str(raw.get("notes") or ""))
    for i,entry in enumerate(raw.get("dynamo") or raw.get("force") or []):
        if not isinstance(entry,dict): warnings.append(f"{which}.dynamo[{i}] ignored · not an object"); continue
        test=str(entry.get("test") or entry.get("name") or "").strip().lower().replace(" ","_").replace("-","_")
        if test not in DYNAMO_TESTS: warnings.append(f"{which}.dynamo[{i}] ignored · unknown test '{test}'"); continue
        val=_to_float(entry.get("value") if entry.get("value") is not None else entry.get("peak_force")); lb=_to_lb(val,entry.get("unit"),cfg)
        if lb is None or not (0 < lb <= 700): warnings.append(f"{which}.dynamo[{i}] ({test}) ignored · invalid or implausible force"); continue
        source=str(entry.get("source") or "manual")
        if source.startswith("activforce") and (entry.get("side") not in ("L","R","bilateral") or not measured_on): warnings.append(f"{which}.dynamo[{i}] ignored · ActivForce requires side and date"); continue
        joint,motion=DYNAMO_TESTS[test]
        ms.forces.append(ForceMeasure(test=test,joint=joint,motion=motion,side=canonical_side(entry.get("side")),value_lb=lb,device="activforce_2" if source.startswith("activforce") else "dynamo",raw_value=val,raw_unit=str(entry.get("unit") or "lb"),measured_on=measured_on,source=source,source_id=str(entry["source_id"]) if entry.get("source_id") else None,metrics=entry.get("metrics") if isinstance(entry.get("metrics"),dict) else {}))
    for i,entry in enumerate(raw.get("voltra") or []):
        if not isinstance(entry,dict): warnings.append(f"{which}.voltra[{i}] ignored · not an object"); continue
        pattern=str(entry.get("pattern") or entry.get("test") or "").strip().lower().replace(" ","_").replace("-","_"); position=str(entry.get("position") or "").strip().lower().replace("-","_")
        if position in ("mid","midrange"): position="mid_range"
        if position in ("end","endrange"): position="end_range"
        if not pattern or position not in ("mid_range","end_range"): warnings.append(f"{which}.voltra[{i}] ignored · needs pattern + mid_range/end_range"); continue
        val=_to_float(entry.get("value") if entry.get("value") is not None else entry.get("peak_force")); lb=_to_lb(val,entry.get("unit"),cfg)
        if lb is None or lb<=0: warnings.append(f"{which}.voltra[{i}] ignored · unreadable value"); continue
        ms.forces.append(ForceMeasure(test=pattern,joint=canonical_joint(entry.get("joint")),motion=canonical_motion(entry.get("motion") or "compound"),side=canonical_side(entry.get("side")),value_lb=lb,device="voltra",position=position,raw_value=val,raw_unit=str(entry.get("unit") or "lb"),measured_on=measured_on))
    rom_raw=raw.get("rom") or raw.get("rom_degrees") or []
    if isinstance(rom_raw,dict):
        converted=[]
        for k,v in rom_raw.items():
            parts=str(k).split("_"); side=parts[-1] if parts and parts[-1].lower() in ("l","r") else None; core=parts[:-1] if side else parts
            if len(core)>=2: converted.append({"joint":core[0],"motion":"_".join(core[1:]),"side":side,"degrees":v})
        rom_raw=converted
    for i,entry in enumerate(rom_raw or []):
        if not isinstance(entry,dict): warnings.append(f"{which}.rom[{i}] ignored · not an object"); continue
        joint=canonical_joint(entry.get("joint")); motion=canonical_motion(entry.get("motion") or entry.get("direction")); deg=_to_float(entry.get("degrees") if entry.get("degrees") is not None else entry.get("value"))
        if not joint or not motion or deg is None: warnings.append(f"{which}.rom[{i}] ignored · needs joint, motion and degrees"); continue
        if not (-50<=deg<=200): warnings.append(f"{which}.rom[{i}] ignored · {deg}° out of plausible range"); continue
        source=str(entry.get("source") or "manual"); mode=str(entry.get("mode") or "").strip().lower()
        if source.startswith("activforce") and (mode not in ("active","passive") or entry.get("side") not in ("L","R","bilateral") or not measured_on or deg<0): warnings.append(f"{which}.rom[{i}] ignored · ActivForce requires explicit mode, side and date"); continue
        if mode and mode not in ("active","passive"): warnings.append(f"{which}.rom[{i}] ignored · unrecognized ROM mode"); continue
        ms.roms.append(RomMeasure(joint=joint,motion=motion,side=canonical_side(entry.get("side")),degrees=deg,mode=mode or "passive",measured_on=measured_on,source=source,source_id=str(entry["source_id"]) if entry.get("source_id") else None))
    return ms

def parse_objective_measures(raw,cfg=None):
    if not isinstance(raw,dict) or not raw: return None
    cfg=cfg or load_thresholds(); warnings=[]
    current_raw=raw.get("current")
    if current_raw is None and ("dynamo" in raw or "rom" in raw or "voltra" in raw): current_raw=raw
    current=_parse_measure_set(current_raw,cfg,warnings,"current",raw.get("current_date"))
    if current is None or current.is_empty(): return None
    previous=_parse_measure_set(raw.get("previous"),cfg,warnings,"previous",raw.get("previous_date")) if raw.get("previous") else None
    return ObjectiveMeasures(current=current,previous=previous,warnings=warnings)
