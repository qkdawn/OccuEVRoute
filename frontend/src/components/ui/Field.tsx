type SelectOptions<T extends string> = Record<T, string>;

interface SelectFieldProps<T extends string> {
  label: string;
  onChange: (value: T) => void;
  options: SelectOptions<T>;
  value: T;
}

interface NumberFieldProps {
  label: string;
  max: number;
  min: number;
  onChange: (value: number) => void;
  step: number;
  value: number;
}

export function SelectField<T extends string>({ label, onChange, options, value }: SelectFieldProps<T>) {
  return (
    <label className="ui-field">
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value as T)}>
        {Object.entries(options).map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {String(optionLabel)}
          </option>
        ))}
      </select>
    </label>
  );
}

export function NumberField({ label, max, min, onChange, step, value }: NumberFieldProps) {
  return (
    <label className="ui-field">
      {label}
      <input type="number" min={min} max={max} step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}
