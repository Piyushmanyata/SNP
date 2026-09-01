import React, { useEffect, useState, useCallback, useMemo } from "react";
import api, { formatApiError } from "../lib/api";
import { Button, Card, Alert } from "./ui";
import { v4 } from "../lib/uuid";
import { Save } from "lucide-react";
import { swapItems, validateLogoFile, buildSampleRx } from "./template/templateHelpers";
import { TemplateLogosEditor } from "./template/TemplateLogosEditor";
import { TemplatePreview } from "./template/TemplatePreview";

export default function TemplateEditor() {
  const [camps, setCamps] = useState([]);
  const [campId, setCampId] = useState("");
  const [logos, setLogos] = useState(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get("/camps")
      .then((r) => {
        setCamps(r.data.camps);
        const active = r.data.camps.find((c) => c.is_active) || r.data.camps[0];
        if (active) setCampId(active.id);
      })
      .catch((e) => setErr(formatApiError(e)));
  }, []);

  const load = useCallback(() => {
    if (!campId) return;
    setErr("");
    setMsg("");
    api
      .get(`/templates/logos?camp_id=${campId}`)
      .then((r) => setLogos((r.data.logos || []).map((l) => ({ ...l }))))
      .catch((e) => setErr(formatApiError(e)));
  }, [campId]);

  useEffect(() => {
    load();
  }, [load]);

  const camp = camps.find((c) => c.id === campId);
  const sampleRx = useMemo(() => buildSampleRx(camp), [camp]);

  const addLogo = useCallback((file) => {
    const { valid, error } = validateLogoFile(file);
    if (!valid) {
      if (error) setErr(error);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setLogos((current) => [
        ...(current || []),
        { id: v4(), name: file.name, data_url: reader.result, order: (current || []).length },
      ]);
    };
    reader.readAsDataURL(file);
  }, []);

  const moveLogo = useCallback((i, dir) => {
    setLogos((current) => (current ? swapItems(current, i, dir) : current));
  }, []);

  const removeLogo = useCallback((i) => {
    setLogos((current) => (current ? current.filter((_, j) => j !== i) : current));
  }, []);

  const save = useCallback(async () => {
    if (!campId || !logos) return;
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const { data } = await api.put("/templates/logos", {
        camp_id: campId,
        logos: logos.map((l, i) => ({ ...l, order: i })),
      });
      setLogos(data.logos);
      setMsg("Sponsor logos saved. The change is live.");
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }, [campId, logos]);

  return (
    <div className="space-y-4">
      <Card>
        <h3 className="font-display font-bold text-slate-900 mb-1">Prescription</h3>
        <p className="text-sm text-slate-500" data-testid="tpl-locked-note">
          The header, address block, layout and footer are fixed in code so the printed form
          always matches the trust's paper. Sponsor logos are the only editable part.
        </p>
        <label className="block mt-3 text-sm font-semibold text-slate-700" htmlFor="tpl-camp">
          Camp
        </label>
        <select
          id="tpl-camp"
          className="mt-1 w-full sm:w-80 min-h-[44px] px-3 rounded-xl border border-slate-300"
          value={campId}
          onChange={(e) => setCampId(e.target.value)}
          data-testid="tpl-camp-select"
        >
          {camps.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
              {c.is_active ? " (active)" : ""}
            </option>
          ))}
        </select>
      </Card>

      {err && <Alert>{err}</Alert>}
      {msg && <Alert tone="emerald">{msg}</Alert>}

      {logos && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <div className="space-y-4">
            <TemplateLogosEditor
              logos={logos}
              onAddLogo={addLogo}
              onMoveLogo={moveLogo}
              onRemoveLogo={removeLogo}
            />
            <Button onClick={save} disabled={busy} data-testid="tpl-save-logos-button">
              <Save className="w-4 h-4" /> {busy ? "Saving…" : "Save logos"}
            </Button>
          </div>
          <TemplatePreview sampleRx={sampleRx} logos={logos} />
        </div>
      )}
    </div>
  );
}
