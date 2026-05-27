import { useId, useState } from "react";

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
  const [isOpen, setIsOpen] = useState(false);
  const listboxId = useId();
  const selectedLabel = options[value];

  return (
    <div className="ui-field">
      <span>{label}</span>
      <div className="ui-select-shell">
        <button
          type="button"
          className="ui-select-trigger"
          aria-expanded={isOpen}
          aria-haspopup="listbox"
          aria-controls={listboxId}
          onBlur={(event) => {
            if (!event.currentTarget.parentElement?.contains(event.relatedTarget as Node | null)) {
              setIsOpen(false);
            }
          }}
          onClick={() => setIsOpen((current) => !current)}
          onKeyDown={(event) => {
            if (event.key === "Escape") setIsOpen(false);
          }}
        >
          <span>{selectedLabel}</span>
          <span className="ui-select-chevron" aria-hidden="true" />
        </button>
        {isOpen && (
          <div id={listboxId} className="ui-select-options" role="listbox" tabIndex={-1}>
            {(Object.entries(options) as [T, string][]).map(([optionValue, optionLabel]) => (
              <button
                type="button"
                key={optionValue}
                className={["ui-select-option", optionValue === value ? "selected" : ""].filter(Boolean).join(" ")}
                role="option"
                aria-selected={optionValue === value}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => {
                  onChange(optionValue);
                  setIsOpen(false);
                }}
              >
                <span>{optionLabel}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
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
