import { useCallback, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { PostFilterParams, SavedFilterPreset } from '../../types';
import { LIFECYCLE_LABELS, SAVED_FILTERS_KEY } from '../../analytics/constants';
import {
  postFiltersFromSearchParams,
  postFiltersToSearchParams,
} from '../../lib/urlFilters';

type FilterBarProps = {
  onChange: (filters: PostFilterParams) => void;
};

function loadPresets(): SavedFilterPreset[] {
  try {
    const raw = localStorage.getItem(SAVED_FILTERS_KEY);
    if (!raw) {
      return [];
    }
    return JSON.parse(raw) as SavedFilterPreset[];
  } catch {
    return [];
  }
}

function savePresets(presets: SavedFilterPreset[]) {
  localStorage.setItem(SAVED_FILTERS_KEY, JSON.stringify(presets));
}

export function FilterBar({ onChange }: FilterBarProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(
    () => postFiltersFromSearchParams(searchParams),
    [searchParams]
  );
  const [presets, setPresets] = useState<SavedFilterPreset[]>(loadPresets);
  const [presetName, setPresetName] = useState('');

  const apply = useCallback(
    (next: PostFilterParams) => {
      const params = postFiltersToSearchParams(next);
      setSearchParams(params, { replace: true });
      onChange(next);
    },
    [setSearchParams, onChange]
  );

  const updateField = (patch: Partial<PostFilterParams>) => {
    apply({ ...filters, ...patch });
  };

  const savePreset = () => {
    const name = presetName.trim();
    if (!name) {
      return;
    }
    const preset: SavedFilterPreset = {
      id: `${Date.now()}`,
      name,
      params: filters,
      createdAt: new Date().toISOString(),
    };
    const next = [preset, ...presets].slice(0, 10);
    setPresets(next);
    savePresets(next);
    setPresetName('');
  };

  const loadPreset = (preset: SavedFilterPreset) => {
    apply(preset.params);
  };

  return (
    <div className="filter-bar" aria-label="Post filters">
      <div className="filter-bar__row">
        <label className="filter-bar__field">
          Since
          <input
            type="datetime-local"
            value={filters.since?.slice(0, 16) ?? ''}
            onChange={(e) =>
              updateField({ since: e.target.value ? new Date(e.target.value).toISOString() : undefined })
            }
          />
        </label>
        <label className="filter-bar__field">
          Until
          <input
            type="datetime-local"
            value={filters.until?.slice(0, 16) ?? ''}
            onChange={(e) =>
              updateField({ until: e.target.value ? new Date(e.target.value).toISOString() : undefined })
            }
          />
        </label>
        <label className="filter-bar__field">
          Min ER
          <input
            type="number"
            step="0.001"
            value={filters.erMin ?? ''}
            onChange={(e) =>
              updateField({ erMin: e.target.value ? Number(e.target.value) : undefined })
            }
          />
        </label>
        <label className="filter-bar__field">
          Max ER
          <input
            type="number"
            step="0.001"
            value={filters.erMax ?? ''}
            onChange={(e) =>
              updateField({ erMax: e.target.value ? Number(e.target.value) : undefined })
            }
          />
        </label>
        <label className="filter-bar__field">
          Min impressions
          <input
            type="number"
            value={filters.impressionsMin ?? ''}
            onChange={(e) =>
              updateField({
                impressionsMin: e.target.value ? Number(e.target.value) : undefined,
              })
            }
          />
        </label>
        <label className="filter-bar__field">
          Voice
          <input
            type="text"
            value={filters.voice ?? ''}
            onChange={(e) => updateField({ voice: e.target.value || undefined })}
          />
        </label>
        <label className="filter-bar__field">
          Media type
          <input
            type="text"
            value={filters.mediaType ?? ''}
            onChange={(e) => updateField({ mediaType: e.target.value || undefined })}
          />
        </label>
        <label className="filter-bar__field">
          Lifecycle
          <select
            value={filters.lifecycle ?? ''}
            onChange={(e) =>
              updateField({
                lifecycle: (e.target.value || undefined) as PostFilterParams['lifecycle'],
              })
            }
          >
            <option value="">Any</option>
            {Object.entries(LIFECYCLE_LABELS).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="btn btn--ghost" onClick={() => apply({})}>
          Clear
        </button>
      </div>

      <div className="filter-bar__presets">
        <label className="filter-bar__field">
          Save preset
          <input
            type="text"
            placeholder="Preset name"
            value={presetName}
            onChange={(e) => setPresetName(e.target.value)}
          />
        </label>
        <button type="button" className="btn btn--ghost" onClick={savePreset}>
          Save filters
        </button>
        {presets.length > 0 ? (
          <div className="filter-bar__preset-list">
            {presets.map((p) => (
              <button
                key={p.id}
                type="button"
                className="filter-bar__preset-btn"
                onClick={() => loadPreset(p)}
              >
                {p.name}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
