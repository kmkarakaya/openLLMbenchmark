import { Field } from "./field";
import { Select } from "./select";

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
  return (
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
  );
}
