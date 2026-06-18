// Mirror of backend app/pipeline/spec/validator.py ValidationReport (doc 05 §5.2).
export type ValidationError = {
  code: string;             // stable code set (doc 05 §5.2)
  step_id?: string | null;
  artifact?: string | null;
  detail?: string;
};

export type ValidationReport = { ok: boolean; errors: ValidationError[] };
