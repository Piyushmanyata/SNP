import React from "react";
import { Button, Card } from "../ui";
import { ArrowUp, ArrowDown, Trash2, ImagePlus } from "lucide-react";
import { MAX_LOGOS } from "./templateHelpers";

export function TemplateLogosEditor({ logos, onAddLogo, onMoveLogo, onRemoveLogo }) {
  const full = logos.length >= MAX_LOGOS;
  return (
    <Card>
      <div className="flex items-center justify-between mb-1">
        <h3 className="font-display font-bold text-slate-900">Sponsor Logos</h3>
        <label
          className={`inline-flex items-center gap-2 min-h-[44px] px-4 rounded-xl bg-slate-900 text-white text-sm font-semibold ${full ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:bg-slate-800"}`}
          data-testid="tpl-add-logo-label"
        >
          <ImagePlus className="w-4 h-4" /> Add logo
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            disabled={full}
            onChange={(e) => {
              onAddLogo(e.target.files?.[0]);
              e.target.value = "";
            }}
            data-testid="tpl-logo-input"
          />
        </label>
      </div>
      <p className="text-sm text-slate-700 mb-3" data-testid="tpl-logo-limits">
        {logos.length} of {MAX_LOGOS}. Up to {MAX_LOGOS} logos, PNG, JPEG or WebP, each up to 2 MB. Saved logos are resized to at most 600 px and 150 KB.
      </p>
      {logos.length === 0 ? (
        <p className="text-slate-600 text-sm">No logos.</p>
      ) : (
        <div className="space-y-2" data-testid="tpl-logos-list">
          {logos.map((lg, i) => (
            <div
              key={lg.id || `logo-${lg.name}-${i}`}
              className="flex items-center gap-3 p-2 rounded-xl border border-slate-200"
            >
              <img
                src={lg.data_url}
                alt={lg.name}
                className="h-10 w-10 object-contain rounded bg-slate-50"
              />
              <span className="flex-1 text-sm text-slate-700 truncate">{lg.name}</span>
              <Button size="sm" variant="ghost" onClick={() => onMoveLogo(i, -1)}>
                <ArrowUp className="w-4 h-4" />
              </Button>
              <Button size="sm" variant="ghost" onClick={() => onMoveLogo(i, 1)}>
                <ArrowDown className="w-4 h-4" />
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => onRemoveLogo(i)}
                data-testid={`tpl-remove-logo-${i}`}
              >
                <Trash2 className="w-4 h-4 text-rose-500" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
