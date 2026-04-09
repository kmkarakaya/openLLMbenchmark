import { Field } from "./field";
import { Select } from "./select";

function modelSource(model: string): "cloud" | "local" {
  const normalized = model.trim().toLowerCase();
  if (normalized.endsWith(":local")) {
    return "local";
  }
  return "cloud";
}

export function ModelPicker({
  label,
  options,
  selected,
  onSelectedChange,
  disabled = false
}: {
  label: string;
  options: string[];
  selected: string;
  onSelectedChange: (value: string) => void;
  disabled?: boolean;
}) {
  const cloudModels: string[] = [];
  const localModels: string[] = [];
  for (const model of options) {
    if (modelSource(model) === "local") {
      localModels.push(model);
    } else {
      cloudModels.push(model);
    }
  }

  return (
    <Field label={label}>
      <Select value={selected} onChange={(event) => onSelectedChange(event.target.value)} disabled={disabled}>
        <option value="">Select from model list</option>
        {localModels.length ? (
          <optgroup label="----- LOCAL MODELS -----">
            {localModels.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </optgroup>
        ) : null}
        {cloudModels.length ? (
          <optgroup label="----- CLOUD MODELS -----">
            {cloudModels.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </optgroup>
        ) : null}
      </Select>
    </Field>
  );
}
