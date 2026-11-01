/** Failure from ontology loading, Intent validation, dialect parsing, or the FFI call. */
export class OntographiaError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "OntographiaError";
  }
}

export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
