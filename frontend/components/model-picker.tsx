import { Field } from "./field";
import { Select } from "./select";

export function ModelPicker({
  label,
  options,
  selected,
  manual,
  onSelectedChange,
  onManualChange,
  disabled = false
}: {
  label: string;
  options: string[];
  selected: string;
  manual: string;
  onSelectedChange: (value: string) => void;
  onManualChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="grid gap-2">
      <Field label={label}>
        <Select value={selected} onChange={(event) => onSelectedChange(event.target.value)} disabled={disabled}>
          <option value="">Select from model list</option>
          {options.map((model) => (
            <option key={model} value={model}>
              {model}
            </option>
          ))}
        </Select>
      </Field>
      <Field label={`${label} (Manual)`}>
        <input
          className="focus-ring h-10 rounded-ui border border-border bg-white px-3 text-sm"
          value={manual}
          onChange={(event) => onManualChange(event.target.value)}
          placeholder="Enter model name manually"
          disabled={disabled}
        />
      </Field>
    </div>
  );
}
