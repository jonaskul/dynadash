import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Edit2, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";
import { createArea, deleteArea, getConfigAreas, updateArea } from "../api/client";
import type { AreaConfig, AreaType } from "../api/types";

interface PresetRow {
  key: string;
  label: string;
}


function presetsToRows(presets: Record<string, string>): PresetRow[] {
  return Object.entries(presets).map(([key, label]) => ({ key, label }));
}

function rowsToPresets(rows: PresetRow[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const row of rows) {
    if (row.key.trim()) out[row.key.trim()] = row.label;
  }
  return out;
}

interface FormState {
  id: string;
  name: string;
  type: AreaType;
  channels: string;
  presetRows: PresetRow[];
  temp_min: string;
  temp_max: string;
  order: string;
}

function configToForm(cfg: AreaConfig): FormState {
  return {
    id: String(cfg.id),
    name: cfg.name,
    type: cfg.type,
    channels: String(cfg.channels),
    presetRows: presetsToRows(cfg.presets),
    temp_min: String(cfg.temp_min),
    temp_max: String(cfg.temp_max),
    order: String(cfg.order),
  };
}

function blankForm(): FormState {
  return {
    id: "",
    name: "",
    type: "lighting",
    channels: "1",
    presetRows: [],
    temp_min: "16",
    temp_max: "30",
    order: "0",
  };
}

function formToConfig(form: FormState): AreaConfig {
  return {
    id: parseInt(form.id, 10),
    name: form.name.trim(),
    type: form.type,
    channels: parseInt(form.channels, 10) || 1,
    presets: rowsToPresets(form.presetRows),
    temp_min: parseFloat(form.temp_min) || 16,
    temp_max: parseFloat(form.temp_max) || 30,
    order: parseInt(form.order, 10) || 0,
  };
}

function validate(form: FormState): string | null {
  const id = parseInt(form.id, 10);
  if (!form.id || isNaN(id) || id < 1 || id > 65535)
    return "Area ID must be a number between 1 and 65535.";
  if (!form.name.trim()) return "Name is required.";
  if (form.type === "lighting") {
    const ch = parseInt(form.channels, 10);
    if (isNaN(ch) || ch < 1) return "Channel count must be at least 1.";
  }
  return null;
}

interface AreaFormProps {
  initialForm: FormState;
  onSubmit: (cfg: AreaConfig) => Promise<void>;
  onCancel: () => void;
  submitLabel: string;
  idDisabled?: boolean;
}

function AreaForm({ initialForm, onSubmit, onCancel, submitLabel, idDisabled }: AreaFormProps) {
  const [form, setForm] = useState<FormState>(initialForm);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function addPresetRow() {
    setForm((f) => ({ ...f, presetRows: [...f.presetRows, { key: "", label: "" }] }));
  }

  function updatePresetRow(index: number, field: keyof PresetRow, value: string) {
    setForm((f) => {
      const rows = [...f.presetRows];
      rows[index] = { ...rows[index], [field]: value };
      return { ...f, presetRows: rows };
    });
  }

  function removePresetRow(index: number) {
    setForm((f) => ({ ...f, presetRows: f.presetRows.filter((_, i) => i !== index) }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const err = validate(form);
    if (err) { setFormError(err); return; }
    setFormError(null);
    setSubmitting(true);
    try {
      await onSubmit(formToConfig(form));
    } catch (ex) {
      setFormError(String(ex));
    } finally {
      setSubmitting(false);
    }
  }

  const inputCls = "w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-white placeholder-slate-500 outline-none focus:border-electric-blue/50 focus:ring-1 focus:ring-electric-blue/20";

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-400">Area ID</label>
          <input type="number" className={inputCls} value={form.id}
            onChange={(e) => updateField("id", e.target.value)}
            disabled={idDisabled} min={1} max={65535} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-400">Display Order</label>
          <input type="number" className={inputCls} value={form.order}
            onChange={(e) => updateField("order", e.target.value)} min={0} />
        </div>
      </div>

      <div>
        <label className="mb-1 block text-xs font-medium text-slate-400">Name</label>
        <input type="text" className={inputCls} value={form.name}
          onChange={(e) => updateField("name", e.target.value)} placeholder="Living Room" />
      </div>

      <div>
        <label className="mb-1 block text-xs font-medium text-slate-400">Type</label>
        <select className={inputCls} value={form.type}
          onChange={(e) => updateField("type", e.target.value as AreaType)}>
          <option value="lighting">Lighting</option>
          <option value="thermostat">Thermostat</option>
        </select>
      </div>

      {form.type === "lighting" && (
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-400">Number of Channels</label>
          <input type="number" className={inputCls} value={form.channels}
            onChange={(e) => updateField("channels", e.target.value)} min={1} max={32} />
        </div>
      )}

      {form.type === "thermostat" && (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-400">Temp Min (°C)</label>
            <input type="number" className={inputCls} value={form.temp_min}
              onChange={(e) => updateField("temp_min", e.target.value)} step={0.5} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-400">Temp Max (°C)</label>
            <input type="number" className={inputCls} value={form.temp_max}
              onChange={(e) => updateField("temp_max", e.target.value)} step={0.5} />
          </div>
        </div>
      )}

      {/* Presets */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <label className="text-xs font-medium text-slate-400">Presets</label>
          <button type="button" onClick={addPresetRow}
            className="flex items-center gap-1 rounded-md border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:text-white hover:border-electric-blue/30 transition">
            <Plus className="h-3 w-3" /> Add
          </button>
        </div>
        <div className="space-y-2">
          {form.presetRows.map((row, i) => (
            <div key={i} className="flex items-center gap-2">
              <input type="text" placeholder="Preset #" value={row.key}
                onChange={(e) => updatePresetRow(i, "key", e.target.value)}
                className="w-24 rounded-md border border-white/15 bg-white/5 px-2 py-1.5 text-xs text-white placeholder-slate-500 outline-none focus:border-electric-blue/50" />
              <input type="text" placeholder="Label" value={row.label}
                onChange={(e) => updatePresetRow(i, "label", e.target.value)}
                className="flex-1 rounded-md border border-white/15 bg-white/5 px-2 py-1.5 text-xs text-white placeholder-slate-500 outline-none focus:border-electric-blue/50" />
              <button type="button" onClick={() => removePresetRow(i)}
                className="rounded-md p-1 text-slate-500 hover:text-red-400 transition">
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {formError && <p className="text-sm text-red-400">{formError}</p>}

      <div className="flex gap-3 pt-2">
        <button type="submit" disabled={submitting}
          className="flex-1 rounded-lg bg-electric-blue py-2 text-sm font-semibold text-navy-900 hover:bg-electric-blue-light transition disabled:opacity-40">
          {submitLabel}
        </button>
        <button type="button" onClick={onCancel}
          className="rounded-lg border border-white/15 bg-white/5 px-4 py-2 text-sm text-slate-300 hover:text-white transition">
          Cancel
        </button>
      </div>
    </form>
  );
}

export default function AreaManagerView() {
  const queryClient = useQueryClient();
  const { data: areas = [], isLoading } = useQuery({
    queryKey: ["config-areas"],
    queryFn: getConfigAreas,
    staleTime: 30_000,
  });

  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["config-areas"] });

  async function handleCreate(cfg: AreaConfig) {
    await createArea(cfg);
    invalidate();
    setShowAdd(false);
  }

  async function handleUpdate(cfg: AreaConfig) {
    await updateArea(cfg.id, cfg);
    invalidate();
    setEditingId(null);
  }

  async function handleDelete(id: number) {
    if (!confirm(`Delete area ${id}? This cannot be undone.`)) return;
    try {
      await deleteArea(id);
      invalidate();
    } catch (e) {
      setDeleteError(String(e));
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Area Manager</h1>
        {!showAdd && (
          <button onClick={() => { setShowAdd(true); setEditingId(null); }}
            className="flex items-center gap-2 rounded-lg bg-electric-blue px-4 py-2 text-sm font-semibold text-navy-900 hover:bg-electric-blue-light transition">
            <Plus className="h-4 w-4" /> Add Area
          </button>
        )}
      </div>

      {/* Add form */}
      {showAdd && (
        <div className="rounded-xl border border-electric-blue/30 bg-navy-800/60 p-5 backdrop-blur-sm animate-fade-in">
          <h2 className="mb-4 text-sm font-semibold text-electric-blue">New Area</h2>
          <AreaForm
            initialForm={blankForm()}
            onSubmit={handleCreate}
            onCancel={() => setShowAdd(false)}
            submitLabel="Create Area"
          />
        </div>
      )}

      {deleteError && (
        <p className="text-sm text-red-400">{deleteError}</p>
      )}

      {/* Area list */}
      {isLoading ? (
        <div className="flex h-32 items-center justify-center">
          <div className="h-7 w-7 animate-spin rounded-full border-2 border-electric-blue border-t-transparent" />
        </div>
      ) : areas.length === 0 && !showAdd ? (
        <div className="rounded-xl border border-dashed border-white/10 py-12 text-center">
          <p className="text-slate-500">No areas yet. Click "Add Area" to get started.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {areas.map((area) => (
            <div key={area.id}
              className="rounded-xl border border-white/10 bg-navy-800/60 p-4 backdrop-blur-sm animate-fade-in">
              {editingId === area.id ? (
                <>
                  <h3 className="mb-3 text-sm font-semibold text-electric-blue">
                    Editing: {area.name}
                  </h3>
                  <AreaForm
                    initialForm={configToForm(area)}
                    onSubmit={handleUpdate}
                    onCancel={() => setEditingId(null)}
                    submitLabel="Save Changes"
                    idDisabled
                  />
                </>
              ) : (
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-medium text-white">{area.name}</p>
                    <p className="text-xs text-slate-500">
                      ID {area.id} · {area.type === "lighting" ? `Lighting · ${area.channels} ch` : "Thermostat"}
                      {Object.keys(area.presets).length > 0 &&
                        ` · ${Object.keys(area.presets).length} presets`}
                    </p>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <button onClick={() => { setEditingId(area.id); setShowAdd(false); }}
                      className="rounded-md p-1.5 text-slate-400 hover:text-white hover:bg-white/10 transition">
                      <Edit2 className="h-4 w-4" />
                    </button>
                    <button onClick={() => handleDelete(area.id)}
                      className="rounded-md p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 transition">
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
