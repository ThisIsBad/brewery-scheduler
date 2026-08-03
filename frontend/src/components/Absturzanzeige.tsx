import { Component, type ReactNode } from "react";

// Error boundary of last resort: a crash after mount must show its message
// instead of unmounting to a blank page. Inline styles on purpose — this
// must render even when the stylesheet never loaded.
export class Absturzanzeige extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error === null) return this.props.children;
    return (
      <div style={{ padding: 24, maxWidth: "40rem", margin: "0 auto" }}>
        <h1 style={{ fontSize: "1.2rem" }}>⚠️ Die App ist abgestürzt</h1>
        <pre
          style={{
            whiteSpace: "pre-wrap",
            background: "#f6f2ea",
            padding: 12,
            borderRadius: 8,
            fontSize: ".85rem",
          }}
        >
          {this.state.error.message}
        </pre>
        <button
          onClick={() => window.location.reload()}
          style={{ padding: "12px 20px", fontSize: "1rem" }}
        >
          Neu laden
        </button>
        <p style={{ color: "#666", fontSize: ".85rem" }}>
          Screenshot dieser Seite genügt zur Fehlersuche.
        </p>
      </div>
    );
  }
}
