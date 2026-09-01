import React, { useEffect, useState, useCallback, useMemo } from "react";
import api, { formatApiError } from "../lib/api";
import { Button, Card, Input, Field, Alert, Badge } from "./ui";
import { PrescriptionSheet } from "../pages/PrintPrescription";
import { v4 } from "../lib/uuid";
import {
  Save, Eye, RotateCcw, ArrowUp, ArrowDown, Trash2, CheckCircle2, ImagePlus,
} from "lucide-react";

const MAX_LOGO = 2 * 1024 * 1024;

export default function TemplateEditor() {
  const [camps, setCamps] = useState([]);
  const [campId, setCampId] = useState("");
  const [tpl, setTpl] = useState(null);
  const [published, setPublished] = useState(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/camps").then((r) => {
      setCamps(r.data.camps);
      const active = r.data.camps.find((c) => c.is_active) || r.data.camps[0];
      if (active) setCampId(active.id);
    }).catch((e) => setErr(formatApiError(e)));
  }, []);

  const load = useCallback(() => {
    if (!campId) return;
    setErr(""); setMsg("");
    api.get(`/templates?camp_id=${campId}`).then((r) => {
      const base = r.data.draft || r.data.published || r.data.defaults;
      setTpl({
        header_title: base.header_title, header_subtitle: base.header_subtitle,
        footer_note: base.footer_note, blocks: base.blocks.map((b) => ({ ...b })),
        logos: (base.logos || []).map((l) => ({ ...l })),
      });
      setPublished(r.data.published);
    }).catch((e) => setErr(formatApiError(e)));
  }, [campId]);
  useEffect(() => { load(); }, [load]);

  const camp = camps.find((c) => c.id === campId);
  const sampleRx = useMemo(() => ({
    reg_no: 101, full_name: "Sample Patient", date: new Date().toISOString().slice(0, 10),
    age: 52, gender: "M", phone: "9876543210", address: "12 MG Road, Kolkata",
    patient_qr: "sample-preview-uuid", camp_name: camp?.name, venue: camp?.venue,
  }), [camp?.name, camp?.venue]);

  const setBlock = useCallback((i, patch) => {
    setTpl((t) => (t ? { ...t, blocks: t.blocks.map((b, j) => (j === i ? { ...b, ...patch } : b)) } : t));
  }, []);

  const move = useCallback((i, dir) => {
    setTpl((t) => {
      if (!t) return t;
      const b = [...t.blocks];
      const j = i + dir;
      if (j < 0 || j >= b.length) return t;
      [b[i], b[j]] = [b[j], b[i]];
      return { ...t, blocks: b };
    });
  }, []);

  const addLogo = useCallback((file) => {
    if (!file) return;
    if (file.size > MAX_LOGO) { setErr("Logo must be 2 MB or smaller."); return; }
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) { setErr("Use PNG, JPEG or WebP."); return; }
    const reader = new FileReader();
    reader.onload = () => setTpl((t) => (t ? { ...t, logos: [...t.logos, { id: v4(), name: file.name, data_url: reader.result, order: t.logos.length }] } : t));
    reader.readAsDataURL(file);
  }, []);

  const moveLogo = useCallback((i, dir) => {
    setTpl((t) => {
      if (!t) return t;
      const l = [...t.logos];
      const j = i + dir;
      if (j < 0 || j >= l.length) return t;
      [l[i], l[j]] = [l[j], l[i]];
      return { ...t, logos: l };
    });
  }, []);

  const removeLogo = useCallback((i) => {
    setTpl((t) => (t ? { ...t, logos: t.logos.filter((_, j) => j !== i) } : t));
  }, []);

  const saveDraft = useCallback(async () => {
    if (!campId || !tpl) return;
    setBusy(true); setErr(""); setMsg("");
    try { await api.post("/templates/draft", { camp_id: campId, ...tpl }); setMsg("Draft saved."); }
    catch (e) { setErr(formatApiError(e)); }
    finally { setBusy(false); }
  }, [campId, tpl]);

  const publish = useCallback(async () => {
    if (!campId || !tpl) return;
    setBusy(true); setErr(""); setMsg("");
    try {
      await api.post("/templates/draft", { camp_id: campId, ...tpl });
      const r = await api.post("/templates/publish", { camp_id: campId });
      setPublished(r.data.published);
      setMsg(`Published v${r.data.published.version}.`);
    } catch (e) { setErr(formatApiError(e)); }
    finally { setBusy(false); }
  }, [campId, tpl]);

  const restore = useCallback(async () => {
    if (!campId) return;
    setBusy(true); setErr(""); setMsg("");
    try {
      const r = await api.post("/templates/restore-defaults", { camp_id: campId });
      const d = r.data.draft;
      setTpl({ header_title: d.header_title, header_subtitle: d.header_subtitle, footer_note: d.footer_note, blocks: d.blocks, logos: d.logos || [] });
      setMsg("Restored defaults.");
    }
    catch (e) { setErr(formatApiError(e)); }
    finally { setBusy(false); }
  }, [campId]);

  if (!campId) return <Alert tone="amber">Create a camp first to design its prescription template.</Alert>;
  if (!tpl) return null;

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <Field label="Camp">
            <select className="min-h-[44px] px-3.5 rounded-xl border border-slate-300" value={campId} onChange={(e) => setCampId(e.target.value)} data-testid="tpl-camp-select">
              {camps.map((c) => <option key={c.id} value={c.id}>{c.name}{c.is_active ? " (active)" : ""}</option>)}
            </select>
          </Field>
          {published && <Badge tone="emerald" className="mt-4">Published v{published.version}</Badge>}
          <div className="ml-auto flex gap-2 mt-4">
            <Button variant="ghost" onClick={restore} disabled={busy} data-testid="tpl-restore-button"><RotateCcw className="w-4 h-4" /> Defaults</Button>
            <Button variant="outline" onClick={saveDraft} disabled={busy} data-testid="tpl-save-draft-button"><Save className="w-4 h-4" /> Save draft</Button>
            <Button onClick={publish} disabled={busy} data-testid="tpl-publish-button"><CheckCircle2 className="w-4 h-4" /> Publish</Button>
          </div>
        </div>
        {err && <Alert className="mt-3">{err}</Alert>}
        {msg && <Alert tone="emerald" className="mt-3">{msg}</Alert>}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Editor */}
        <div className="space-y-4">
          <Card>
            <h3 className="font-display font-bold text-slate-900 mb-3">Letterhead</h3>
            <div className="space-y-3">
              <Field label="Title"><Input value={tpl.header_title} onChange={(e) => setTpl({ ...tpl, header_title: e.target.value })} data-testid="tpl-title-input" /></Field>
              <Field label="Subtitle"><Input value={tpl.header_subtitle} onChange={(e) => setTpl({ ...tpl, header_subtitle: e.target.value })} data-testid="tpl-subtitle-input" /></Field>
              <Field label="Footer note"><Input value={tpl.footer_note} onChange={(e) => setTpl({ ...tpl, footer_note: e.target.value })} data-testid="tpl-footer-input" /></Field>
            </div>
          </Card>

          <Card>
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-display font-bold text-slate-900">Sponsor Logos</h3>
              <label className="inline-flex items-center gap-2 min-h-[44px] px-4 rounded-xl bg-slate-900 text-white text-sm font-semibold cursor-pointer hover:bg-slate-800" data-testid="tpl-add-logo-label">
                <ImagePlus className="w-4 h-4" /> Add logo
                <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => { addLogo(e.target.files?.[0]); e.target.value = ""; }} data-testid="tpl-logo-input" />
              </label>
            </div>
            {tpl.logos.length === 0 ? <p className="text-slate-400 text-sm">No logos. PNG/JPEG/WebP ≤ 2 MB.</p> : (
              <div className="space-y-2" data-testid="tpl-logos-list">
                {tpl.logos.map((lg, i) => (
                  <div key={lg.id || `logo-${lg.name}-${i}`} className="flex items-center gap-3 p-2 rounded-xl border border-slate-200">
                    <img src={lg.data_url} alt={lg.name} className="h-10 w-10 object-contain rounded bg-slate-50" />
                    <span className="flex-1 text-sm text-slate-700 truncate">{lg.name}</span>
                    <Button size="sm" variant="ghost" onClick={() => moveLogo(i, -1)}><ArrowUp className="w-4 h-4" /></Button>
                    <Button size="sm" variant="ghost" onClick={() => moveLogo(i, 1)}><ArrowDown className="w-4 h-4" /></Button>
                    <Button size="sm" variant="ghost" onClick={() => removeLogo(i)} data-testid={`tpl-remove-logo-${i}`}><Trash2 className="w-4 h-4 text-rose-500" /></Button>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card>
            <h3 className="font-display font-bold text-slate-900 mb-3">Blocks (order, visibility, height)</h3>
            <div className="space-y-2" data-testid="tpl-blocks-list">
              {tpl.blocks.map((b, i) => (
                <div key={b.id} className="flex flex-wrap items-center gap-2 p-2.5 rounded-xl border border-slate-200" data-testid={`tpl-block-${b.id}`}>
                  <div className="flex flex-col">
                    <button onClick={() => move(i, -1)} className="text-slate-400 hover:text-slate-700" data-testid={`tpl-block-up-${b.id}`}><ArrowUp className="w-4 h-4" /></button>
                    <button onClick={() => move(i, 1)} className="text-slate-400 hover:text-slate-700" data-testid={`tpl-block-down-${b.id}`}><ArrowDown className="w-4 h-4" /></button>
                  </div>
                  <Input className="flex-1 min-w-[120px]" value={b.label} onChange={(e) => setBlock(i, { label: e.target.value })} data-testid={`tpl-block-label-${b.id}`} />
                  {b.type === "lines" && (
                    <div className="flex items-center gap-1">
                      <Input type="number" className="w-20 text-center" value={b.height} onChange={(e) => setBlock(i, { height: Number(e.target.value) })} data-testid={`tpl-block-height-${b.id}`} />
                      <span className="text-xs text-slate-400">mm</span>
                    </div>
                  )}
                  <label className="inline-flex items-center gap-1.5 text-sm text-slate-600 min-h-[44px] px-2">
                    <input type="checkbox" checked={b.visible} onChange={(e) => setBlock(i, { visible: e.target.checked })} className="w-5 h-5" data-testid={`tpl-block-visible-${b.id}`} />
                    Show
                  </label>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* Live A4 preview */}
        <Card className="overflow-hidden">
          <div className="flex items-center gap-2 mb-3">
            <Eye className="w-5 h-5 text-slate-400" />
            <h3 className="font-display font-bold text-slate-900">A4 Preview</h3>
          </div>
          <div className="border border-slate-200 rounded-xl overflow-auto bg-slate-100 p-3" style={{ maxHeight: "70vh" }}>
            <div style={{ transform: "scale(0.55)", transformOrigin: "top left", width: "210mm" }} data-testid="tpl-preview">
              <PrescriptionSheet rx={sampleRx} tpl={tpl} preview />
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
